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
apt autoremove -y &>> "$LOG_FILE"
apt clean &>> "$LOG_FILE"

# ----------------------------
# 5. Create a New User with Sudo Privileges
# ----------------------------
if id "$NEW_USER" &>/dev/null; then
    echo_warn "User '$NEW_USER' already exists. Skipping user creation."
else
    echo_info "Creating a new user: $NEW_USER"
    adduser --disabled-password --gecos "" "$NEW_USER" &>> "$LOG_FILE"

    echo_info "Adding $NEW_USER to sudo group..."
    usermod -aG sudo "$NEW_USER" &>> "$LOG_FILE"
fi

# ----------------------------
# 6. Generate SSH Key Pair for the New User
# ----------------------------
SSH_KEY_PATH="/home/$NEW_USER/.ssh/id_ed25519"

if [ -f "$SSH_KEY_PATH" ]; then
    echo_warn "SSH key for '$NEW_USER' already exists. Skipping key generation."
else
    echo_info "Generating SSH key pair for $NEW_USER..."
    sudo -u "$NEW_USER" mkdir -p /home/"$NEW_USER"/.ssh &>> "$LOG_FILE"
    sudo -u "$NEW_USER" ssh-keygen -t ed25519 -f "$SSH_KEY_PATH" -N "" &>> "$LOG_FILE"
fi

# Extract the public key
PUB_KEY=$(cat "/home/$NEW_USER/.ssh/id_ed25519.pub")

# Set up SSH authorized_keys
AUTHORIZED_KEYS_PATH="/home/$NEW_USER/.ssh/authorized_keys"

if [ -f "$AUTHORIZED_KEYS_PATH" ]; then
    if grep -q "$PUB_KEY" "$AUTHORIZED_KEYS_PATH"; then
        echo_warn "Public key already exists in authorized_keys. Skipping."
    else
        echo_info "Adding public key to authorized_keys for $NEW_USER..."
        echo "$PUB_KEY" >> "$AUTHORIZED_KEYS_PATH"
        chmod 600 "$AUTHORIZED_KEYS_PATH"
        chown -R "$NEW_USER":"$NEW_USER" /home/"$NEW_USER"/.ssh &>> "$LOG_FILE"
    fi
else
    echo_info "Configuring SSH authorized_keys for $NEW_USER..."
    echo "$PUB_KEY" > "$AUTHORIZED_KEYS_PATH"
    chmod 700 /home/"$NEW_USER"/.ssh
    chmod 600 "$AUTHORIZED_KEYS_PATH"
    chown -R "$NEW_USER":"$NEW_USER" /home/"$NEW_USER"/.ssh &>> "$LOG_FILE"
fi

# Secure the SSH private key for user download
if [ -f "$SSH_KEY_PATH" ]; then
    echo_info "Preparing SSH private key for secure download..."
    chmod 600 "$SSH_KEY_PATH" &>> "$LOG_FILE"
else
    echo_error "SSH private key not found at $SSH_KEY_PATH."
fi

# Instructions for user
echo_warn "An SSH key pair has been generated for $NEW_USER."
echo_warn "You need to securely download the private key from /home/$NEW_USER/.ssh/id_ed25519 before ending your current session."
echo_warn "You can use SCP or SFTP to transfer the key to your local machine securely."

# ----------------------------
# 7. Configure SSH
# ----------------------------
echo_info "Configuring SSH..."

# Backup original SSH config if backup doesn't exist
if [ ! -f /etc/ssh/sshd_config.bak ]; then
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak &>> "$LOG_FILE"
    echo_info "Backup of sshd_config created at /etc/ssh/sshd_config.bak"
else
    echo_warn "Backup of sshd_config already exists. Skipping backup."
fi

# Function to update SSH config safely
function update_sshd_config {
    local PARAM="$1"
    local VALUE="$2"
    local FILE="/etc/ssh/sshd_config"

    if grep -q "^$PARAM" "$FILE"; then
        sed -i "s/^$PARAM.*/$PARAM $VALUE/" "$FILE"
    else
        echo "$PARAM $VALUE" >> "$FILE"
    fi
}

