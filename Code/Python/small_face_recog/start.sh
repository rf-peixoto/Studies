#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Error: virtual environment not found. Run ./install.sh first."
    exit 1
fi

echo "── Activating virtual environment ──"
source "$VENV_DIR/bin/activate"

echo "── Starting Face Recognition API ──"
uvicorn face_recognition_server:app --host 0.0.0.0 --port 8000 --reload
