"""Network emulation for dynamic analysis ("netsim").

Many samples do nothing interesting unless their network calls succeed -- they
wait on a C2 handshake, a DNS answer, an HTTP 200. This stage lets the sample
"reach the internet" while actually talking to local fakes, and -- crucially --
logs every destination it *tried* to reach. That intended-destination list
(C2 IPs, ports, domains-by-resolution) is usually the most valuable artifact of
a dynamic run.

How it works, built on the existing ptrace core:
  * A local fake TCP server (HTTP-aware) and a local fake DNS server are started
    on loopback ephemeral ports.
  * The target runs under ptrace. At every ``connect()`` syscall-entry we read
    the sockaddr out of the child's memory, record the real destination, then
    rewrite that sockaddr in place to point at our loopback fake (port 53 UDP ->
    fake DNS; everything else -> fake TCP). The call then succeeds against the
    fake.
  * The fake DNS answers every A/AAAA query with loopback, so libc resolution
    succeeds and the subsequent connect() is caught and redirected too.

This EXECUTES the target. Use it in a VM or disposable container.

Limits (stated honestly): it redirects connect()-based flows (the common case).
Pure sendto()/sendmsg() datagram traffic with no connect() is logged by strace
but not answered here; raw AF_PACKET sockets are out of scope. It is emulation,
not containment -- it does not stop the sample doing other damage.

Requires python-ptrace. Linux x86-64 / aarch64.
"""
from __future__ import annotations

import os
import socket
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

from .util import Severity, StageResult

try:
    from ptrace.debugger import (
        PtraceDebugger, ProcessExit, ProcessSignal,
        NewProcessEvent, ProcessExecution,
    )
    from ptrace.debugger.child import createChild
    from ptrace.func_call import FunctionCallOptions
    HAVE_PTRACE = True
except ImportError:
    HAVE_PTRACE = False


AF_INET = 2
AF_INET6 = 10


# --------------------------------------------------------------------------- #
# Fake services                                                                #
# --------------------------------------------------------------------------- #
class FakeServices:
    """Loopback TCP (HTTP-aware) and DNS responders. Context manager."""

    def __init__(self, http_body: bytes = b"OK\n"):
        self.http_body = http_body
        self._stop = threading.Event()
        self.tcp_port = 0
        self.dns_port = 0
        self.hits: List[dict] = []
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()

    # -- TCP -------------------------------------------------------------- #
    def _make_tcp_socket(self):
        """Prefer a dual-stack IPv6 socket; fall back to IPv4 if v6 is off."""
        if socket.has_ipv6:
            try:
                srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                except OSError:
                    pass
                srv.bind(("::", 0))
                return srv
            except OSError:
                pass
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        return srv

    def _serve_tcp(self):
        srv = self._make_tcp_socket()
        self.tcp_port = srv.getsockname()[1]
        srv.listen(16)
        srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_tcp, args=(conn,),
                             daemon=True).start()
        srv.close()

    def _handle_tcp(self, conn: socket.socket):
        conn.settimeout(2.0)
        data = b""
        try:
            data = conn.recv(4096)
        except OSError:
            pass
        first = data[:200].decode("latin-1", "replace") if data else ""
        with self._lock:
            self.hits.append({"service": "tcp", "first_bytes": first})
        try:
            if data[:8].upper().startswith((b"GET", b"POST", b"HEAD", b"PUT",
                                            b"DELETE", b"OPTIONS")):
                body = self.http_body
                resp = (b"HTTP/1.1 200 OK\r\n"
                        b"Server: nginx\r\n"
                        b"Content-Type: text/plain\r\n"
                        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                        b"Connection: close\r\n\r\n" + body)
                conn.sendall(resp)
            else:
                # Generic banner then echo once, which satisfies many simple
                # custom C2 handshakes enough to advance the sample.
                conn.sendall(b"220 service ready\r\n")
                if data:
                    conn.sendall(data)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # -- DNS -------------------------------------------------------------- #
    def _serve_dns(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        self.dns_port = srv.getsockname()[1]
        srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                data, addr = srv.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            reply = self._dns_reply(data)
            if reply:
                try:
                    srv.sendto(reply, addr)
                except OSError:
                    pass
        srv.close()

    def _dns_reply(self, query: bytes) -> Optional[bytes]:
        if len(query) < 12:
            return None
        tid = query[:2]
        # Parse the queried name for logging.
        qname, qtype = self._parse_dns_question(query)
        with self._lock:
            self.hits.append({"service": "dns", "qname": qname, "qtype": qtype})
        flags = b"\x81\x80"  # standard response, no error
        qd = b"\x00\x01"
        an = b"\x00\x01"
        header = tid + flags + qd + an + b"\x00\x00" + b"\x00\x00"
        question = query[12:]  # original question section (name+type+class)
        # Answer: pointer to name at 0x0c, type A, class IN, ttl 60, rdlen 4.
        if qtype == 28:  # AAAA
            rtype = b"\x00\x1c"
            rdata = b"\x00" * 15 + b"\x01"  # ::1
            rdlen = b"\x00\x10"
        else:
            rtype = b"\x00\x01"
            rdata = socket.inet_aton("127.0.0.1")
            rdlen = b"\x00\x04"
        answer = b"\xc0\x0c" + rtype + b"\x00\x01" + b"\x00\x00\x00\x3c" + rdlen + rdata
        return header + question + answer

    @staticmethod
    def _parse_dns_question(query: bytes) -> Tuple[str, int]:
        try:
            i = 12
            labels = []
            while i < len(query) and query[i] != 0:
                ln = query[i]
                labels.append(query[i + 1:i + 1 + ln].decode("latin-1", "replace"))
                i += 1 + ln
            qtype = struct.unpack_from(">H", query, i + 1)[0] if i + 3 <= len(query) else 1
            return ".".join(labels), qtype
        except Exception:
            return "?", 1

    def __enter__(self):
        for fn in (self._serve_tcp, self._serve_dns):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self._threads.append(t)
        # Wait until both ports are assigned.
        for _ in range(50):
            if self.tcp_port and self.dns_port:
                break
            time.sleep(0.02)
        return self

    def __exit__(self, *exc):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=1.0)