# Disable root login and password authentication, change SSH port
update_sshd_config "Port" "$SSH_PORT"
update_sshd_config "PermitRootLogin" "no"
update_sshd_config "PasswordAuthentication" "no"
update_sshd_config "PubkeyAuthentication" "yes"

# Disable SSH Agent Forwarding and enable strict modes
update_sshd_config "AllowAgentForwarding" "no"
update_sshd_config "StrictModes" "yes"

# Restart SSH service
echo_info "Restarting SSH service..."
systemctl restart sshd &>> "$LOG_FILE"

# ----------------------------
# 8. Install and Configure UFW Firewall
# ----------------------------
echo_info "Installing UFW firewall..."
if is_installed ufw; then
    echo_warn "UFW is already installed. Skipping installation."
else
    apt install ufw -y &>> "$LOG_FILE"
fi

echo_info "Configuring UFW rules..."
ufw default deny incoming &>> "$LOG_FILE"
ufw default allow outgoing &>> "$LOG_FILE"

# Allow SSH on the new port
if ufw status | grep -qw "$SSH_PORT/tcp"; then
    echo_warn "UFW already allows port $SSH_PORT/tcp. Skipping."
else
    ufw allow "$SSH_PORT"/tcp &>> "$LOG_FILE"
fi

# Allow HTTP and HTTPS
for PORT in 80 443; do
    if ufw status | grep -qw "$PORT/tcp"; then
        echo_warn "UFW already allows port $PORT/tcp. Skipping."
    else
        ufw allow "$PORT"/tcp &>> "$LOG_FILE"
        echo_info "Allowed port $PORT/tcp in UFW."
    fi
done

# Enable UFW if not already enabled
if ufw status | grep -qw "Status: active"; then
    echo_warn "UFW is already enabled. Skipping."
else
    echo_info "Enabling UFW..."
    ufw --force enable &>> "$LOG_FILE"
fi

# Enhance UFW with rate limiting and drop suspicious packets
echo_info "Enhancing UFW with additional security rules..."

# Limit SSH to prevent brute-force attacks
if ufw status | grep -qw "limit $SSH_PORT/tcp"; then
    echo_warn "UFW rate limiting for port $SSH_PORT/tcp is already enabled. Skipping."
else
    ufw limit "$SSH_PORT"/tcp &>> "$LOG_FILE"
    echo_info "Enabled rate limiting for port $SSH_PORT/tcp in UFW."
fi

# Enable UFW logging
ufw logging high &>> "$LOG_FILE"

# Configure UFW for IPv6 appropriately
echo_info "Configuring UFW for IPv6..."
# Ensure UFW is set to manage IPv6
sed -i 's/^IPV6=yes/IPV6=yes/' /etc/default/ufw

# Reload UFW to apply IPv6 settings
ufw reload &>> "$LOG_FILE"

# ----------------------------
# 9. Install Tor and Nyx
# ----------------------------
echo_info "Installing Tor and Nyx..."
if is_installed tor && is_installed nyx; then
    echo_warn "Tor and Nyx are already installed. Skipping installation."
else
    apt install tor nyx -y &>> "$LOG_FILE"
fi

# ----------------------------
# 10. Configure Tor Hidden Service
# ----------------------------
echo_info "Configuring Tor hidden service..."

# Backup original Tor config if backup doesn't exist
if [ ! -f /etc/tor/torrc.bak ]; then
    cp /etc/tor/torrc /etc/tor/torrc.bak &>> "$LOG_FILE"
    echo_info "Backup of torrc created at /etc/tor/torrc.bak"
else
    echo_warn "Backup of torrc already exists. Skipping backup."
fi

# Check if hidden service is already configured
if grep -q "HiddenServiceDir $HIDDEN_SERVICE_DIR" /etc/tor/torrc; then
    echo_warn "Tor hidden service already configured. Skipping."
else
    # Define Tor hidden service
    # Nginx will listen on localhost:80, Tor will forward to it
    cat >> /etc/tor/torrc <<EOL

# Hidden Service Configuration
HiddenServiceDir $HIDDEN_SERVICE_DIR
HiddenServicePort 80 127.0.0.1:80
EOL
fi

# Restart Tor to apply changes and generate the onion address
echo_info "Restarting Tor service to generate onion address..."
systemctl restart tor &>> "$LOG_FILE"

