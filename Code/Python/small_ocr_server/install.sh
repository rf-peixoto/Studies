#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# install.sh — Create a Python virtual-env and install all dependencies for the
#              OCR + Logo Detection server.
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Override the Python interpreter:
#   PYTHON=python3.11 ./install.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

VENV_DIR=".venv"
PYTHON=${PYTHON:-python3}

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[install]${NC} $*"; }
error() { echo -e "${RED}[install]${NC} $*" >&2; }

# ── 1. System dependencies (Tesseract + OpenCV prerequisites) ─────────────────
install_system_deps() {
    if command -v apt-get &>/dev/null; then
        info "Detected Debian/Ubuntu — installing system packages via apt…"
        sudo apt-get update -qq
        sudo apt-get install -y \
            tesseract-ocr tesseract-ocr-eng tesseract-ocr-por \
            libgl1 libglib2.0-0          # required by opencv-python-headless
    elif command -v brew &>/dev/null; then
        info "Detected macOS — installing via Homebrew…"
        brew install tesseract
        # OpenCV system libs are bundled in the Python wheel on macOS
    elif command -v dnf &>/dev/null; then
        info "Detected Fedora/RHEL — installing via dnf…"
        sudo dnf install -y tesseract mesa-libGL
    elif command -v pacman &>/dev/null; then
        info "Detected Arch Linux — installing via pacman…"
        sudo pacman -Sy --noconfirm tesseract tesseract-data-eng
    else
        warn "Unknown package manager — skipping system packages."
        warn "Please install manually:"
        warn "  • Tesseract OCR  → https://github.com/tesseract-ocr/tesseract"
        warn "  • libgl1 / mesa  (needed by OpenCV on Linux)"
    fi
}

if command -v tesseract &>/dev/null; then
    info "Tesseract already installed: $(tesseract --version 2>&1 | head -1)"
else
    install_system_deps
fi

# ── 2. Verify Python ───────────────────────────────────────────────────────────
if ! command -v "$PYTHON" &>/dev/null; then
    error "Python interpreter '$PYTHON' not found. Install Python 3.9+ and retry."
    exit 1
fi

PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Using Python $PY_VER ($($PYTHON -c 'import sys; print(sys.executable)'))"

MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ "$MAJOR" -lt 3 ]] || { [[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 9 ]]; }; then
    error "Python 3.9+ is required (found $PY_VER)."
    exit 1
fi

# ── 3. Create virtual environment ─────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment '$VENV_DIR' already exists — skipping creation."
else
    info "Creating virtual environment in '$VENV_DIR'…"
    "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtual environment activated."

# ── 4. Install Python packages ─────────────────────────────────────────────────
info "Upgrading pip…"
pip install --quiet --upgrade pip

info "Installing Python dependencies…"
pip install \
    "fastapi>=0.111.0"           \
    "uvicorn[standard]>=0.29.0"  \
    "python-multipart>=0.0.9"    \
    "pytesseract>=0.3.10"        \
    "Pillow>=10.3.0"             \
    "opencv-python-headless>=4.9.0.80" \
    "numpy>=1.26.0"

# Create the logo storage directory
mkdir -p logo_store

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✔ Installation complete!${NC}"
echo ""
echo "  Dependencies installed:"
echo "    • FastAPI + Uvicorn  — REST API server"
echo "    • pytesseract        — OCR (text extraction)"
echo "    • Pillow             — image I/O for OCR"
echo "    • opencv-headless    — feature matching for logo detection"
echo "    • numpy              — array operations"
echo ""
echo "  Next step → start the server:"
echo "    ./start.sh"
echo ""
