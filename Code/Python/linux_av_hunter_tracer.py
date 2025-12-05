# GOOD LORD, THIS SH*T WAS A PAIN IN THE A*S. Tested on Fedora, probably won't work outside my room.
#
# PoC – Trace a single Linux process and detect attempts to tamper with
# common AV/EDR agents via signals, systemctl, and file operations.
#
# REQUIREMENTS:
#   - Run as root
#   - BCC / eBPF available (python3-bcc)
#
# USAGE:
#   sudo python linux_av_hunter_tracer.py /path/to/sample [args...]
#
# LIMITATIONS (still):
#   - Only traces the main sample PID (no child process tracking yet).
#   - No cgroup or namespace isolation handled in this PoC.
#   - eBPF argv buffer is bounded (first N args, limited total length).
#

import os
import sys
import json
import time
import errno
import signal
import subprocess
import shlex
from collections import defaultdict
from datetime import datetime

from bcc import BPF

# --------------------------------------------------------------------------------------
# 1. AV / EDR SURFACE CONFIGURATION
# --------------------------------------------------------------------------------------

AV_SURFACE = {
    "process_names": [
        # CrowdStrike
        "falcon-sensor",
        "falcond",

        # Microsoft Defender for Endpoint (Linux)
        "mdatp",

        # ClamAV
        "clamd",
        "clamonacc",
        "freshclam",

        # Sophos (various)
        "savd",
        "savscand",
        "sophos-spl",
        "sophosd",
        "sophosfs",

        # Symantec / Broadcom (examples)
        "sisamddaemon",
        "sesmagent",
        "sepm",

        # Trend Micro (examples)
        "ds_agent",
        "ds_am",
        "ds_notifier",

        # ESET (examples)
        "ekrn",
        "esets_daemon",

        # Kaspersky (examples)
        "klnagent",
        "kesl",

        # Bitdefender (examples)
        "bdwd",
        "bdredline",

        # SentinelOne (examples)
        "sentinelagent",
        "sentineld",

        # OSSEC / Wazuh / Beats (examples)
        "ossec-agentd",
        "wazuh-agentd",
        "auditbeat",
        "filebeat",
        "packetbeat",

        # Generic names
        "avagent",
        "edragent",
        "endpoint-agent",
        "securityagent",
    ],

    "paths": [
        "/opt/CrowdStrike/falcon-sensor",
        "/opt/CrowdStrike/",
        "/opt/microsoft/mdatp/",
        "/usr/bin/mdatp",
        "/usr/sbin/clamd",
        "/usr/sbin/clamav-daemon",
        "/var/lib/clamav/",
        "/opt/sophos/",
        "/opt/sophos-spl/",
        "/opt/Symantec/",
        "/opt/sep/",
        "/opt/TrendMicro/",
        "/opt/eset/",
        "/opt/kaspersky/",
        "/opt/BitDefender/",
        "/opt/sentinelone/",
        "/var/ossec/",
        "/var/ossec/bin/",
        "/var/ossec/active-response/bin/",
        "/var/osquery/",
    ],

    "systemd_units": [
        "falcon-sensor.service",
        "falcon-sensor",
        "mdatp.service",
        "microsoft-defender.service",
        "clamav-daemon.service",
        "clamav-freshclam.service",
        "sophos.service",
        "sophos-spl.service",
        "symantec.service",
        "sep.service",
        "ds_agent.service",
        "eset.service",
        "kesl.service",
        "sentinelagent.service",
        "sentinelone.service",
        "avagent.service",
        "edragent.service",
        "endpoint-agent.service",
        "securityagent.service",
    ],

    "directories": [
        "/opt/CrowdStrike/",
        "/opt/microsoft/mdatp/",
        "/var/lib/clamav/",
        "/opt/sophos/",
        "/opt/Symantec/",
        "/opt/sep/",
        "/opt/TrendMicro/",
        "/opt/eset/",
        "/opt/kaspersky/",
        "/opt/BitDefender/",
        "/opt/sentinelone/",
        "/var/ossec/",
        "/var/osquery/",
    ],
}


