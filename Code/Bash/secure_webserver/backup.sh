#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# ----------------------------
# 1. Customizable Variables
# ----------------------------

# User Configuration
NEW_USER="your_username"                # Replace with your actual username

# Backup Configuration
BACKUP_DIR="/var/backups"               # Backup storage directory
RETENTION_DAYS=7                        # Number of days to keep backups

# Backup Script Configuration
BACKUP_SCRIPT="/usr/local/bin/backup.sh"

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
# 3. Validate Variables
# ----------------------------

# Check if NEW_USER is set
if [[ -z "$NEW_USER" ]]; then
    echo_error "NEW_USER is not set. Please edit the script and set it to your VPS username."
fi

# ----------------------------
# 4. Create Backup Directory
# ----------------------------
echo_info "Creating backup directory at $BACKUP_DIR if it doesn't exist..."
mkdir -p "$BACKUP_DIR"

# ----------------------------
# 5. Perform Backup
# ----------------------------
echo_info "Starting backup process..."

# Generate timestamp
TIMESTAMP=$(date +"%F_%T")

# Define backup file name
BACKUP_FILE="$BACKUP_DIR/backup-$TIMESTAMP.tar.gz"

# Perform the backup using tar
tar --exclude="$BACKUP_DIR" -czf "$BACKUP_FILE" \
    "/home/$NEW_USER" \
    "/etc/nginx" \
    "/etc/tor" \
    "/etc/modsecurity" \
    "/var/lib/aide/aide.db"

echo_info "Backup created at $BACKUP_FILE."

# ----------------------------
# 6. Manage Backup Retention
# ----------------------------
echo_info "Removing backups older than $RETENTION_DAYS days..."

find "$BACKUP_DIR" -type f -name "backup-*.tar.gz" -mtime +$RETENTION_DAYS -exec rm {} \;

echo_info "Old backups removed."

# ----------------------------
# 7. Logging and Notifications (Optional)
# ----------------------------
# You can enhance this script by adding logging or sending notifications upon successful backup.

# ----------------------------
# 8. Completion Message
# ----------------------------
echo_info "Backup process completed successfully."
