#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

if [ -d "$VENV_DIR" ]; then
    echo "── Removing existing virtual environment ──"
    rm -rf "$VENV_DIR"
fi

echo "── Creating virtual environment in ./${VENV_DIR} ──"
python3 -m venv "$VENV_DIR"

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
