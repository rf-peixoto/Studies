#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

echo "── Creating virtual environment in ./${VENV_DIR} ──"
python3 -m venv "$VENV_DIR"

echo "── Upgrading pip ──"
"$VENV_DIR/bin/pip" install --upgrade pip

echo "── Installing dependencies ──"
"$VENV_DIR/bin/pip" install \
    face_recognition \
    fastapi \
    uvicorn[standard]
"$VENV_DIR/bin/pip" install git+https://github.com/ageitgey/face_recognition_models

echo ""
echo "✓ Done. Run ./start.sh to start the server."
