#!/usr/bin/env bash
# install.sh - Creates a Python virtual environment and installs Python dependencies.
# External Go tools are checked, not installed automatically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[*] Setting up Python virtual environment in $VENV_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[-] $PYTHON_BIN not found. Please install Python 3.9 or newer."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo "[+] Virtual environment created."
else
    echo "[*] Virtual environment already exists."
fi

source "$VENV_DIR/bin/activate"

echo "[*] Upgrading pip..."
python -m pip install --upgrade pip

echo "[*] Installing required Python packages..."
python -m pip install aiohttp aiodns ipwhois

echo "[*] Checking for external binaries..."
OPTIONAL_MISSING=()
REQUIRED_FOR_FULL_SCAN=(assetfinder subfinder httpx nuclei)

for bin in "${REQUIRED_FOR_FULL_SCAN[@]}"; do
    if [ -x "$SCRIPT_DIR/$bin" ]; then
        echo "[+] $bin found locally: $SCRIPT_DIR/$bin"
    elif command -v "$bin" >/dev/null 2>&1; then
        echo "[+] $bin found in PATH: $(command -v "$bin")"
    else
        OPTIONAL_MISSING+=("$bin")
    fi
done

if [ ${#OPTIONAL_MISSING[@]} -ne 0 ]; then
    echo "[!] Missing optional external tools:"
    printf '    - %s\n' "${OPTIONAL_MISSING[@]}"
    echo "    The scanner still runs, but missing stages will be skipped or degraded."
    echo "    Suggested Go installs:"
    echo "      go install github.com/tomnomnom/assetfinder@latest"
    echo "      go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    echo "      go install github.com/projectdiscovery/httpx/cmd/httpx@latest"
    echo "      go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
fi

echo "[✓] Installation complete. Run: ./scan.sh domains.txt"
