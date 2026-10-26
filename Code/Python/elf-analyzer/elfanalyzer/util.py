"""Shared helpers: colored output, findings model, safe command runner."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Color handling                                                              #
# --------------------------------------------------------------------------- #
class _Color:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def red(self, t):     return self._wrap("31", t)
    def green(self, t):   return self._wrap("32", t)
    def yellow(self, t):  return self._wrap("33", t)
    def blue(self, t):    return self._wrap("34", t)
    def magenta(self, t): return self._wrap("35", t)
    def cyan(self, t):    return self._wrap("36", t)
    def bold(self, t):    return self._wrap("1", t)
    def dim(self, t):     return self._wrap("2", t)


def make_color(force: Optional[bool] = None) -> _Color:
    if force is not None:
        return _Color(force)
    enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    return _Color(enabled)


# --------------------------------------------------------------------------- #
# Findings                                                                     #
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Weight each severity contributes to the suspicion score.
SEVERITY_WEIGHT = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 3,
    Severity.HIGH: 6,
}


@dataclass
class Finding:
    """A single notable observation from any stage."""

    category: str           # e.g. "entropy", "imports", "anomaly"
    severity: Severity
    title: str
    detail: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class StageResult:
    """Output of one analysis stage: structured data + findings."""

    name: str
    data: dict = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None

    def add(self, severity: Severity, category: str, title: str, detail: str = ""):
        self.findings.append(Finding(category, severity, title, detail))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "data": self.data,
            "findings": [f.to_dict() for f in self.findings],
            "error": self.error,
        }


# --------------------------------------------------------------------------- #
# Subprocess helper                                                            #
# --------------------------------------------------------------------------- #
def run_tool(
    argv: List[str],
    timeout: int = 60,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """Run a tool capturing output. Never raises on non-zero exit.

    Returns a CompletedProcess; on timeout/other OSError the returncode is set
    to a sentinel and stderr carries the message.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(argv, 124, exc.stdout or "", "timeout")
    except (OSError, ValueError) as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num}B"