# Wait for Tor to generate the hidden service files
sleep 10

# Retrieve the onion address
if [ -f "${HIDDEN_SERVICE_DIR}/hostname" ]; then
    ONION_ADDRESS=$(cat "${HIDDEN_SERVICE_DIR}/hostname")

    if [[ -z "$ONION_ADDRESS" ]]; then
        echo_error "Failed to retrieve onion address."
    else
        DOMAIN="$ONION_ADDRESS"
        echo_info "Your Tor hidden service is available at: $DOMAIN"
    fi
else
    echo_error "Hidden service hostname file not found at ${HIDDEN_SERVICE_DIR}/hostname."
fi

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

# Disable server tokens
if grep -q "server_tokens off;" "$NGINX_CONF"; then
    echo_warn "Nginx server_tokens already disabled. Skipping."
else
    sed -i '/http {/a \    server_tokens off;' "$NGINX_CONF"
    echo_info "Disabled Nginx server tokens."
fi

# Install nginx-extras for more_set_headers and more_clear_headers
echo_info "Installing nginx-extras for additional modules..."
if is_installed nginx-extras; then
    echo_warn "nginx-extras is already installed. Skipping installation."
else
    apt install nginx-extras -y &>> "$LOG_FILE"
fi

# Remove the Server header using more_clear_headers
if grep -q 'more_clear_headers "Server";' "$NGINX_CONF"; then
    echo_warn "Nginx already configured to remove Server header. Skipping."
else
    sed -i '/http {/a \    more_clear_headers "Server";' "$NGINX_CONF"
    echo_info "Configured Nginx to remove Server header from responses."
fi

# Implement additional HTTP security headers
SECURITY_HEADERS_CONF="/etc/nginx/snippets/security_headers.conf"

if [ ! -f "$SECURITY_HEADERS_CONF" ]; then
    echo_info "Creating Nginx security headers snippet..."
    cat > "$SECURITY_HEADERS_CONF" <<EOL
# Security Headers
add_header Content-Security-Policy "default-src 'self';" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
EOL
    echo_info "Security headers snippet created at $SECURITY_HEADERS_CONF."
else
    echo_warn "Nginx security headers snippet already exists. Skipping creation."
fi

# Include the security headers snippet in the default site configuration
if grep -q "include snippets/security_headers.conf;" "$NGINX_DEFAULT_SITE"; then
    echo_warn "Security headers already included in Nginx default site. Skipping."
else
    sed -i '/location \/ {/a \        include snippets/security_headers.conf;' "$NGINX_DEFAULT_SITE"
    echo_info "Included security headers in Nginx default site configuration."
fi

# Remove the Server header if not already done
# (Redundant if already handled by more_clear_headers)

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

# Create 404 error page without server info
cat > "$NGINX_ROOT_DIR/errors/404.html" <<EOL
<!DOCTYPE html>
<html>
<head>
    <title>404 Not Found</title>
</head>
<body>
    <center><h1>404 Not Found</h1></center>
    <hr>
</body>
</html>
EOL

# Create 50x error page without server info
cat > "$NGINX_ROOT_DIR/errors/50x.html" <<EOL
<!DOCTYPE html>
<html>
<head>
    <title>Server Error</title>
</head>
<body>
    <center><h1>500 Internal Server Error</h1></center>
    <hr>
</body>
</html>
EOL

# Update Nginx default site configuration with custom error pages
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

# ----------------------------
# 12. Install PHP-FPM and Harden PHP
# ----------------------------
echo_info "Installing PHP-FPM and necessary modules..."
if is_installed php-fpm && is_installed php-mysql; then
    echo_warn "PHP-FPM and php-mysql are already installed. Skipping installation."
else
    apt install php-fpm php-mysql -y &>> "$LOG_FILE"
fi

echo_info "Configuring PHP-FPM to use Unix socket..."
# Ensure PHP-FPM is using a Unix socket
PHP_FPM_SOCK=$(find /run/php/ -type s -name "php*-fpm.sock" | head -n 1)

if [ -z "$PHP_FPM_SOCK" ]; then
    echo_error "PHP-FPM socket not found. Please check PHP-FPM installation."
fi