# --------------------------------------------------------------------------------------
# 2. eBPF PROGRAM (with argv capture)
# --------------------------------------------------------------------------------------

BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <uapi/linux/limits.h>
#include <linux/sched.h>

// Event type definitions
#define EV_SIGNAL   1
#define EV_EXECVE   2
#define EV_OPENAT   3
#define EV_UNLINKAT 4

#define ARGS_BUF_SIZE  512
#define MAX_ARGS       16

struct event_t {
    u32 pid;
    u32 ppid;
    u32 tpid;           // target pid for signals (0 if not applicable)
    int sig;            // signal number (for EV_SIGNAL)
    int ev_type;        // one of EV_*
    char comm[TASK_COMM_LEN]; // current process name
    char filename[PATH_MAX];  // execve filename or open/unlink path

    // Concatenated argv string: "arg0 arg1 arg2 ..."
    char argv[ARGS_BUF_SIZE];
};

BPF_PERF_OUTPUT(events);

// Helper: fill base fields
static __inline int fill_common(struct pt_regs *ctx, struct event_t *ev, int ev_type) {
    struct task_struct *task = (struct task_struct *)bpf_get_current_task();
    ev->pid = bpf_get_current_pid_tgid() >> 32;
    ev->ppid = 0;
    ev->tpid = 0;
    ev->sig = 0;
    ev->ev_type = ev_type;
    bpf_get_current_comm(&ev->comm, sizeof(ev->comm));

    if (task && task->real_parent) {
        ev->ppid = task->real_parent->tgid;
    }

    ev->filename[0] = '\0';
    ev->argv[0] = '\0';
    return 0;
}

// ---- kill / tgkill / tkill ----

int trace_kill(struct pt_regs *ctx, pid_t pid, int sig) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_SIGNAL);
    ev.tpid = pid;
    ev.sig = sig;
    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}

int trace_tgkill(struct pt_regs *ctx, pid_t tgid, pid_t pid, int sig) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_SIGNAL);
    ev.tpid = pid;
    ev.sig = sig;
    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}

int trace_tkill(struct pt_regs *ctx, pid_t pid, int sig) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_SIGNAL);
    ev.tpid = pid;
    ev.sig = sig;
    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}

// ---- execve (with argv capture) ----

int trace_execve(struct pt_regs *ctx,
                 const char __user *filename,
                 const char __user *const __user *argv,
                 const char __user *const __user *envp) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_EXECVE);

    // filename
    bpf_probe_read_user_str(&ev.filename, sizeof(ev.filename), filename);

    // concatenate up to MAX_ARGS arguments into ev.argv
    int pos = 0;
    #pragma unroll
    for (int i = 0; i < MAX_ARGS; i++) {
        const char __user *argp = NULL;
        int ret = bpf_probe_read_user(&argp, sizeof(argp), &argv[i]);
        if (ret < 0) {
            break;
        }
        if (argp == NULL) {
            break;
        }

        if (pos >= ARGS_BUF_SIZE - 1) {
            break;
        }

        int len = bpf_probe_read_user_str(&ev.argv[pos], ARGS_BUF_SIZE - pos, argp);
        if (len <= 0) {
            break;
        }

        // bpf_probe_read_user_str includes the terminating '\0', replace it with space
        if (len > 0) {
            if (pos + len >= ARGS_BUF_SIZE) {
                pos = ARGS_BUF_SIZE - 1;
                break;
            }
            pos += len;
            if (pos >= ARGS_BUF_SIZE) {
                pos = ARGS_BUF_SIZE - 1;
                break;
            }
            ev.argv[pos - 1] = ' ';
        }
    }

    if (pos > 0) {
        if (pos >= ARGS_BUF_SIZE) {
            pos = ARGS_BUF_SIZE - 1;
        }
        ev.argv[pos] = '\0';
    }

    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}

// ---- openat ----

