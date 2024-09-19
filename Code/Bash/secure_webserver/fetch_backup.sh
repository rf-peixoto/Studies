#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# ----------------------------
# 1. Customizable Variables
# ----------------------------

# VPS Configuration
SERVER_ADDRESS="your_vps_ip"          # Replace with your VPS's IP or hostname
SSH_PORT="30080"                      # Replace with your VPS's SSH port
USERNAME="your_username"              # Replace with your VPS username

# Backup Directory on Client
LOCAL_BACKUP_DIR="$HOME/vps_backups"  # Replace with your desired local backup directory

# ----------------------------
# 2. Function Definitions
# ----------------------------

# Function to display informational messages
function echo_info {
    echo -e "\e[32m[INFO]\e[0m $1"
}

# Function to display warning messages
function echo_warn {
    echo -e "\e[33m[WARN]\e[0m $1"
}

# Function to display error messages and exit
function echo_error {
    echo -e "\e[31m[ERROR]\e[0m $1"
    exit 1
}

# ----------------------------
# 3. Create Local Backup Directory
# ----------------------------
echo_info "Creating local backup directory at $LOCAL_BACKUP_DIR if it doesn't exist..."
mkdir -p "$LOCAL_BACKUP_DIR"

# ----------------------------
# 4. Fetch Latest Backup from VPS
# ----------------------------
echo_info "Fetching the latest backup from VPS..."

# List backups sorted by time, latest first
LATEST_BACKUP=$(ssh -p "$SSH_PORT" "$USERNAME@$SERVER_ADDRESS" "ls -1t /var/backups/backup-*.tar.gz | head -n 1")

if [[ -z "$LATEST_BACKUP" ]]; then
    echo_error "No backup files found on the VPS."
else
    echo_info "Latest backup found: $(basename "$LATEST_BACKUP")"
    
    # Securely copy the backup to the local machine
    scp -P "$SSH_PORT" "$USERNAME@$SERVER_ADDRESS:$LATEST_BACKUP" "$LOCAL_BACKUP_DIR/"
    
    echo_info "Backup $(basename "$LATEST_BACKUP") successfully copied to $LOCAL_BACKup_DIR."
fi

# ----------------------------
# 5. Optional: Delete Old Local Backups
# ----------------------------
echo_info "Removing local backups older than $RETENTION_DAYS days..."

find "$LOCAL_BACKUP_DIR" -type f -name "backup-*.tar.gz" -mtime +$RETENTION_DAYS -exec rm {} \;

echo_info "Old local backups removed."

# ----------------------------
# 6. Completion Message
# ----------------------------
echo_info "Backup transfer completed successfully."