# Set ownership and permissions for the socket
sed -i 's/^listen.owner.*/listen.owner = www-data/' /etc/php/*/fpm/pool.d/www.conf
sed -i 's/^listen.group.*/listen.group = www-data/' /etc/php/*/fpm/pool.d/www.conf
sed -i 's/^listen.mode.*/listen.mode = 0660/' /etc/php/*/fpm/pool.d/www.conf

# Harden PHP by disabling unnecessary functions and setting appropriate directives
PHP_INI_DIR="/etc/php/$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')/fpm"
PHP_INI_FILE="$PHP_INI_DIR/php.ini"

echo_info "Hardening PHP by disabling unnecessary functions..."
# List of functions to disable
DISABLED_FUNCTIONS="exec,passthru,shell_exec,system,proc_open,popen,curl_exec,curl_multi_exec,parse_ini_file,show_source"

# Backup php.ini if backup doesn't exist
if [ ! -f "$PHP_INI_FILE.bak" ]; then
    cp "$PHP_INI_FILE" "$PHP_INI_FILE.bak" &>> "$LOG_FILE"
    echo_info "Backup of php.ini created at $PHP_INI_FILE.bak"
else
    echo_warn "Backup of php.ini already exists. Skipping backup."
fi

# Disable functions
if grep -q "^disable_functions = $DISABLED_FUNCTIONS" "$PHP_INI_FILE"; then
    echo_warn "Unnecessary PHP functions already disabled. Skipping."
else
    sed -i "s/^disable_functions.*/disable_functions = $DISABLED_FUNCTIONS/" "$PHP_INI_FILE"
    echo_info "Disabled unnecessary PHP functions in php.ini."
fi

echo_info "Setting appropriate php.ini directives for security..."
# Set some recommended PHP settings
sed -i 's/^expose_php = .*/expose_php = Off/' "$PHP_INI_FILE"
sed -i 's/^display_errors = .*/display_errors = Off/' "$PHP_INI_FILE"
sed -i 's/^log_errors = .*/log_errors = On/' "$PHP_INI_FILE"
sed -i 's/^session.cookie_httponly = .*/session.cookie_httponly = On/' "$PHP_INI_FILE"
sed -i 's/^session.use_strict_mode = .*/session.use_strict_mode = On/' "$PHP_INI_FILE"
sed -i 's/^allow_url_fopen = .*/allow_url_fopen = Off/' "$PHP_INI_FILE"
sed -i 's/^allow_url_include = .*/allow_url_include = Off/' "$PHP_INI_FILE"

echo_info "Isolating PHP-FPM processes for enhanced security..."
# Ensure PHP-FPM runs under the www-data user and group
sed -i 's/^user = .*/user = www-data/' "$PHP_INI_DIR/fpm-pool.conf"
sed -i 's/^group = .*/group = www-data/' "$PHP_INI_DIR/fpm-pool.conf"

# Restart PHP-FPM and Nginx
echo_info "Restarting PHP-FPM and Nginx..."
systemctl restart php*-fpm &>> "$LOG_FILE"
systemctl restart nginx &>> "$LOG_FILE"

# ----------------------------
# 13. Install and Configure ModSecurity
# ----------------------------
echo_info "Installing ModSecurity..."
if is_installed libnginx-mod-http-modsecurity; then
    echo_warn "ModSecurity is already installed. Skipping installation."
else
    apt install libnginx-mod-http-modsecurity -y &>> "$LOG_FILE"
fi

echo_info "Configuring ModSecurity..."
# Enable ModSecurity
if grep -q "^SecRuleEngine On" /etc/modsecurity/modsecurity.conf; then
    echo_warn "ModSecurity is already enabled. Skipping."
else
    sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' /etc/modsecurity/modsecurity.conf
    echo_info "Enabled ModSecurity."
fi

# Configure Nginx to use ModSecurity
if grep -q "modsecurity on;" /etc/nginx/modsecurity.conf; then
    echo_warn "ModSecurity is already configured in Nginx. Skipping."
