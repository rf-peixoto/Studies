#!/bin/bash
# secure_chat_v2.sh: Real-time encrypted chat with netcat
# Usage: 
#   Server: ./secure_chat.sh server <PORT> <PASSWORD>
#   Client: ./secure_chat.sh client <SERVER_IP> <PORT> <PASSWORD>

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

# Create FIFOs (temporary pipes)
IN_FIFO=$(mktemp -u)
OUT_FIFO=$(mktemp -u)
mkfifo "$IN_FIFO" "$OUT_FIFO"
trap 'rm -f "$IN_FIFO" "$OUT_FIFO"; kill $(jobs -p) 2>/dev/null' EXIT

# Encryption/Decryption functions
encrypt() {
  openssl enc -aes-256-cbc -base64 -pass "pass:$PASSWORD" -pbkdf2
}

decrypt() {
  openssl enc -d -aes-256-cbc -base64 -pass "pass:$PASSWORD" -pbkdf2
}

# Start chat connection
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
NC_PID=$!

# Real-time message receiver
(
  while read -r line <"$OUT_FIFO"; do
    # Decrypt and display incoming messages
    decrypted=$(echo "$line" | decrypt 2>/dev/null)
    if [ $? -eq 0 ]; then
      printf "\n\033[1;34m[Friend]\033[0m %s\n" "$decrypted"
    else
      printf "\n\033[1;31m[Error] Bad message received\033[0m\n"
    fi
    # Show input prompt again
    echo -n "You: "
  done
) &

# Terminal setup for clean input
stty -echoctl
clear
echo -e "\033[1;32mSecure Chat Started\033[0m (CTRL+C to exit)"
echo -e "Encryption: \033[1;33mAES-256\033[0m"
echo "----------------------------------------"

# Message input handler
while true; do
  echo -n "You: "
  read -r msg
  # Exit condition
  if [[ -z "$msg" ]]; then continue; fi
  if [[ "$msg" == "/quit" ]]; then exit; fi
  
  # Encrypt and send message
  echo "$msg" | encrypt > "$IN_FIFO"
  
  # Clear previous input and show local echo
  tput cuu1
  tput el
  printf "\033[1;32mYou:\033[0m %s\n" "$msg"
done
