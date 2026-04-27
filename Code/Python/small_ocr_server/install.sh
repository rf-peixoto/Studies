#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# install.sh — Create a Python virtual-env and install all OCR-server deps.
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

VENV_DIR=".venv"
PYTHON=${PYTHON:-python3}          # override with: PYTHON=python3.11 ./install.sh

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()    { echo -e "${GREEN}[install]${NC} $*"; }
warn()    { echo -e "${YELLOW}[install]${NC} $*"; }
error()   { echo -e "${RED}[install]${NC} $*" >&2; }

# ── 1. Detect OS and install system dependencies ───────────────────────────────
install_system_deps() {
    if command -v apt-get &>/dev/null; then
        info "Detected Debian/Ubuntu — installing Tesseract via apt…"
        sudo apt-get update -qq
        sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-por
    elif command -v brew &>/dev/null; then
        info "Detected macOS — installing Tesseract via Homebrew…"
        brew install tesseract
    elif command -v dnf &>/dev/null; then
        info "Detected Fedora/RHEL — installing Tesseract via dnf…"
        sudo dnf install -y tesseract
    elif command -v pacman &>/dev/null; then
        info "Detected Arch Linux — installing Tesseract via pacman…"
        sudo pacman -Sy --noconfirm tesseract tesseract-data-eng
    else
        warn "Could not detect package manager."
        warn "Please install Tesseract OCR manually: https://github.com/tesseract-ocr/tesseract"
    fi
}

# Check if tesseract is already installed
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

PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Using Python $PYTHON_VERSION ($($PYTHON -c 'import sys; print(sys.executable)'))"

MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [[ "$MAJOR" -lt 3 ]] || { [[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 9 ]]; }; then
    error "Python 3.9+ is required (found $PYTHON_VERSION)."
    exit 1
fi

# ── 3. Create virtual environment ─────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment '$VENV_DIR' already exists — skipping creation."
else
    info "Creating virtual environment in '$VENV_DIR'…"
    "$PYTHON" -m venv "$VENV_DIR"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtual environment activated."

# ── 4. Upgrade pip & install Python packages ──────────────────────────────────
info "Upgrading pip…"
pip install --quiet --upgrade pip

info "Installing Python dependencies…"
pip install \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "python-multipart>=0.0.9" \
    "pytesseract>=0.3.10" \
    "Pillow>=10.3.0"

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✔ Installation complete!${NC}"
echo ""
echo "  Next step → run the server:"
echo "    ./start.sh"
echo ""