else
    sed -i 's/# modsecurity on;/modsecurity on;/' /etc/nginx/modsecurity.conf
    sed -i 's/# modsecurity_rules_file \/path\/to\/modsecurity\/rules.conf;/modsecurity_rules_file \/etc\/modsecurity\/modsecurity.conf;/' /etc/nginx/modsecurity.conf
    echo_info "Configured Nginx to use ModSecurity."
fi

# Include ModSecurity configuration in Nginx main config if not already present
if grep -q "modsecurity on;" /etc/nginx/nginx.conf; then
    echo_warn "ModSecurity is already included in Nginx main configuration. Skipping."
else
    echo_info "Including ModSecurity in Nginx main configuration..."
    echo "modsecurity on;" >> /etc/nginx/nginx.conf
    echo "modsecurity_rules_file /etc/modsecurity/modsecurity.conf;" >> /etc/nginx/nginx.conf
fi

# Restart Nginx to apply ModSecurity
echo_info "Restarting Nginx to apply ModSecurity..."
systemctl restart nginx &>> "$LOG_FILE"

# ----------------------------
# 14. Configure ModSecurity with OWASP Core Rule Set (CRS)
# ----------------------------
echo_info "Configuring ModSecurity with OWASP Core Rule Set (CRS)..."

# Check if CRS is already cloned
if [ -d /etc/modsecurity/crs ]; then
    echo_warn "OWASP CRS is already cloned. Skipping."
else
    # Install dependencies
    apt install git -y &>> "$LOG_FILE"

    # Clone CRS repository
    git clone https://github.com/coreruleset/coreruleset.git /etc/modsecurity/crs &>> "$LOG_FILE"

    # Copy example setup
    cp /etc/modsecurity/crs/crs-setup.conf.example /etc/modsecurity/crs/crs-setup.conf &>> "$LOG_FILE"
    echo_info "Cloned OWASP CRS and copied setup configuration."
fi

# Check if CRS is already included in ModSecurity config
if grep -q "Include /etc/modsecurity/crs/crs-setup.conf" /etc/modsecurity/modsecurity.conf; then
    echo_warn "OWASP CRS is already included in ModSecurity configuration. Skipping."
else
    # Include CRS in ModSecurity configuration
    echo "Include /etc/modsecurity/crs/crs-setup.conf" >> /etc/modsecurity/modsecurity.conf
    echo "Include /etc/modsecurity/crs/rules/*.conf" >> /etc/modsecurity/modsecurity.conf
    echo_info "Included OWASP CRS in ModSecurity configuration."
fi

# Restart Nginx to apply ModSecurity CRS
echo_info "Restarting Nginx to apply ModSecurity CRS..."
systemctl restart nginx &>> "$LOG_FILE"

# ----------------------------
# 15. Harden Kernel Parameters and Disable IPv6
# ----------------------------
echo_info "Hardening kernel parameters and disabling IPv6..."

# Check if kernel parameters are already set
if grep -q "net.ipv4.ip_forward = 0" /etc/sysctl.conf; then
    echo_warn "Kernel parameters already hardened. Skipping."
else
    cat >> /etc/sysctl.conf <<EOL

# Hardened kernel parameters

# Disable IP forwarding
net.ipv4.ip_forward = 0

# Enable TCP SYN Cookies
net.ipv4.tcp_syncookies = 1

# Disable source packet routing
net.ipv4.conf.all.route_localnet = 0

# Disable send redirects
net.ipv4.conf.all.send_redirects = 0

# Disable ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# Enable protection against SYN flood attacks
net.ipv4.tcp_synack_retries = 2

# Log Martian Packets
net.ipv4.conf.all.log_martians = 1

# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1

# Additional Kernel Hardening

# Enable Reverse Path Filtering
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Disable ICMP Redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0

# Ignore ICMP Broadcast Requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Protect against IP Spoofing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Enable TCP SYN Cookies
net.ipv4.tcp_syncookies = 1
EOL
    echo_info "Added hardened kernel parameters to sysctl.conf."
fi

# Apply the kernel parameter changes
echo_info "Applying kernel parameter changes..."
sysctl -p &>> "$LOG_FILE"

# ----------------------------
# 16. Install and Configure Fail2Ban
# ----------------------------
echo_info "Installing Fail2Ban to protect against brute-force attacks..."
if is_installed fail2ban; then
    echo_warn "Fail2Ban is already installed. Skipping installation."
