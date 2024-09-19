#!/bin/bash

# Exit immediately if a command exits with a non-zero status,
# and treat unset variables as an error.
set -euo pipefail

# ----------------------------
# 1. Customizable Variables
# ----------------------------

# User Configuration
NEW_USER="your_username"                # Replace with your desired username
SSH_PORT="30080"                        # Replace with your desired SSH port

# Backup Configuration
BACKUP_DIR="/var/backups"               # Replace with your desired backup directory
RETENTION_DAYS=7                        # Number of days to keep backups

# Tor Hidden Service Configuration
HIDDEN_SERVICE_DIR="/var/lib/tor/hidden_service_blog/"  # Directory for Tor hidden service

# Nginx Configuration
NGINX_DEFAULT_SITE="/etc/nginx/sites-available/default"
NGINX_ROOT_DIR="/var/www/html"

# Backup Script Configuration
BACKUP_SCRIPT="/usr/local/bin/backup.sh"

# Services to Disable
UNNECESSARY_SERVICES=("bluetooth.service" "avahi-daemon.service" "cups.service" "ftp.service" "smtp.service")

# Log File Configuration
LOG_FILE="/var/log/vps_setup.log"

# ----------------------------
# 2. Function Definitions
# ----------------------------

# Function to initialize the log file
function init_log {
    touch "$LOG_FILE"
    chmod 600 "$LOG_FILE"
    echo "========================================" >> "$LOG_FILE"
    echo "Setup started at $(date +"%F %T")" >> "$LOG_FILE"
    echo "========================================" >> "$LOG_FILE"
}

# Function to display informational messages
function echo_info {
    local MESSAGE="$1"
    echo -e "\e[32m[INFO]\e[0m $MESSAGE" | tee -a "$LOG_FILE"
}

# Function to display warning messages
function echo_warn {
    local MESSAGE="$1"
    echo -e "\e[33m[WARN]\e[0m $MESSAGE" | tee -a "$LOG_FILE"
}

# Function to display error messages and exit
function echo_error {
    local MESSAGE="$1"
    echo -e "\e[31m[ERROR]\e[0m $MESSAGE" | tee -a "$LOG_FILE" >&2
    exit 1
}

# Function to check if a package is installed
function is_installed {
    dpkg -l "$1" &> /dev/null
}

# Function to check if a service is enabled
function is_service_enabled {
    systemctl is-enabled --quiet "$1"
}

# Function to check if a service is active
function is_service_active {
    systemctl is-active --quiet "$1"
}

# Function to check if a line exists in a file
function line_exists {
    grep -Fxq "$1" "$2"
}

# ----------------------------
# 3. Initialize Logging
# ----------------------------
init_log

# ----------------------------
# 4. System Update
# ----------------------------
echo_info "Updating system packages..."
apt update && apt upgrade -y &>> "$LOG_FILE"

# (Steps 5 to 10 remain the same as before)

# ----------------------------
# 11. Install and Configure Nginx
# ----------------------------
echo_info "Installing Nginx..."
if is_installed nginx; then
    echo_warn "Nginx is already installed. Skipping installation."
else
    apt install nginx -y &>> "$LOG_FILE"
fi

echo_info "Configuring Nginx for enhanced security..."

# Backup original Nginx config if backup doesn't exist
if [ ! -f /etc/nginx/nginx.conf.bak ]; then
    cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak &>> "$LOG_FILE"
    echo_info "Backup of nginx.conf created at /etc/nginx/nginx.conf.bak"
else
    echo_warn "Backup of nginx.conf already exists. Skipping backup."
fi

# Modify Nginx main configuration for security
NGINX_CONF="/etc/nginx/nginx.conf"
if grep -q "server_tokens off;" "$NGINX_CONF"; then
    echo_warn "Nginx main configuration already enhanced. Skipping modification."
else
    sed -i '/http {/a \    server_tokens off;' "$NGINX_CONF"
    echo_info "Disabled Nginx server tokens."
fi

# Configure Nginx to hide version in error pages
if grep -q "more_set_headers 'Server: '; " "$NGINX_CONF"; then
    echo_warn "Nginx already configured to hide server header. Skipping."
else
    # Install nginx-extras for more_set_headers module
    echo_info "Installing nginx-extras for additional modules..."
    apt install nginx-extras -y &>> "$LOG_FILE"

    # Add directive to hide server header
    sed -i '/http {/a \    more_set_headers "Server: ";' "$NGINX_CONF"
    echo_info "Configured Nginx to hide server header in responses."
fi

# Remove default Nginx welcome page
if [ -f "$NGINX_ROOT_DIR/index.nginx-debian.html" ]; then
    rm -f "$NGINX_ROOT_DIR/index.nginx-debian.html"
    echo_info "Removed default Nginx welcome page."
else
    echo_warn "Default Nginx welcome page not found. Skipping removal."
fi

# Create a minimal custom index page
echo_info "Creating a minimal custom index page..."
cat > "$NGINX_ROOT_DIR/index.html" <<EOL
<!DOCTYPE html>
<html>
<head>
    <title>Welcome</title>
</head>
<body>
    <h1>Welcome to your secure Tor hidden service!</h1>
</body>
</html>
EOL

# Configure custom error pages
echo_info "Configuring custom error pages to prevent server info leakage..."
mkdir -p "$NGINX_ROOT_DIR/errors"
cat > "$NGINX_ROOT_DIR/errors/404.html" <<EOL
<!DOCTYPE html>
<html>
<head>
    <title>404 Not Found</title>
</head>
<body>
    <h1>Oops! The page you're looking for doesn't exist.</h1>
</body>
</html>
EOL

cat > "$NGINX_ROOT_DIR/errors/50x.html" <<EOL
<!DOCTYPE html>
<html>
<head>
    <title>Server Error</title>
</head>
<body>
    <h1>Oops! Something went wrong on our end.</h1>
</body>
</html>
EOL

# Update Nginx default site configuration
if grep -q "error_page 404" "$NGINX_DEFAULT_SITE"; then
    echo_warn "Custom error pages already configured. Skipping."
else
    sed -i '/location \/ {/a \        error_page 404 /errors/404.html;\n        error_page 500 502 503 504 /errors/50x.html;\n        location = /errors/404.html {\n            internal;\n        }\n        location = /errors/50x.html {\n            internal;\n        }' "$NGINX_DEFAULT_SITE"
    echo_info "Updated Nginx default site configuration with custom error pages."
fi

# Test Nginx configuration and restart
echo_info "Testing Nginx configuration..."
nginx -t &>> "$LOG_FILE"

echo_info "Restarting Nginx..."
systemctl restart nginx &>> "$LOG_FILE"

# (The rest of the script remains the same as before)

# ----------------------------
# 27. Completion Message
# ----------------------------
echo_info "Server configuration completed successfully!"

# Display the Onion URL prominently
if [[ -n "${DOMAIN:-}" ]]; then
    echo -e "\e[34m========================================\e[0m"
    echo -e "\e[32m[SUCCESS]\e[0m Your Tor hidden service is running at:"
    echo -e "\e[32m$DOMAIN\e[0m"
    echo -e "\e[34m========================================\e[0m"
else
    echo_warn "Tor hidden service domain not found."
fi

echo_warn "Please securely download your SSH private key from /home/$NEW_USER/.ssh/id_ed25519."
echo_warn "Verify SSH access with the new user before closing your current session."

echo_info "Setup completed at $(date +"%F %T")" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