# --------------------------------------------------------------------------- #
# ptrace connect() redirection                                                 #
# --------------------------------------------------------------------------- #
def _read_sockaddr(process, addr: int, length: int) -> Optional[bytes]:
    if not addr or length < 2:
        return None
    try:
        return process.readBytes(addr, min(length, 28))
    except Exception:
        return None


def _parse_dest(sa: bytes) -> Optional[Tuple[int, str, int]]:
    """Return (family, ip, port) from a sockaddr blob, or None."""
    if len(sa) < 2:
        return None
    family = struct.unpack_from("<H", sa, 0)[0]
    try:
        if family == AF_INET and len(sa) >= 8:
            port = struct.unpack_from(">H", sa, 2)[0]
            ip = socket.inet_ntop(socket.AF_INET, sa[4:8])
            return AF_INET, ip, port
        if family == AF_INET6 and len(sa) >= 24:
            port = struct.unpack_from(">H", sa, 2)[0]
            ip = socket.inet_ntop(socket.AF_INET6, sa[8:24])
            return AF_INET6, ip, port
    except OSError:
        return None
    return None


def _rewrite_sockaddr(process, addr: int, family: int, new_port: int) -> bool:
    """Rewrite the destination in child memory to loopback:new_port."""
    try:
        port_be = struct.pack(">H", new_port)
        if family == AF_INET:
            process.writeBytes(addr + 2, port_be)
            process.writeBytes(addr + 4, socket.inet_aton("127.0.0.1"))
        elif family == AF_INET6:
            process.writeBytes(addr + 2, port_be)
            process.writeBytes(addr + 8, b"\x00" * 15 + b"\x01")  # ::1
        else:
            return False
        return True
    except Exception:
        return False


_SYSCALL_NR_REG = {"x86_64": "orig_rax", "aarch64": "x8"}


