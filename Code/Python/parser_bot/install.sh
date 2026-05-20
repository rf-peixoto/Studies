#!/usr/bin/env bash
set -euo pipefail

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[OK] Installed dependencies."
echo "For RAR support, install system dependency:"
echo "  Fedora: sudo dnf install unrar p7zip p7zip-plugins"
echo "  Debian/Ubuntu: sudo apt install unrar p7zip-full"