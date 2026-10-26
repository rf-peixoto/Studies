"""Interactive syscall gate ("supervise" mode).

Runs the target under ptrace and stops at every *interesting* system call BEFORE
the kernel executes it, showing you what the program is about to do. You decide:

    allow it, drop it (the kernel never executes it; a chosen errno is returned
    to the program), or set a standing policy for that syscall class.

This is the "run it like a debugger and veto suspicious actions" workflow. It
executes the target, so use it in a VM or disposable container.

Mechanism: at a syscall-entry stop we read the syscall number and arguments.
To DROP a call we overwrite the syscall-number register with -1 (an invalid
syscall); the kernel then skips it and, at syscall-exit, we set the return
register to the chosen -errno so the program sees a clean failure instead of a
crash. Uninteresting syscalls are auto-allowed so the program runs at speed.

Requires python-ptrace and a Linux x86-64 / aarch64 host.
"""
from __future__ import annotations

import errno
import os
from typing import Dict, List, Optional, Set

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


# Syscalls grouped by the behavior you most likely want to gate. Names are
# architecture-neutral (python-ptrace resolves numbers per arch).
INTERESTING: Dict[str, Set[str]] = {
    "network": {
        "socket", "connect", "bind", "listen", "accept", "accept4",
        "sendto", "sendmsg", "recvfrom", "recvmsg", "getpeername",
    },
    "exec": {"execve", "execveat"},
    "process": {"fork", "vfork", "clone", "clone3", "ptrace", "kill", "tgkill"},
    "file_write": {
        "open", "openat", "openat2", "unlink", "unlinkat", "rename",
        "renameat", "renameat2", "chmod", "fchmodat", "truncate",
        "mkdir", "mkdirat", "link", "symlink",
    },
    "memory": {"mprotect", "pkey_mprotect", "memfd_create"},
    "privilege": {"setuid", "setgid", "setreuid", "setresuid", "setsid",
                  "mount", "umount2", "chroot", "personality"},
}

# Which syscall classes carry a drop-friendly errno when vetoed.
_DROP_ERRNO = {
    "network": errno.EACCES,
    "exec": errno.EACCES,
    "process": errno.EPERM,
    "file_write": errno.EACCES,
    "memory": errno.EPERM,
    "privilege": errno.EPERM,
}

_SEVERITY = {
    "network": Severity.MEDIUM, "exec": Severity.HIGH, "process": Severity.MEDIUM,
    "file_write": Severity.LOW, "memory": Severity.MEDIUM, "privilege": Severity.HIGH,
}


def _classify(name: str) -> Optional[str]:
    for cls, names in INTERESTING.items():
        if name in names:
            return cls
    return None


class _Policy:
    """Remembers standing allow/drop decisions per syscall class and name."""

    def __init__(self, auto_allow_all: bool = False):
        self.allow_class: Set[str] = set()
        self.drop_class: Set[str] = set()
        self.allow_name: Set[str] = set()
        self.drop_name: Set[str] = set()
        self.allow_everything = auto_allow_all

    def decide(self, cls: str, name: str) -> Optional[str]:
        """Return 'allow', 'drop', or None if we must ask the user."""
        if self.allow_everything:
            return "allow"
        if name in self.drop_name or cls in self.drop_class:
            return "drop"
        if name in self.allow_name or cls in self.allow_class:
            return "allow"
        return None


def _prompt(cls: str, name: str, display: str, policy: _Policy) -> str:
    """Ask the user what to do with one syscall. Returns 'allow' or 'drop'."""
    print(f"\n  \033[1m[{cls.upper()}]\033[0m {display}")
    print("    [a]llow  [d]rop  [A]llow-all-this-class  [D]rop-all-this-class")
    print("    [g]allow-all-remaining  [q]uit(kill target)")
    while True:
        try:
            choice = input("    > ").strip()
        except EOFError:
            choice = "a"
        if choice == "a":
            return "allow"
        if choice == "d":
            return "drop"
        if choice == "A":
            policy.allow_class.add(cls)
            return "allow"
        if choice == "D":
            policy.drop_class.add(cls)
            return "drop"
        if choice == "g":
            policy.allow_everything = True
            return "allow"
        if choice == "q":
            raise KeyboardInterrupt
        print("    (a/d/A/D/g/q)")


# Registers that hold the syscall number, per architecture.
_SYSCALL_NR_REG = {"x86_64": "orig_rax", "aarch64": "x8"}
_RET_REG = {"x86_64": "rax", "aarch64": "x0"}


