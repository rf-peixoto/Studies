#!/usr/bin/env bash

set -e

VENV_DIR=".venv"
BOT_FILE="reminder_bot.py"

if [ ! -d "$VENV_DIR" ]; then
    echo "[!] Virtual environment not found."
    echo "Run ./start.sh first."
    exit 1
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "[!] TELEGRAM_BOT_TOKEN is not set."
    echo "Example:"
    echo "export TELEGRAM_BOT_TOKEN=\"your_token_here\""
    exit 1
fi

echo "[*] Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "[*] Starting bot..."
python "$BOT_FILE"
