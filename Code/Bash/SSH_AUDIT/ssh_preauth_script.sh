/etc/ssh/sshrc
 Commands in this file are executed by ssh when the user
 logs in, just before the user\'s shell (or command) is
 started. See the sshd(8) manual page for more
 information.

ref: https://www.linkedin.com/posts/luciano-marcos_se-tem-algo-que-eu-gosto-%C3%A9-seguran%C3%A7a-da-informa%C3%A7%C3%A3o-activity-7317211747042353154-zH-3

# Script:
#!/bin/bash
# /etc/ssh/sshrc

# === Telegram Bot Configuration ===
BOT_TOKEN="YOUR_BOT_TOKEN"
CHAT_ID="YOUR_CHAT_ID"

# === Session Information ===
HOSTNAME=$(hostname)
DATE_START=$(date "+%Y-%m-%d %H:%M:%S %Z")
REMOTE_IP=$(echo $SSH_CLIENT | awk '{print $1}')

# === Send Login Notification ===
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" \
  --data-urlencode "text=🔐 SSH Login Detected
User: $USER
IP: $REMOTE_IP
Hostname: $HOSTNAME
Start Time: $DATE_START" \
  > /dev/null 2>&1
