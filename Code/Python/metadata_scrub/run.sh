#!/usr/bin/env bash
# Start scrub. Creates a virtual environment on first run so that pip does not
# collide with a system-managed Python (the "externally-managed-environment"
# error on Debian, Ubuntu and Homebrew).
#
# If this file will not execute, its permission bit was lost in transit:
#     chmod +x run.sh      or just:      bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
VENV=${SCRUB_VENV:-.venv}

if [ ! -d "$VENV" ]; then
  echo "  creating virtual environment in $VENV ..."
  "$PY" -m venv "$VENV" || {
    echo "  could not create a venv. On Debian/Ubuntu: sudo apt install python3-venv" >&2
    exit 1
  }
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# PyAV is a ~35 MB wheel, so the first install is not instant. Show progress
# rather than sitting silently behind -q.
if ! python -c "import flask, av, pikepdf, PIL" 2>/dev/null; then
  echo "  installing dependencies (this takes a minute the first time) ..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

exec python app.py "$@"