def run_netsim(path: str, args: List[str], outdir: str,
               timeout: int = 20) -> StageResult:
    res = StageResult("netsim")
    if not HAVE_PTRACE:
        res.error = "python-ptrace not installed; run install.sh."
        return res

    os.chmod(path, os.stat(path).st_mode | 0o111)
    attempts: List[dict] = []

    print("\n" + "=" * 70)
    print("NETWORK EMULATION — redirecting the sample's connections to local")
    print("fakes and logging intended destinations. This EXECUTES the target.")
    print("=" * 70)

    with FakeServices() as fake:
        debugger = PtraceDebugger()
        try:
            debugger.traceFork()
            debugger.traceExec()
        except Exception:
            pass
        try:
            pid = createChild([path, *args], no_stdout=False, env=None)
        except Exception as exc:  # noqa: BLE001
            res.error = f"could not spawn target: {exc}"
            return res

        process = debugger.addProcess(pid, is_attached=True)
        nr_reg = "orig_rax"
        call_opts = FunctionCallOptions(write_types=False)
        deadline = time.time() + timeout
        process.syscall()

        try:
            while True:
                if time.time() > deadline:
                    break
                try:
                    debugger.waitSyscall()
                except ProcessExit:
                    break
                except ProcessSignal as event:
                    event.process.syscall(event.signum)
                    continue
                except (NewProcessEvent, ProcessExecution) as event:
                    event.process.syscall()
                    continue
                except KeyError:
                    break

                proc = debugger.list[0] if debugger.list else process
                state = proc.syscall_state
                try:
                    syscall = state.event(call_opts)
                except Exception:
                    proc.syscall()
                    continue
                if syscall is None:
                    proc.syscall()
                    continue

                if syscall.result is None and syscall.name == "connect":
                    try:
                        sa_ptr = syscall.arguments[1].value
                        sa_len = syscall.arguments[2].value
                    except Exception:
                        sa_ptr = sa_len = 0
                    sa = _read_sockaddr(proc, sa_ptr, sa_len or 28)
                    dest = _parse_dest(sa) if sa else None
                    if dest:
                        family, ip, port = dest
                        is_dns = (port == 53)
                        new_port = fake.dns_port if is_dns else fake.tcp_port
                        # Only redirect if the matching fake actually came up.
                        ok = (bool(new_port)
                              and _rewrite_sockaddr(proc, sa_ptr, family, new_port))
                        rec = {"family": "inet6" if family == AF_INET6 else "inet",
                               "dest_ip": ip, "dest_port": port,
                               "redirected": ok,
                               "to": "fake-dns" if is_dns else "fake-tcp"}
                        attempts.append(rec)
                        print(f"  connect -> {ip}:{port}"
                              f"{' (DNS)' if is_dns else ''}"
                              f"  [redirected to local {rec['to']}]")

                proc.syscall()
        finally:
            try:
                debugger.quit()
            except Exception:
                pass
        service_hits = list(fake.hits)

    # Persist + summarize.
    log = os.path.join(outdir, "netsim.log")
    with open(log, "w") as fh:
        fh.write("Attempted connections:\n")
        for a in attempts:
            fh.write(f"  {a['dest_ip']}:{a['dest_port']} ({a['family']}) "
                     f"-> {a['to']} redirected={a['redirected']}\n")
        fh.write("\nFake-service hits:\n")
        for h in service_hits:
            fh.write(f"  {h}\n")

    # Unique destinations, excluding loopback/DNS noise for the headline list.
    real_dests = sorted({(a["dest_ip"], a["dest_port"]) for a in attempts
                         if not a["dest_ip"].startswith("127.")
                         and a["dest_ip"] != "::1"})
    res.data = {
        "attempted_connections": attempts,
        "unique_destinations": [f"{ip}:{p}" for ip, p in real_dests],
        "fake_service_hits": service_hits,
        "log": log,
        "fake_tcp_port": fake.tcp_port,
        "fake_dns_port": fake.dns_port,
    }
    if real_dests:
        res.add(Severity.HIGH, "netsim",
                f"Sample attempted {len(real_dests)} outbound destination(s)",
                ", ".join(f"{ip}:{p}" for ip, p in real_dests))
    dns_names = sorted({h["qname"] for h in service_hits
                        if h.get("service") == "dns" and h.get("qname")})
    if dns_names:
        res.add(Severity.MEDIUM, "netsim", "Domains resolved by the sample",
                ", ".join(dns_names[:10]))
    return res
