#!/usr/bin/env bash

set -e

VENV_DIR=".venv"

echo "[*] Preparing environment..."

if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "[*] Virtual environment already exists."
fi

echo "[*] Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "[*] Upgrading pip..."
pip install --upgrade pip

echo "[*] Installing dependencies..."
pip install python-telegram-bot==21.6

echo "[*] Environment ready."
echo ""
echo "Next step:"
echo "export TELEGRAM_BOT_TOKEN=\"YOUR_TOKEN\""
echo "./run.sh"
