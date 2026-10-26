"""Dynamic analysis stages. THESE EXECUTE THE TARGET BINARY.

Everything here actually runs the sample, so it should only be used on files you
are willing to execute (ideally inside a VM or disposable container). Each stage
runs under a timeout and writes raw logs into the report directory.

Stages:
  * strace  - system call trace (-f follows children)
  * ltrace  - library call trace
  * tcpdump - packet capture running alongside the sample
  * memdump - snapshot of the process memory maps while it runs
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import List, Optional

from .tools import ToolStatus
from .util import Severity, StageResult, run_tool


def _confirm_exec(path: str, assume_yes: bool) -> bool:
    print("\n" + "!" * 70)
    print(f"DYNAMIC ANALYSIS will EXECUTE the target:\n    {path}")
    print("Only continue inside a VM or disposable container.")
    print("!" * 70)
    if assume_yes:
        return True
    try:
        return input("Execute it now? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def run_strace(path: str, args: List[str], tools: ToolStatus, outdir: str,
               timeout: int = 20) -> StageResult:
    res = StageResult("strace")
    if not tools.has("strace"):
        res.error = "strace not installed"
        return res
    log = os.path.join(outdir, "strace.log")
    cp = run_tool(
        [tools.path("strace"), "-f", "-tt", "-T", "-y", "-s", "200",
         "-o", log, path, *args],
        timeout=timeout,
    )
    summary = _summarize_strace(log)
    res.data = {"log": log, "timed_out": cp.returncode == 124, **summary}
    if summary.get("network_syscalls"):
        res.add(Severity.MEDIUM, "dynamic",
                "Network syscalls observed",
                f"{summary['network_syscalls']} connect/socket/send calls.")
    if summary.get("exec_syscalls"):
        res.add(Severity.MEDIUM, "dynamic",
                "Process execution observed",
                f"{summary['exec_syscalls']} execve/clone calls.")
    return res


def _summarize_strace(log: str) -> dict:
    net = exe = files = 0
    opened = []
    try:
        with open(log, errors="replace") as fh:
            for line in fh:
                if any(k in line for k in ("connect(", "socket(", "sendto(",
                                           "recvfrom(")):
                    net += 1
                if "execve(" in line or "clone(" in line:
                    exe += 1
                if "openat(" in line or "open(" in line:
                    files += 1
                    if len(opened) < 40 and '"' in line:
                        try:
                            opened.append(line.split('"')[1])
                        except IndexError:
                            pass
    except OSError:
        return {}
    return {
        "network_syscalls": net,
        "exec_syscalls": exe,
        "file_syscalls": files,
        "sample_opened_paths": sorted(set(opened)),
    }


def run_ltrace(path: str, args: List[str], tools: ToolStatus, outdir: str,
               timeout: int = 20) -> StageResult:
    res = StageResult("ltrace")
    if not tools.has("ltrace"):
        res.error = "ltrace not installed"
        return res
    log = os.path.join(outdir, "ltrace.log")
    cp = run_tool(
        [tools.path("ltrace"), "-f", "-s", "200", "-o", log, path, *args],
        timeout=timeout,
    )
    lines = 0
    try:
        with open(log, errors="replace") as fh:
            lines = sum(1 for _ in fh)
    except OSError:
        pass
    res.data = {"log": log, "timed_out": cp.returncode == 124, "call_lines": lines}
    return res


def run_tcpdump(path: str, args: List[str], tools: ToolStatus, outdir: str,
                timeout: int = 20, iface: str = "any") -> StageResult:
    """Capture packets while the sample runs. Needs privileges for the capture."""
    res = StageResult("tcpdump")
    if not tools.has("tcpdump"):
        res.error = "tcpdump not installed"
        return res

    pcap = os.path.join(outdir, "capture.pcap")
    tcpdump_proc: Optional[subprocess.Popen] = None
    try:
        tcpdump_proc = subprocess.Popen(
            [tools.path("tcpdump"), "-i", iface, "-w", pcap, "-U", "-n"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except OSError as exc:
        res.error = f"could not start tcpdump: {exc}"
        return res

    time.sleep(0.5)  # let the capture come up
    if tcpdump_proc.poll() is not None:
        err = tcpdump_proc.stderr.read().decode(errors="replace") if tcpdump_proc.stderr else ""
        res.error = f"tcpdump exited early (need root?): {err.strip()}"
        return res

    # Run the sample under its own timeout.
    sample_rc = None
    try:
        sample = subprocess.Popen([path, *args],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        try:
            sample_rc = sample.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            sample.kill()
            sample_rc = "timeout"
    except OSError as exc:
        res.error = f"could not execute sample: {exc}"
    finally:
        tcpdump_proc.send_signal(signal.SIGINT)
        try:
            tcpdump_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tcpdump_proc.kill()

    size = os.path.getsize(pcap) if os.path.exists(pcap) else 0
    res.data = {"pcap": pcap, "pcap_bytes": size, "sample_exit": sample_rc}
    if size > 24:  # more than just the pcap global header
        res.add(Severity.MEDIUM, "dynamic", "Network traffic captured",
                f"{size} bytes written to {pcap}; inspect with wireshark/tshark.")
    return res


def run_memdump(path: str, args: List[str], outdir: str,
                timeout: int = 5) -> StageResult:
    """Snapshot the live process: /proc/<pid>/maps + readable region dump.

    This gives you something to carry into further memory analysis. It is a
    lightweight self-contained dump (no Volatility profile needed, since that
    targets full-system memory images, not a single process)."""
    res = StageResult("memdump")
    try:
        proc = subprocess.Popen([path, *args],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as exc:
        res.error = f"could not execute sample: {exc}"
        return res

    pid = proc.pid
    maps_path = os.path.join(outdir, f"maps_{pid}.txt")
    dump_path = os.path.join(outdir, f"mem_{pid}.bin")
    regions = 0
    dumped = 0
    try:
        time.sleep(0.3)  # let it map memory
        with open(f"/proc/{pid}/maps") as mh:
            maps = mh.read()
        with open(maps_path, "w") as out:
            out.write(maps)

        with open(f"/proc/{pid}/mem", "rb", 0) as mem, open(dump_path, "wb") as out:
            for line in maps.splitlines():
                if "r" not in line.split()[1][:1]:
                    continue
                bounds = line.split()[0]
                try:
                    start_s, end_s = bounds.split("-")
                    start, end = int(start_s, 16), int(end_s, 16)
                    if end - start > 64 * 1024 * 1024:
                        continue  # skip huge regions
                    mem.seek(start)
                    out.write(mem.read(end - start))
                    regions += 1
                    dumped += end - start
                except (OSError, ValueError):
                    continue
    except (OSError, PermissionError) as exc:
        res.error = (f"memory read failed ({exc}); may need ptrace permission "
                     "(sudo, or /proc/sys/kernel/yama/ptrace_scope=0).")
    finally:
        proc.kill()

    res.data = {
        "maps_file": maps_path if os.path.exists(maps_path) else None,
        "dump_file": dump_path if dumped else None,
        "regions_dumped": regions,
        "bytes_dumped": dumped,
    }
    return res


def run_dynamic_suite(path: str, args: List[str], tools: ToolStatus, outdir: str,
                      timeout: int, assume_yes: bool,
                      do_tcpdump: bool, do_memdump: bool) -> List[StageResult]:
    """Run the non-interactive dynamic stages (used by --dynamic / --all)."""
    if not _confirm_exec(path, assume_yes):
        r = StageResult("dynamic")
        r.error = "user declined execution"
        return [r]

    results = [run_strace(path, args, tools, outdir, timeout),
               run_ltrace(path, args, tools, outdir, timeout)]
    if do_tcpdump:
        results.append(run_tcpdump(path, args, tools, outdir, timeout))
    if do_memdump:
        results.append(run_memdump(path, args, outdir, timeout))
    return results