else
    apt install fail2ban -y &>> "$LOG_FILE"
fi

# Configure Fail2Ban
if [ -f /etc/fail2ban/jail.local ]; then
    echo_warn "Fail2Ban jail.local already exists. Skipping configuration."
else
    cat > /etc/fail2ban/jail.local <<EOL
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
ignoreip = 127.0.0.1/8 ::1

[sshd]
port = $SSH_PORT
logpath = /var/log/auth.log
backend = systemd

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
EOL
    echo_info "Fail2Ban configuration updated."
fi

# Restart Fail2Ban
echo_info "Restarting Fail2Ban service..."
systemctl restart fail2ban &>> "$LOG_FILE"

# ----------------------------
# 17. Install and Configure AppArmor
# ----------------------------
echo_info "Installing and enabling AppArmor..."
if is_installed apparmor && is_installed apparmor-profiles; then
    echo_warn "AppArmor and profiles are already installed. Skipping installation."
else
    apt install apparmor apparmor-profiles -y &>> "$LOG_FILE"
fi

# Enable and start AppArmor
if systemctl is-active --quiet apparmor; then
    echo_warn "AppArmor is already running. Skipping start."
else
    systemctl enable apparmor &>> "$LOG_FILE"
    systemctl start apparmor &>> "$LOG_FILE"
    echo_info "AppArmor enabled and started."
fi

# ----------------------------
# 18. Disable Unnecessary Services
# ----------------------------
echo_info "Disabling unnecessary services..."

for service in "${UNNECESSARY_SERVICES[@]}"; do
    if systemctl is-enabled --quiet "$service"; then
        systemctl disable "$service" &>> "$LOG_FILE"
        echo_info "Disabled $service"
    else
        echo_warn "$service is already disabled or not installed. Skipping."
    fi

    if systemctl is-active --quiet "$service"; then
        systemctl stop "$service" &>> "$LOG_FILE"
        echo_info "Stopped $service"
    else
        echo_warn "$service is not active. Skipping."
    fi
done

# ----------------------------
# 19. Configure UFW to Block Invalid Packets
# ----------------------------
echo_info "Configuring UFW to block invalid packets..."
if ufw status | grep -qw "deny from any to any proto tcp flags all FIN,SYN,RST,ACK,URG,PSH"; then
    echo_warn "UFW already configured to block invalid packets. Skipping."
else
    ufw deny in from any to any proto tcp flags all FIN,SYN,RST,ACK,URG,PSH &>> "$LOG_FILE"
    echo_info "Configured UFW to block invalid packets."
fi

# ----------------------------
# 20. Enable TCP SYN Cookies
# ----------------------------
echo_info "Ensuring TCP SYN Cookies are enabled..."
# Already enabled in kernel parameters above

# ----------------------------
# 21. Implement Zero Trust Principles
# ----------------------------
echo_info "Implementing Zero Trust principles..."
# Enforced through previous configurations:
# - Strict SSH access controls
# - Firewall rules limiting access
# - Fail2Ban protecting against unauthorized access attempts
# - AppArmor providing MAC
# Further Zero Trust implementations may involve using VPNs, mutual TLS, etc., which are beyond the scope of this script.

# ----------------------------
# 22. Install and Configure AIDE (Intrusion Detection)
# ----------------------------
echo_info "Installing AIDE for Intrusion Detection..."
if is_installed aide; then
    echo_warn "AIDE is already installed. Skipping installation."
else
    apt install aide -y &>> "$LOG_FILE"
fi

# Initialize AIDE database if not already initialized
if [ -f /var/lib/aide/aide.db ]; then
    echo_warn "AIDE database already initialized. Skipping initialization."
else
    echo_info "Initializing AIDE database..."
    aideinit &>> "$LOG_FILE"
    cp /var/lib/aide/aide.db.new /var/lib/aide/aide.db &>> "$LOG_FILE"
    echo_info "AIDE database initialized."
fi

# Schedule AIDE daily checks via cron
if [ -f /etc/cron.d/aide ]; then
    echo_warn "AIDE cron job already exists. Skipping."
