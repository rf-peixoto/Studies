#!/usr/bin/env bash
# scan.sh - Activates the virtual environment and runs scan.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SCANNER_SCRIPT="$SCRIPT_DIR/scan.py"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <domains_list.txt> [scanner options]"
    echo "Example: $0 domains.txt --skip-nuclei"
    exit 1
fi

DOMAINS_FILE="$1"
shift

if [ ! -f "$DOMAINS_FILE" ]; then
    echo "[-] Domains file not found: $DOMAINS_FILE"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[-] Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

if [ ! -f "$SCANNER_SCRIPT" ]; then
    echo "[-] Scanner script not found: $SCANNER_SCRIPT"
    exit 1
fi

source "$VENV_DIR/bin/activate"

echo "[*] Starting own-domain scan using: $DOMAINS_FILE"
python3 "$SCANNER_SCRIPT" "$DOMAINS_FILE" "$@"