int trace_openat(struct pt_regs *ctx,
                 int dfd,
                 const char __user *filename,
                 int flags,
                 umode_t mode) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_OPENAT);
    bpf_probe_read_user_str(&ev.filename, sizeof(ev.filename), filename);
    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}

// ---- unlinkat ----

int trace_unlinkat(struct pt_regs *ctx,
                   int dfd,
                   const char __user *pathname,
                   int flags) {
    struct event_t ev = {};
    fill_common(ctx, &ev, EV_UNLINKAT);
    bpf_probe_read_user_str(&ev.filename, sizeof(ev.filename), pathname);
    events.perf_submit(ctx, &ev, sizeof(ev));
    return 0;
}
"""


# --------------------------------------------------------------------------------------
# 3. UTILITIES
# --------------------------------------------------------------------------------------

def readlink_safe(path: str) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return ""


def read_comm(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def get_exe_basename(pid: int) -> str:
    exe = readlink_safe(f"/proc/{pid}/exe")
    if not exe:
        return ""
    return os.path.basename(exe)


def path_matches_av(path: str) -> bool:
    if not path:
        return False
    for prefix in AV_SURFACE["paths"]:
        if path.startswith(prefix):
            return True
    for d in AV_SURFACE["directories"]:
        if path.startswith(d):
            return True
    return False


def name_matches_av(name: str) -> bool:
    if not name:
        return False
    base = os.path.basename(name)
    return base in AV_SURFACE["process_names"]


def unit_matches_av(unit: str) -> bool:
    if not unit:
        return False
    return unit in AV_SURFACE["systemd_units"]


# --------------------------------------------------------------------------------------
# 4. MAIN TRACE LOGIC
# --------------------------------------------------------------------------------------

class AVHunterTracer:
    def __init__(self, sample_pid: int):
        self.sample_pid = sample_pid
        self.tracked_pids = {sample_pid}  # PoC: only main PID
        self.detections = []
        self.stats = defaultdict(int)

        self.bpf = BPF(text=BPF_PROGRAM)

        # Attach kprobes (x86-64 syscall entry symbols)
        self.bpf.attach_kprobe(event="__x64_sys_kill", fn_name="trace_kill")
        self.bpf.attach_kprobe(event="__x64_sys_tgkill", fn_name="trace_tgkill")
        self.bpf.attach_kprobe(event="__x64_sys_tkill", fn_name="trace_tkill")
        self.bpf.attach_kprobe(event="__x64_sys_execve", fn_name="trace_execve")
        self.bpf.attach_kprobe(event="__x64_sys_openat", fn_name="trace_openat")
        self.bpf.attach_kprobe(event="__x64_sys_unlinkat", fn_name="trace_unlinkat")

        self.bpf["events"].open_perf_buffer(self._handle_event)

    def _handle_event(self, cpu, data, size):
        event = self.bpf["events"].event(data)
        pid = event.pid

        if pid not in self.tracked_pids:
            return

        ev_type = event.ev_type
        if ev_type == 1:
            self._handle_signal_event(event)
        elif ev_type == 2:
            self._handle_execve_event(event)
        elif ev_type == 3:
            self._handle_open_event(event)
        elif ev_type == 4:
            self._handle_unlink_event(event)

    def _record_detection(self, category: str, detail: dict):
        det = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "category": category,
            "detail": detail,
        }
        self.detections.append(det)

    # --- HANDLERS ---

    def _handle_signal_event(self, event):
        pid = event.pid
        tpid = event.tpid
        sig = event.sig

        target_comm = read_comm(tpid)
        target_exe = readlink_safe(f"/proc/{tpid}/exe")
        target_base = os.path.basename(target_exe) if target_exe else ""

        if not (target_comm or target_exe):
            return

        if name_matches_av(target_comm) or name_matches_av(target_base) or path_matches_av(target_exe):
            self.stats["signal_av"] += 1
            self._record_detection(
                "signal_av_process",
                {
                    "src_pid": int(pid),
                    "src_comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                    "target_pid": int(tpid),
                    "target_comm": target_comm,
                    "target_exe": target_exe,
                    "signal": int(sig),
                },
            )

    def _handle_execve_event(self, event):
        pid = event.pid
        filename = event.filename.decode("utf-8", errors="ignore").strip("\x00")
        argv_str = event.argv.decode("utf-8", errors="ignore").strip("\x00")

        self.stats["execve"] += 1

        # Parse arguments safely
        args = []
        if argv_str:
            try:
                args = shlex.split(argv_str)
            except ValueError:
                # fallback: split on spaces
                args = argv_str.split()

        base = os.path.basename(filename)

        # Detect systemctl <verb> <unit>
        if base == "systemctl" or (args and os.path.basename(args[0]) == "systemctl"):
            verb = args[1] if len(args) > 1 else ""
            unit = args[2] if len(args) > 2 else ""

            if unit_matches_av(unit):
                self._record_detection(
                    "systemctl_av_unit",
                    {
                        "pid": int(pid),
                        "comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                        "filename": filename,
                        "argv": args,
                        "verb": verb,
                        "unit": unit,
                    },
                )
            else:
                # still useful to record generic systemctl use
                self._record_detection(
                    "systemctl_exec",
                    {
                        "pid": int(pid),
                        "comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                        "filename": filename,
                        "argv": args,
                    },
                )
        else:
            # Also flag direct execution of AV binaries
            if name_matches_av(filename) or path_matches_av(filename):
                self._record_detection(
                    "exec_av_binary",
                    {
                        "pid": int(pid),
                        "comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                        "filename": filename,
                        "argv": args,
                    },
                )

    def _handle_open_event(self, event):
        pid = event.pid
        filename = event.filename.decode("utf-8", errors="ignore").strip("\x00")
        if path_matches_av(filename):
            self.stats["open_av"] += 1
            self._record_detection(
                "open_av_path",
                {
                    "pid": int(pid),
                    "comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                    "path": filename,
                },
            )

    def _handle_unlink_event(self, event):
        pid = event.pid
        filename = event.filename.decode("utf-8", errors="ignore").strip("\x00")
        if path_matches_av(filename):
            self.stats["unlink_av"] += 1
            self._record_detection(
                "unlink_av_path",
                {
                    "pid": int(pid),
                    "comm": event.comm.decode("utf-8", errors="ignore").strip("\x00"),
                    "path": filename,
                },
            )

    # --- PUBLIC API ---

    def run(self, timeout_sec: int = 120):
        start = time.time()
        while True:
            if time.time() - start > timeout_sec:
                break

            if not self._pid_alive(self.sample_pid):
                break

            try:
                self.bpf.perf_buffer_poll(timeout=100)
            except KeyboardInterrupt:
                break

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                return False
        return True


# --------------------------------------------------------------------------------------
# 5. CONTROLLER: LAUNCH SAMPLE AND TRACE IT
# --------------------------------------------------------------------------------------

def run_sample_and_trace(sample_argv):
    proc = subprocess.Popen(
        sample_argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    sample_pid = proc.pid

    tracer = AVHunterTracer(sample_pid=sample_pid)
    tracer.run(timeout_sec=300)

    # Try to kill process group
    try:
        os.killpg(os.getpgid(sample_pid), signal.SIGKILL)
    except Exception:
        pass

    try:
        proc.wait(timeout=5)
    except Exception:
        pass

    return tracer.detections


def main():
    if os.geteuid() != 0:
        print("[!] This script must be run as root (for eBPF/BCC).", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 2:
        print(f"Usage: sudo {sys.argv[0]} /path/to/sample [args...]", file=sys.stderr)
        sys.exit(1)

    sample_argv = sys.argv[1:]
    print(f"[*] Launching sample: {' '.join(sample_argv)}")
    detections = run_sample_and_trace(sample_argv)

    report = {
        "sample": {
            "argv": sample_argv,
            "launched_at_utc": datetime.utcnow().isoformat() + "Z",
        },
        "detections": detections,
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
