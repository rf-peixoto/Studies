#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# start.sh — Activate the venv and start the OCR + Logo Detection server.
#
# Environment variables (all optional):
#   HOST      Bind address          (default: 0.0.0.0)
#   PORT      TCP port to listen on (default: 8000)
#   WORKERS   Number of workers     (default: 1)
#   LOG_LEVEL Uvicorn log level     (default: info)
#   RELOAD    Hot-reload flag       (default: false)
#
# Usage:
#   chmod +x start.sh && ./start.sh
#   PORT=9000 WORKERS=4 ./start.sh
#   RELOAD=true ./start.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

VENV_DIR=".venv"
APP_MODULE="ocr_server:app"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"
RELOAD="${RELOAD:-false}"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; CYAN="\033[0;36m"; NC="\033[0m"
info()  { echo -e "${GREEN}[start]${NC} $*"; }
warn()  { echo -e "${YELLOW}[start]${NC} $*"; }
error() { echo -e "${RED}[start]${NC} $*" >&2; }

[[ ! -d "$VENV_DIR" ]]     && { error "Run ./install.sh first."; exit 1; }
[[ ! -f "ocr_server.py" ]] && { error "ocr_server.py not found. Run from project root."; exit 1; }

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtual environment activated."

command -v tesseract &>/dev/null \
    || { error "Tesseract not found. Run ./install.sh."; exit 1; }
info "Tesseract: $(tesseract --version 2>&1 | head -1)"

mkdir -p logo_store

UVICORN_ARGS=(
    "$APP_MODULE"
    "--host"      "$HOST"
    "--port"      "$PORT"
    "--log-level" "$LOG_LEVEL"
)

if [[ "$RELOAD" == "true" ]]; then
    warn "Hot-reload enabled (development mode)."
    UVICORN_ARGS+=("--reload")
else
    UVICORN_ARGS+=("--workers" "$WORKERS")
fi

echo ""
echo -e "${CYAN}  ╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}  ║      OCR + Logo Detection  API  Server  v3       ║${NC}"
echo -e "${CYAN}  ╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}URL   ${NC}: http://${HOST}:${PORT}"
echo -e "  ${GREEN}Docs  ${NC}: http://${HOST}:${PORT}/docs"
echo ""
echo -e "  ── OCR ─────────────────────────────────────────────"
echo -e "  ${YELLOW}POST /ocr${NC}                  extract text (single)"
echo -e "  ${YELLOW}POST /ocr/batch${NC}            extract text (batch)"
echo ""
echo -e "  ── Logo Management ─────────────────────────────────"
echo -e "  ${YELLOW}POST   /logos/register${NC}     upload + cache ORB & SIFT"
echo -e "  ${YELLOW}GET    /logos${NC}              list registered logos"
echo -e "  ${YELLOW}DELETE /logos/{id}${NC}         remove logo + caches"
echo ""
echo -e "  ── Logo Detection ──────────────────────────────────"
echo -e "  ${YELLOW}POST /logos/detect/orb${NC}     fast  — binary features"
echo -e "  ${YELLOW}POST /logos/detect/sift${NC}    accurate — float features"
echo ""
echo -e "  ${YELLOW}GET  /health${NC}               health check"
echo ""

exec uvicorn "${UVICORN_ARGS[@]}"
