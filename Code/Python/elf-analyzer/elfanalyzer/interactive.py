"""Interactive debugging launcher (gdb).

Opens gdb on the target with a few sensible defaults (Intel syntax, pagination
off, a breakpoint at the entry point). If pwndbg or GEF is installed in the
user's gdbinit it will load as usual. This hands over the terminal to gdb; it
executes the target only when you tell gdb to `run`.
"""
from __future__ import annotations

import os
import subprocess
from typing import List

from .tools import ToolStatus
from .util import StageResult


_GDB_PRELUDE = """\
set pagination off
set disassembly-flavor intel
set disable-randomization on
echo \\n== elf-analyzer gdb session ==\\n
echo Target loaded. A breakpoint is set at the entry point.\\n
echo Use 'run' to start, 'info functions' to list symbols.\\n
"""


def launch_gdb(path: str, args: List[str], tools: ToolStatus,
               outdir: str) -> StageResult:
    res = StageResult("gdb")
    if not tools.has("gdb"):
        res.error = "gdb not installed"
        return res

    script = os.path.join(outdir, "gdbinit.local")
    with open(script, "w") as fh:
        fh.write(_GDB_PRELUDE)
        # Break at the program's _start. For stripped binaries where _start is
        # not a named symbol, 'starti' (run and stop at the very first insn) is
        # the manual fallback; we note it in the prelude text above.
        fh.write("break _start\n")

    argv = [tools.path("gdb"), "-q", "-x", script, "--args", path, *args]
    print(f"\nLaunching gdb on {path} (type 'quit' to leave)...")
    try:
        subprocess.run(argv, check=False)
        res.data = {"launched": True, "gdbinit": script}
    except OSError as exc:
        res.error = f"could not launch gdb: {exc}"
    return res
