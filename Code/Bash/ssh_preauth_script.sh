/etc/ssh/sshrc
 Commands in this file are executed by ssh when the user
 logs in, just before the user\'s shell (or command) is
 started. See the sshd(8) manual page for more
 information.

ref: https://www.linkedin.com/posts/luciano-marcos_se-tem-algo-que-eu-gosto-%C3%A9-seguran%C3%A7a-da-informa%C3%A7%C3%A3o-activity-7317211747042353154-zH-3

# Script:
#!/bin/bash

# Extract relevant session data
DATE=$(date "+%Y-%m-%d %H:%M:%S %Z")
USER_NAME="$USER"
REMOTE_INFO=($SSH_CLIENT)
IP_ADDRESS="${REMOTE_INFO[0]}"
PORT="${REMOTE_INFO[1]}"
TTY="$SSH_TTY"
CMD="${SSH_ORIGINAL_COMMAND:-Interactive shell}"
HOSTNAME=$(hostname)

# Telegram configuration
BOT_TOKEN="YOUR_BOT_TOKEN"
CHAT_ID="YOUR_CHAT_ID"

# Construct human-readable message
MESSAGE="🚨 New SSH login detected

🔹 User: $USER_NAME
🔹 IP Address:Port: $IP_ADDRESS:$PORT
🔹 TTY: $TTY
🔹 Hostname: $HOSTNAME
🔹 Time: $DATE
🔹 Command: $CMD"

# Send the message via Telegram Bot API
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
     -d chat_id="$CHAT_ID" \
     --data-urlencode "text=$MESSAGE" \
     > /dev/null 2>&1
