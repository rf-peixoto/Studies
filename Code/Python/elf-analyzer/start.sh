#!/usr/bin/env bash
#
# start.sh - entry point. Activates the venv (creating it if needed) and runs
# the analyzer, passing all arguments straight through.
#
#   ./start.sh /path/to/elf                 # static analysis (default)
#   ./start.sh /path/to/elf --mitigations   # add checksec-style mitigations
#   ./start.sh /path/to/elf --dynamic        # strace/ltrace/tcpdump capture
#   ./start.sh /path/to/elf --supervise      # interactive syscall gate
#   ./start.sh /path/to/elf --gdb            # drop into gdb
#   ./start.sh /path/to/elf --all            # everything (interactive)
#   ./start.sh --check-tools                 # report tool availability
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HERE}/.venv"

if [ ! -d "${VENV}" ]; then
    echo ">> No virtualenv found. Running install.sh first..." >&2
    "${HERE}/install.sh"
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

# Run as a module so relative imports work. PYTHONPATH points at the package
# root so the analyzer can be launched from any working directory while still
# receiving file paths relative to the caller's cwd.
export PYTHONPATH="${HERE}:${PYTHONPATH:-}"
exec python -m elfanalyzer "$@"
