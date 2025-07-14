#!/bin/bash
# secure_chat.sh: Simple encrypted chat via netcat
# Usage: 
#   Server: ./secure_chat.sh server <PORT> <PASSWORD>
# ./secure_chat.sh server 4444 mySecretPassword
#   Client: ./secure_chat.sh client <SERVER_IP> <PORT> <PASSWORD>
# ./secure_chat.sh client 192.168.1.100 4444 mySecretPassword

set -e

# Check arguments
if [[ $# -lt 3 ]]; then
  echo "Usage:"
  echo "  Server: $0 server <PORT> <PASSWORD>"
  echo "  Client: $0 client <SERVER_IP> <PORT> <PASSWORD>"
  exit 1
fi

MODE=$1
PASSWORD=${@: -1} # Last argument

# Generate FIFOs (temporary pipes)
IN_FIFO=$(mktemp -u)
OUT_FIFO=$(mktemp -u)
mkfifo "$IN_FIFO" "$OUT_FIFO"
trap 'rm -f "$IN_FIFO" "$OUT_FIFO"' EXIT

# Encryption/Decryption functions
encrypt() {
  openssl enc -aes-256-cbc -base64 -pass "pass:$PASSWORD" -pbkdf2
}

decrypt() {
  openssl enc -d -aes-256-cbc -base64 -pass "pass:$PASSWORD" -pbkdf2
}

# Start chat
if [[ "$MODE" == "server" ]]; then
  PORT=$2
  echo "[*] Server running on port $PORT. Waiting for connection..."
  nc -l -p "$PORT" > "$OUT_FIFO" < "$IN_FIFO" &
else
  IP=$2
  PORT=$3
  echo "[*] Connecting to $IP:$PORT..."
  nc "$IP" "$PORT" > "$OUT_FIFO" < "$IN_FIFO" &
fi

# Background: Receive and decrypt messages
( while true; do
    if read -r line <"$OUT_FIFO"; then
      echo -e "\n[Anon] $(echo "$line" | decrypt)"
    fi
  done
) &

# Foreground: Encrypt and send user input
echo "Type your message (CTRL+C to exit):"
while IFS= read -r msg; do
  echo "[Me] $msg"  # Show local echo
  echo "$msg" | encrypt > "$IN_FIFO"
done
