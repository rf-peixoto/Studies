"""External CLI tool detection and (optional) installation.

Each analysis stage declares which command-line tools it would like. We detect
what is present on PATH, let stages skip gracefully when something is missing,
and -- on request -- offer a single apt-get command for Debian trixie.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Tool:
    """A command-line tool the framework may use."""

    command: str          # executable name looked up on PATH
    package: str          # Debian trixie apt package that provides it
    purpose: str          # short human description
    runs_target: bool = False  # True if using it executes the analyzed binary


# Central registry. `runs_target=True` marks tools that EXECUTE the sample --
# those are only ever invoked from dynamic stages, never from static analysis.
REGISTRY: Dict[str, Tool] = {
    "file":     Tool("file", "file", "file type identification"),
    "readelf":  Tool("readelf", "binutils", "ELF header / sections / dynamic info"),
    "objdump":  Tool("objdump", "binutils", "disassembly and headers"),
    "nm":       Tool("nm", "binutils", "symbol listing"),
    "strings":  Tool("strings", "binutils", "printable string extraction"),
    "upx":      Tool("upx", "upx-ucl", "detect / unpack UPX-packed binaries"),
    "binwalk":  Tool("binwalk", "binwalk", "find embedded files / signatures"),
    # Tools below run the target; dynamic/interactive stages only.
    "ldd":      Tool("ldd", "libc-bin", "resolve shared library deps", runs_target=True),
    "strace":   Tool("strace", "strace", "trace system calls", runs_target=True),
    "ltrace":   Tool("ltrace", "ltrace", "trace library calls", runs_target=True),
    "tcpdump":  Tool("tcpdump", "tcpdump", "capture network traffic", runs_target=True),
    "gdb":      Tool("gdb", "gdb", "interactive debugger", runs_target=True),
}


@dataclass
class ToolStatus:
    present: Dict[str, Optional[str]] = field(default_factory=dict)  # name -> path|None

    def has(self, name: str) -> bool:
        return bool(self.present.get(name))

    def path(self, name: str) -> Optional[str]:
        return self.present.get(name)

    def missing(self, names: Optional[Iterable[str]] = None) -> List[str]:
        names = list(names) if names is not None else list(REGISTRY)
        return [n for n in names if not self.has(n)]


def detect(names: Optional[Iterable[str]] = None) -> ToolStatus:
    """Return availability for the requested tools (default: all)."""
    names = list(names) if names is not None else list(REGISTRY)
    status = ToolStatus()
    for name in names:
        tool = REGISTRY.get(name)
        cmd = tool.command if tool else name
        status.present[name] = shutil.which(cmd)
    return status


def apt_command(missing: Iterable[str]) -> Optional[str]:
    """Build an apt-get command installing packages for the missing tools."""
    packages = sorted({REGISTRY[n].package for n in missing if n in REGISTRY})
    if not packages:
        return None
    return "sudo apt-get install -y " + " ".join(packages)


def report_tools(status: ToolStatus) -> str:
    """Human-readable availability table."""
    lines = ["External tool availability:"]
    for name, tool in REGISTRY.items():
        mark = "ok " if status.has(name) else "-- "
        tag = " (executes target)" if tool.runs_target else ""
        where = status.path(name) or f"missing -> apt package '{tool.package}'"
        lines.append(f"  [{mark}] {name:9s} {where}{tag}")
        lines.append(f"            {tool.purpose}")
    missing = status.missing()
    cmd = apt_command(missing)
    if cmd:
        lines.append("")
        lines.append("Install everything missing with:")
        lines.append(f"  {cmd}")
    return "\n".join(lines)


def offer_install(missing: Iterable[str], assume_yes: bool = False) -> bool:
    """Offer to apt-install missing tools. Returns True if an install ran.

    Never auto-runs without consent unless assume_yes is set (``--install-deps``).
    """
    missing = [m for m in missing if m in REGISTRY]
    cmd = apt_command(missing)
    if not cmd:
        return False

    print(f"\nMissing tools: {', '.join(sorted(missing))}")
    print(f"Suggested (Debian trixie): {cmd}")

    if not assume_yes:
        try:
            answer = input("Run this now with apt-get? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in {"y", "yes"}:
            print("Skipping install. Affected stages will be skipped or degraded.")
            return False

    packages = sorted({REGISTRY[n].package for n in missing})
    try:
        subprocess.run(["sudo", "apt-get", "update"], check=False)
        subprocess.run(["sudo", "apt-get", "install", "-y", *packages], check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Install failed: {exc}. Run manually:\n  {cmd}")
        return False
