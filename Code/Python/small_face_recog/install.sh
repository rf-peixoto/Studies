#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

# ── Find a compatible Python version (3.11 or 3.12 preferred) ─────────────────
PYTHON=""
for candidate in python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3.10, 3.11, or 3.12 is required but none were found."
    echo "face_recognition is not compatible with Python 3.13+."
    echo "Install one with: sudo apt install python3.12  (or python3.11)"
    exit 1
fi

echo "── Using $($PYTHON --version) ──"

echo "── Creating virtual environment in ./${VENV_DIR} ──"
"$PYTHON" -m venv "$VENV_DIR"

echo "── Upgrading pip ──"
"$VENV_DIR/bin/pip" install --upgrade pip

echo "── Installing face_recognition_models (from git) ──"
"$VENV_DIR/bin/pip" install git+https://github.com/ageitgey/face_recognition_models

echo "── Installing remaining dependencies ──"
"$VENV_DIR/bin/pip" install \
    face_recognition \
    fastapi \
    uvicorn[standard]

echo "── Verifying face_recognition import ──"
"$VENV_DIR/bin/python" -c "import face_recognition; print('✓ face_recognition imported successfully.')"

echo ""
echo "✓ Done. Run ./start.sh to start the server."
