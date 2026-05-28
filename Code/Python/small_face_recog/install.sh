#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="venv"

echo "── Creating virtual environment in ./${VENV_DIR} ──"
python3 -m venv "$VENV_DIR"

echo "── Upgrading pip ──"
"$VENV_DIR/bin/pip" install --upgrade pip

echo "── Installing dependencies ──"
"$VENV_DIR/bin/pip" install \
    insightface \
    onnxruntime \
    python-multipart \
    opencv-python-headless \
    numpy \
    fastapi \
    uvicorn[standard]

echo "── Verifying insightface import ──"
"$VENV_DIR/bin/python" -c "from insightface.app import FaceAnalysis; print('✓ insightface imported successfully.')"

echo ""
echo "✓ Done. Run ./start.sh to start the server."
echo "Note: InsightFace will download its models (~300 MB) on first start."