def supervise(path: str, args: List[str], outdir: str,
              auto_allow_all: bool = False,
              log_all: bool = True) -> StageResult:
    """Run `path` under the interactive syscall gate."""
    res = StageResult("supervise")
    if not HAVE_PTRACE:
        res.error = ("python-ptrace not installed; run install.sh "
                     "(pip install python-ptrace).")
        return res
    if not os.path.exists(path):
        res.error = f"target not found: {path}"
        return res

    os.chmod(path, os.stat(path).st_mode | 0o111)  # ensure executable bit

    policy = _Policy(auto_allow_all=auto_allow_all)
    dropped: List[dict] = []
    allowed_classes: Dict[str, int] = {}
    pending_drop: Dict[int, str] = {}  # pid -> class awaiting errno at exit
    logf = open(os.path.join(outdir, "supervise.log"), "w") if log_all else None

    print("\n" + "=" * 70)
    print("SYSCALL GATE — stopping before each interesting syscall.")
    print("This EXECUTES the target. Ctrl-C or 'q' kills it.")
    print("=" * 70)

    debugger = PtraceDebugger()
    try:
        debugger.traceFork()
        debugger.traceExec()
    except Exception:
        pass  # not all builds support these; continue single-process

    try:
        pid = createChild([path, *args], no_stdout=False, env=None)
    except Exception as exc:  # noqa: BLE001 - surface any spawn failure
        res.error = f"could not spawn target: {exc}"
        if logf:
            logf.close()
        return res

    process = debugger.addProcess(pid, is_attached=True)
    arch = getattr(process, "getBasicArchitecture", lambda: "x86_64")() \
        if hasattr(process, "getBasicArchitecture") else "x86_64"
    nr_reg = _SYSCALL_NR_REG.get(arch, "orig_rax")
    ret_reg = _RET_REG.get(arch, "rax")

    call_opts = FunctionCallOptions(write_types=False, write_argname=True)
    process.syscall()

    try:
        while True:
            try:
                debugger.waitSyscall()
            except ProcessExit:
                break
            except ProcessSignal as event:
                event.process.syscall(event.signum)
                continue
            except NewProcessEvent as event:
                event.process.syscall()
                continue
            except ProcessExecution as event:
                event.process.syscall()
                continue
            except KeyError:
                # process left the debugger set
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

            entering = syscall.result is None
            cls = _classify(syscall.name)

            if entering and cls is not None:
                display = _format_syscall(syscall)
                if logf:
                    logf.write(f"ENTER {display}\n")
                decision = policy.decide(cls, syscall.name)
                if decision is None:
                    try:
                        decision = _prompt(cls, syscall.name, display, policy)
                    except KeyboardInterrupt:
                        print("\n  Quitting; killing target.")
                        break

                if decision == "drop":
                    # Neutralize: set syscall number to -1 so kernel skips it.
                    try:
                        proc.setreg(nr_reg, (1 << 64) - 1)
                        pending_drop[proc.pid] = cls
                        dropped.append({"syscall": syscall.name, "class": cls,
                                        "call": display})
                        print(f"    -> DROPPED {syscall.name}")
                        if logf:
                            logf.write(f"DROP  {display}\n")
                    except Exception as exc:  # noqa: BLE001
                        print(f"    (could not drop: {exc}; allowing)")
                else:
                    allowed_classes[cls] = allowed_classes.get(cls, 0) + 1

            elif (not entering) and proc.pid in pending_drop:
                # Syscall-exit of a dropped call: set a clean errno return.
                cls = pending_drop.pop(proc.pid)
                err = _DROP_ERRNO.get(cls, errno.EPERM)
                try:
                    proc.setreg(ret_reg, (1 << 64) - err)  # -errno
                except Exception:
                    pass

            proc.syscall()
    finally:
        try:
            debugger.quit()
        except Exception:
            pass
        if logf:
            logf.close()

    # Findings / data.
    res.data = {
        "dropped_calls": dropped,
        "dropped_count": len(dropped),
        "allowed_class_counts": allowed_classes,
        "log": os.path.join(outdir, "supervise.log") if log_all else None,
    }
    for cls, n in allowed_classes.items():
        res.add(_SEVERITY.get(cls, Severity.LOW), "supervise",
                f"Allowed {n} {cls} syscall(s)",
                "Observed during supervised run.")
    if dropped:
        res.add(Severity.INFO, "supervise",
                f"You dropped {len(dropped)} syscall(s)",
                ", ".join(sorted({d['syscall'] for d in dropped})))
    return res


def _format_syscall(syscall) -> str:
    """Build a readable 'name(args)' line from a PtraceSyscall."""
    try:
        parts = []
        for arg in syscall.arguments:
            try:
                parts.append(arg.format())
            except Exception:
                parts.append(hex(arg.value) if hasattr(arg, "value") else "?")
        return f"{syscall.name}({', '.join(parts)})"
    except Exception:
        return f"{syscall.name}(...)"
