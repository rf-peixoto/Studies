#!/usr/bin/env python3
import socket
import ssl
import json
import argparse
from datetime import datetime

TIMEOUT = 4.0

PORTS = {
    "imap_plain": 143,
    "imap_tls": 993,
    "pop3_plain": 110,
    "pop3_tls": 995,
}

def recv_line(sock, max_bytes=8192):
    sock.settimeout(TIMEOUT)
    data = b""
    while b"\n" not in data and len(data) < max_bytes:
        chunk = sock.recv(1024)
        if not chunk:
            break
        data += chunk
    return data.decode(errors="replace").strip()

def send_cmd(sock, cmd):
    if not cmd.endswith("\r\n"):
        cmd += "\r\n"
    sock.sendall(cmd.encode())

def connect_plain(host, port):
    s = socket.create_connection((host, port), timeout=TIMEOUT)
    return s

def connect_tls(host, port):
    raw = socket.create_connection((host, port), timeout=TIMEOUT)
    ctx = ssl.create_default_context()
    # For auditing you generally want verification ON; if you need to capture self-signed certs,
    # keep verification but handle exceptions outside. Do not disable verification silently.
    tls = ctx.wrap_socket(raw, server_hostname=host)
    return tls

def audit_imap(sock):
    results = {"greeting": None, "capability": None}
    results["greeting"] = recv_line(sock)
    # IMAP CAPABILITY is typically allowed pre-auth
    send_cmd(sock, "a1 CAPABILITY")
    # Read a few lines (capability + completion)
    lines = []
    for _ in range(8):
        line = recv_line(sock)
        if not line:
            break
        lines.append(line)
        if line.lower().startswith("a1 "):
            break
    results["capability"] = lines
    # politely logout
    try:
        send_cmd(sock, "a2 LOGOUT")
    except Exception:
        pass
    return results

def audit_pop3(sock):
    results = {"greeting": None, "capa": None}
    results["greeting"] = recv_line(sock)
    # POP3 CAPA is allowed pre-auth
    send_cmd(sock, "CAPA")
    lines = []
    for _ in range(32):
        line = recv_line(sock)
        if not line:
            break
        lines.append(line)
        if line == ".":
            break
    results["capa"] = lines
    try:
        send_cmd(sock, "QUIT")
    except Exception:
        pass
    return results

def check_host(host):
    host = host.strip()
    if not host or host.startswith("#"):
        return None

    entry = {
        "host": host,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": {}
    }

    for name, port in PORTS.items():
        proto = "imap" if "imap" in name else "pop3"
        tls = name.endswith("_tls")

        r = {"port": port, "open": False, "tls": tls, "error": None, "data": None}
        try:
            sock = connect_tls(host, port) if tls else connect_plain(host, port)
            r["open"] = True

            if proto == "imap":
                r["data"] = audit_imap(sock)
            else:
                r["data"] = audit_pop3(sock)

            try:
                sock.close()
            except Exception:
                pass

        except Exception as e:
            r["error"] = f"{type(e).__name__}: {e}"

        entry["results"][name] = r

    return entry

def main():
    ap = argparse.ArgumentParser(description="Audit IMAP/POP3 exposure and capabilities without authentication.")
    ap.add_argument("-i", "--input", required=True, help="Input file with domains/IPs (one per line).")
    ap.add_argument("-o", "--output", default="mail_audit_report.json", help="Output JSON report file.")
    ap.add_argument("--host-logs", default="host_logs", help="Directory for per-host logs.")
    args = ap.parse_args()

    import os
    os.makedirs(args.host_logs, exist_ok=True)

    report = {"generated_at": datetime.utcnow().isoformat() + "Z", "hosts": []}

    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            host = line.strip()
            if not host or host.startswith("#"):
                continue
            entry = check_host(host)
            if entry:
                report["hosts"].append(entry)

                # Write per-host log (evidence)
                log_path = os.path.join(args.host_logs, f"{host.replace('/', '_')}.txt")
                with open(log_path, "w", encoding="utf-8") as lf:
                    lf.write(json.dumps(entry, indent=2))
                    lf.write("\n")

    with open(args.output, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)

    print(f"Wrote JSON report to: {args.output}")
    print(f"Wrote per-host logs to: {args.host_logs}/")

if __name__ == "__main__":
    main()
