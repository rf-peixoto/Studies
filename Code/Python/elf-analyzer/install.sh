#!/usr/bin/env bash
#
# install.sh - create a local virtualenv and install Python dependencies.
#
# This only sets up the Python side. The framework also uses external CLI
# tools (readelf, objdump, strace, gdb, ...). Those are detected at runtime;
# run `./start.sh --check-tools` to see what is present and get an apt command
# for whatever is missing (Debian trixie).
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HERE}/.venv"
PYTHON="${PYTHON:-python3}"

echo ">> Using interpreter: $("${PYTHON}" --version 2>&1)"

if [ ! -d "${VENV}" ]; then
    echo ">> Creating virtualenv at ${VENV}"
    "${PYTHON}" -m venv "${VENV}"
else
    echo ">> Reusing existing virtualenv at ${VENV}"
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo ">> Upgrading pip"
python -m pip install --upgrade pip >/dev/null

echo ">> Installing Python requirements"
python -m pip install -r "${HERE}/requirements.txt"

echo
echo ">> Python environment ready."
echo ">> Next: run ./start.sh --check-tools to verify external analysis tools."
echo ">>       then: ./start.sh /path/to/elf"
