#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

# ── Check Docker ───────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "Error: Docker is required but not installed."
    echo "Install it from https://docs.docker.com/engine/install/"
    exit 1
fi

# ── Python venv ────────────────────────────────────────────────────────────────
echo "── Creating virtual environment in ./${VENV_DIR} ──"
python3 -m venv "$VENV_DIR"

echo "── Upgrading pip ──"
"$VENV_DIR/bin/pip" install --upgrade pip

echo "── Installing dependencies ──"
"$VENV_DIR/bin/pip" install \
    insightface \
    onnxruntime \
    opencv-python-headless \
    numpy \
    qdrant-client \
    fastapi \
    uvicorn[standard]

echo "── Verifying imports ──"
"$VENV_DIR/bin/python" -c "
from insightface.app import FaceAnalysis
from qdrant_client import QdrantClient
print('✓ All imports OK.')
"

echo ""
echo "✓ Done."
echo ""
echo "Next steps:"
echo "  1. Start Qdrant :  docker compose up -d"
echo "  2. Start server :  ./start.sh"