else
    echo_info "Scheduling daily AIDE integrity checks..."
    echo "0 4 * * * root /usr/bin/aide.wrapper --check" > /etc/cron.d/aide &>> "$LOG_FILE"
    echo_info "AIDE cron job created."
fi

# ----------------------------
# 23. Implement Disk Encryption with LUKS (Manual Setup Recommended)
# ----------------------------
echo_info "Setting up LUKS disk encryption..."

# **⚠️ WARNING ⚠️**
# Implementing LUKS encryption on a running system can lead to data loss and system inaccessibility.
# It is highly recommended to set up LUKS encryption during the initial installation of the OS.
# Proceed only if you are certain and have backups of all important data.

# Example steps (not fully automated in this script):
# a. Install cryptsetup
# b. Partition the disk if necessary
# c. Initialize LUKS on the desired partition
# d. Create filesystems within the encrypted partition
# e. Update /etc/crypttab and /etc/fstab accordingly
# f. Reboot and test the setup

# For security reasons, the script will not automate this step to prevent potential system lockouts.

echo_warn "Disk encryption with LUKS is not automated in this script. Please set it up manually if required."
echo_warn "Ensure you understand the risks and have proper backups before proceeding."

# ----------------------------
# 24. Install and Configure Automatic System Updates
# ----------------------------
echo_info "Setting up automatic system updates..."

# Install unattended-upgrades if not already installed
if is_installed unattended-upgrades; then
    echo_warn "unattended-upgrades is already installed. Skipping installation."
else
    apt install unattended-upgrades -y &>> "$LOG_FILE"
fi

# Enable automatic updates
if grep -q "^Unattended-Upgrade::Enabled \"true\";" /etc/apt/apt.conf.d/50unattended-upgrades; then
    echo_warn "Automatic system updates are already enabled. Skipping."
else
    dpkg-reconfigure --priority=low unattended-upgrades &>> "$LOG_FILE"
    echo_info "Automatic system updates enabled."
fi

# ----------------------------
# 25. Install and Configure Cron Jobs for Backups
# ----------------------------
echo_info "Installing cron..."
if is_installed cron; then
    echo_warn "Cron is already installed. Skipping installation."
else
    apt install cron -y &>> "$LOG_FILE"
fi

# Create backup script
if [ -f "$BACKUP_SCRIPT" ]; then
    echo_warn "Backup script already exists at $BACKUP_SCRIPT. Skipping creation."
else
    echo_info "Creating backup script at $BACKUP_SCRIPT..."
    cat > "$BACKUP_SCRIPT" <<'EOL'
#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -euo pipefail

# ----------------------------
# 1. Customizable Variables
# ----------------------------

# User Configuration
NEW_USER="your_username"                # This will be replaced dynamically

# Backup Configuration
BACKUP_DIR="/var/backups"               # Backup storage directory
RETENTION_DAYS=7                        # Number of days to keep backups

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
    echo_error "NEW_USER is not set. Please set it before running the backup script."
fi

# ----------------------------
# 4. Create Backup Directory
# ----------------------------
echo_info "Ensuring backup directory exists at $BACKUP_DIR..."
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
EOL

    # Replace placeholder in backup script with actual username
    sed -i "s/your_username/$NEW_USER/" "$BACKUP_SCRIPT"

    # Make backup script executable
    chmod +x "$BACKUP_SCRIPT"

    echo_info "Backup script created at $BACKUP_SCRIPT."
fi

# Create cron job for daily backups at 2 AM
CRON_JOB="0 2 * * * root $BACKUP_SCRIPT"

if [ -f /etc/cron.d/daily_backup ]; then
    echo_warn "Cron job for daily backups already exists. Skipping."
else
    echo_info "Setting up cron job for daily backups..."
    echo "$CRON_JOB" > /etc/cron.d/daily_backup &>> "$LOG_FILE"
    echo_info "Cron job for daily backups created."
fi

# ----------------------------
# 26. Final Security Enhancements
# ----------------------------
echo_info "Performing final security enhancements..."

# Disable root account password
echo_info "Locking the root account to prevent direct logins..."
passwd -l root &>> "$LOG_FILE"

# Reload UFW to apply all changes
echo_info "Reloading UFW to apply all firewall rules..."
ufw reload &>> "$LOG_FILE"

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
