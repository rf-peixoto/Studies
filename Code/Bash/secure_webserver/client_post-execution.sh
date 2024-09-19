#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# ----------------------------
# 1. Customizable Variables
# ----------------------------

# VPS Configuration
SERVER_ADDRESS="your_server_ip_or_hostname"  # Replace with your VPS's public IP or hostname
SSH_PORT="30080"                              # Replace with your VPS's SSH port
USERNAME="your_username"                      # Replace with the username created on the VPS

# SSH Key Configuration
REMOTE_PRIVATE_KEY_PATH="/home/$USERNAME/.ssh/id_ed25519"  # Path on the VPS
LOCAL_PRIVATE_KEY_PATH="$HOME/.ssh/id_ed25519_vps"         # Path on your local machine

# SSH Config Configuration
SSH_CONFIG_FILE="$HOME/.ssh/config"                       # Local SSH config file
SSH_CONFIG_HOST_ALIAS="vps_blog"                           # Host alias for easier SSH access

# Backup Removal Confirmation
REMOVE_KEY_FROM_SERVER=true                                # Set to 'false' if you don't want to remove the key automatically

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

# Check if SERVER_ADDRESS is set
if [[ -z "$SERVER_ADDRESS" ]]; then
    echo_error "SERVER_ADDRESS is not set. Please edit the script and set it to your VPS's IP or hostname."
fi

# Check if USERNAME is set
if [[ -z "$USERNAME" ]]; then
    echo_error "USERNAME is not set. Please edit the script and set it to the username created on the VPS."
fi

# ----------------------------
# 4. Download SSH Private Key
# ----------------------------
echo_info "Starting download of SSH private key from VPS..."

# Check if the local private key already exists
if [[ -f "$LOCAL_PRIVATE_KEY_PATH" ]]; then
    echo_warn "Local private key already exists at $LOCAL_PRIVATE_KEY_PATH. Skipping download to prevent overwrite."
else
    # Use scp to download the private key
    scp -P "$SSH_PORT" "$USERNAME@$SERVER_ADDRESS:$REMOTE_PRIVATE_KEY_PATH" "$LOCAL_PRIVATE_KEY_PATH"
    echo_info "SSH private key downloaded to $LOCAL_PRIVATE_KEY_PATH."
fi

# ----------------------------
# 5. Set Proper Permissions on Private Key
# ----------------------------
echo_info "Setting proper permissions on the SSH private key..."
chmod 600 "$LOCAL_PRIVATE_KEY_PATH"
echo_info "Permissions set to 600."

# ----------------------------
# 6. Configure SSH Client
# ----------------------------
echo_info "Configuring SSH client..."

# Create ~/.ssh directory if it doesn't exist
mkdir -p "$HOME/.ssh"

# Backup existing SSH config if it exists
if [[ -f "$SSH_CONFIG_FILE" ]]; then
    cp "$SSH_CONFIG_FILE" "${SSH_CONFIG_FILE}.bak"
    echo_info "Existing SSH config backed up to ${SSH_CONFIG_FILE}.bak."
fi

# Add or update SSH config for the VPS
if grep -q "Host $SSH_CONFIG_HOST_ALIAS" "$SSH_CONFIG_FILE" 2>/dev/null; then
    echo_warn "SSH config for host alias '$SSH_CONFIG_HOST_ALIAS' already exists. Skipping addition."
else
    cat >> "$SSH_CONFIG_FILE" <<EOL

# Configuration for VPS Blog
Host $SSH_CONFIG_HOST_ALIAS
    HostName $SERVER_ADDRESS
    User $USERNAME
    Port $SSH_PORT
    IdentityFile $LOCAL_PRIVATE_KEY_PATH
    IdentitiesOnly yes
    ForwardAgent no
EOL
    echo_info "SSH config updated with host alias '$SSH_CONFIG_HOST_ALIAS'."
fi

# Set permissions for SSH config
chmod 600 "$SSH_CONFIG_FILE"
echo_info "SSH config permissions set to 600."

# ----------------------------
# 7. Verify SSH Connection
# ----------------------------
echo_info "Verifying SSH connection..."

# Attempt to SSH and execute a simple command
if ssh -F "$SSH_CONFIG_FILE" "$SSH_CONFIG_HOST_ALIAS" "echo 'SSH connection successful.'" ; then
    echo_info "SSH connection verified successfully."
else
    echo_error "SSH connection failed. Please check your configurations."
fi

# ----------------------------
# 8. Remove Private Key from Server
# ----------------------------
if [[ "$REMOVE_KEY_FROM_SERVER" == true ]]; then
    echo_info "Removing SSH private key from VPS to enhance security..."
    ssh -F "$SSH_CONFIG_FILE" "$SSH_CONFIG_HOST_ALIAS" "rm -f '$REMOTE_PRIVATE_KEY_PATH'"
    echo_info "SSH private key removed from VPS."
else
    echo_warn "Skipping removal of SSH private key from VPS as per configuration."
fi

# ----------------------------
# 9. Completion Message
# ----------------------------
echo_info "Client-side setup completed successfully!"
echo_warn "You can now connect to your VPS using the host alias '$SSH_CONFIG_HOST_ALIAS'."
echo_warn "Example command: ssh $SSH_CONFIG_HOST_ALIAS"

