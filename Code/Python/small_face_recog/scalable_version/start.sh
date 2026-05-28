#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Error: virtual environment not found. Run ./install.sh first."
    exit 1
fi

# ── Check Qdrant is up ─────────────────────────────────────────────────────────
echo "── Checking Qdrant ──"
if ! curl -sf http://localhost:6333/healthz > /dev/null; then
    echo "Error: Qdrant is not running."
    echo "Start it with: docker compose up -d"
    exit 1
fi
echo "✓ Qdrant is up."

echo "── Activating virtual environment ──"
source "$VENV_DIR/bin/activate"

echo "── Starting Face Recognition API ──"
uvicorn face_recognition_server:app --host 0.0.0.0 --port 8000 --reload
