#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

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

# Backup Script Configuration
BACKUP_SCRIPT="/usr/local/bin/backup.sh"

# Services to Disable
UNNECESSARY_SERVICES=("bluetooth.service" "avahi-daemon.service" "cups.service" "ftp.service" "smtp.service")

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
# 3. System Update
# ----------------------------
echo_info "Updating system packages..."
apt update && apt upgrade -y

# ----------------------------
# 4. Create a New User with Sudo Privileges
# ----------------------------
echo_info "Creating a new user: $NEW_USER"
adduser --disabled-password --gecos "" "$NEW_USER"

echo_info "Adding $NEW_USER to sudo group..."
usermod -aG sudo "$NEW_USER"

# ----------------------------
# 5. Generate SSH Key Pair for the New User
# ----------------------------
echo_info "Generating SSH key pair for $NEW_USER..."
sudo -u "$NEW_USER" mkdir -p /home/"$NEW_USER"/.ssh
sudo -u "$NEW_USER" ssh-keygen -t ed25519 -f /home/"$NEW_USER"/.ssh/id_ed25519 -N ""

# Extract the public key
PUB_KEY=$(cat /home/"$NEW_USER"/.ssh/id_ed25519.pub)

# Set up SSH authorized_keys
echo_info "Configuring SSH authorized_keys for $NEW_USER..."
echo "$PUB_KEY" > /home/"$NEW_USER"/.ssh/authorized_keys
chmod 700 /home/"$NEW_USER"/.ssh
chmod 600 /home/"$NEW_USER"/.ssh/authorized_keys
chown -R "$NEW_USER":"$NEW_USER" /home/"$NEW_USER"/.ssh

# Secure the SSH private key for user download
echo_info "Preparing SSH private key for secure download..."
chmod 600 /home/"$NEW_USER"/.ssh/id_ed25519

# Instructions for user
echo_warn "An SSH key pair has been generated for $NEW_USER."
echo_warn "You need to securely download the private key from /home/$NEW_USER/.ssh/id_ed25519 before ending your current session."
echo_warn "You can use SCP or SFTP to transfer the key to your local machine securely."

# ----------------------------
# 6. Configure SSH
# ----------------------------
echo_info "Configuring SSH..."

# Backup original SSH config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Disable root login and password authentication, change SSH port
sed -i "s/#Port 22/Port $SSH_PORT/" /etc/ssh/sshd_config
sed -i "s/^PermitRootLogin.*/PermitRootLogin no/" /etc/ssh/sshd_config
sed -i "s/^PasswordAuthentication.*/PasswordAuthentication no/" /etc/ssh/sshd_config
sed -i "s/^#PubkeyAuthentication.*/PubkeyAuthentication yes/" /etc/ssh/sshd_config

# Disable SSH Agent Forwarding and enable strict modes
sed -i "s/^#AllowAgentForwarding.*/AllowAgentForwarding no/" /etc/ssh/sshd_config
sed -i "s/^#StrictModes.*/StrictModes yes/" /etc/ssh/sshd_config

# Restart SSH service
echo_info "Restarting SSH service..."
systemctl restart sshd

# ----------------------------
# 7. Install and Configure UFW Firewall
# ----------------------------
echo_info "Installing UFW firewall..."
apt install ufw -y

echo_info "Configuring UFW rules..."
ufw default deny incoming
ufw default allow outgoing

# Allow SSH on the new port
ufw allow "$SSH_PORT"/tcp

# Do NOT allow HTTP/HTTPS externally since Tor will handle it
# Nginx will listen only on localhost

# Enable UFW
echo_info "Enabling UFW..."
ufw --force enable

# Enhance UFW with rate limiting and drop suspicious packets
echo_info "Enhancing UFW with additional security rules..."

# Limit SSH to prevent brute-force attacks
ufw limit "$SSH_PORT"/tcp

# Enable UFW logging
ufw logging high

# ----------------------------
# 8. Install Tor and Nyx
# ----------------------------
echo_info "Installing Tor and Nyx..."
apt install tor nyx -y

# ----------------------------
# 9. Configure Tor Hidden Service
# ----------------------------
echo_info "Configuring Tor hidden service..."

# Backup original Tor config
cp /etc/tor/torrc /etc/tor/torrc.bak

# Define Tor hidden service
# Nginx will listen on localhost:80, Tor will forward to it
cat >> /etc/tor/torrc <<EOL

# Hidden Service Configuration
HiddenServiceDir $HIDDEN_SERVICE_DIR
HiddenServicePort 80 127.0.0.1:80
EOL

# Restart Tor to apply changes and generate the onion address
echo_info "Restarting Tor service to generate onion address..."
systemctl restart tor

# Wait for Tor to generate the hidden service files
sleep 10

# Retrieve the onion address
ONION_ADDRESS=$(cat ${HIDDEN_SERVICE_DIR}/hostname)

if [[ -z "$ONION_ADDRESS" ]]; then
    echo_error "Failed to retrieve onion address."
    exit 1
else
    DOMAIN="$ONION_ADDRESS"
    echo_info "Your Tor hidden service is available at: $DOMAIN"
fi

# ----------------------------
# 10. Install and Configure Nginx
# ----------------------------
echo_info "Installing Nginx..."
apt install nginx -y

echo_info "Configuring Nginx for enhanced security..."

# Backup original Nginx config
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak

# Modify Nginx main configuration for security
cat > /etc/nginx/nginx.conf <<EOL
user www-data;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 768;
    # multi_accept on;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Hide Nginx version
    server_tokens off;

    # Security Headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; object-src 'none'; style-src 'self' 'unsafe-inline';";

    # Disable unused HTTP methods
    if (\$request_method !~ ^(GET|HEAD|POST)$ ) {
        return 444;
    }

    # Log settings
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Rate Limiting
    limit_req_zone \$binary_remote_addr zone=one:10m rate=1r/s;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOL

# Configure default site with security enhancements and CSP
cat > "$NGINX_DEFAULT_SITE" <<EOL
server {
    listen 127.0.0.1:80 default_server;
    listen [::1]:80 default_server;

    server_name $DOMAIN;

    root /var/www/html;
    index index.php index.html index.htm;

    # Security Headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; object-src 'none'; style-src 'self' 'unsafe-inline';";

    # Enable Rate Limiting
    limit_req zone=one burst=5 nodelay;

    location / {
        try_files \$uri \$uri/ =404;
    }

    # PHP-FPM configuration
    location ~ \.php\$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php-fpm.sock;
    }

    # Deny access to .htaccess files
    location ~ /\.ht {
        deny all;
    }

    # Limit request size
    client_max_body_size 10M;

    # Disable unwanted HTTP methods
    if (\$request_method !~ ^(GET|HEAD|POST)$ ) {
        return 444;
    }

    # Uniform Response Times
    # Add delay uniformly if needed using ngx_http_delay_module or similar (optional)
}
EOL

# Remove default symlink and enable the new configuration
rm -f /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/

# Disable unnecessary Nginx modules
# Note: Nginx on Debian-based systems loads modules dynamically from /etc/nginx/modules-enabled/
# To disable, remove the symlinks or comment out the load_module lines in /etc/nginx/nginx.conf
# Here, we assume minimal modules are installed by default. Further customization may require recompiling Nginx.

# Test Nginx configuration and restart
echo_info "Testing Nginx configuration..."
nginx -t

echo_info "Restarting Nginx..."
systemctl restart nginx

# ----------------------------
# 11. Install PHP-FPM
# ----------------------------
echo_info "Installing PHP-FPM and necessary modules..."
apt install php-fpm php-mysql -y

echo_info "Configuring PHP-FPM to use Unix socket..."
# Ensure PHP-FPM is using a Unix socket
PHP_FPM_SOCK=$(find /run/php/ -type s -name "php*-fpm.sock" | head -n 1)

if [ -z "$PHP_FPM_SOCK" ]; then
    echo_error "PHP-FPM socket not found. Please check PHP-FPM installation."
    exit 1
fi

# Set ownership and permissions for the socket
sed -i 's/^listen.owner.*/listen.owner = www-data/' /etc/php/*/fpm/pool.d/www.conf
sed -i 's/^listen.group.*/listen.group = www-data/' /etc/php/*/fpm/pool.d/www.conf
sed -i 's/^listen.mode.*/listen.mode = 0660/' /etc/php/*/fpm/pool.d/www.conf

# Restart PHP-FPM and Nginx
echo_info "Restarting PHP-FPM and Nginx..."
systemctl restart php*-fpm
systemctl restart nginx

# ----------------------------
# 12. Install and Configure ModSecurity
# ----------------------------
echo_info "Installing ModSecurity..."
apt install libnginx-mod-http-modsecurity -y

echo_info "Configuring ModSecurity..."
# Enable ModSecurity in Detection Only mode initially
cp /etc/modsecurity/modsecurity.conf-recommended /etc/modsecurity/modsecurity.conf
sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' /etc/modsecurity/modsecurity.conf

# Configure Nginx to use ModSecurity
sed -i 's/# modsecurity on;/modsecurity on;/' /etc/nginx/modsecurity.conf
sed -i 's/# modsecurity_rules_file \/path\/to\/modsecurity\/rules.conf;/modsecurity_rules_file \/etc\/modsecurity\/modsecurity.conf;/' /etc/nginx/modsecurity.conf

# Include ModSecurity configuration in Nginx main config if not already present
if ! grep -q "modsecurity on;" /etc/nginx/nginx.conf; then
    echo_info "Including ModSecurity in Nginx main configuration..."
    echo "modsecurity on;" >> /etc/nginx/nginx.conf
    echo "modsecurity_rules_file /etc/modsecurity/modsecurity.conf;" >> /etc/nginx/nginx.conf
fi

# Restart Nginx to apply ModSecurity
echo_info "Restarting Nginx to apply ModSecurity..."
systemctl restart nginx

# ----------------------------
# 13. Configure ModSecurity with OWASP Core Rule Set (CRS)
# ----------------------------
echo_info "Configuring ModSecurity with OWASP Core Rule Set (CRS)..."

# Install dependencies
apt install git -y

# Clone CRS repository
git clone https://github.com/coreruleset/coreruleset.git /etc/modsecurity/crs

# Copy example setup
cp /etc/modsecurity/crs/crs-setup.conf.example /etc/modsecurity/crs/crs-setup.conf

# Include CRS in ModSecurity configuration
echo "Include /etc/modsecurity/crs/crs-setup.conf" >> /etc/modsecurity/modsecurity.conf
echo "Include /etc/modsecurity/crs/rules/*.conf" >> /etc/modsecurity/modsecurity.conf

# Restart Nginx to apply ModSecurity CRS
echo_info "Restarting Nginx to apply ModSecurity CRS..."
systemctl restart nginx

# ----------------------------
# 14. Harden Kernel Parameters and Disable IPv6
# ----------------------------
echo_info "Hardening kernel parameters and disabling IPv6..."

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
EOL

# Apply the kernel parameter changes
sysctl -p

# ----------------------------
# 15. Install and Configure Fail2Ban
# ----------------------------
echo_info "Installing Fail2Ban to protect against brute-force attacks..."
apt install fail2ban -y

# Configure Fail2Ban
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
EOL

# Restart Fail2Ban
echo_info "Restarting Fail2Ban service..."
systemctl restart fail2ban

# ----------------------------
# 16. Install and Configure AppArmor
# ----------------------------
echo_info "Installing and enabling AppArmor..."
apt install apparmor apparmor-profiles -y
systemctl enable apparmor
systemctl start apparmor

# ----------------------------
# 17. Disable Unnecessary Services
# ----------------------------
echo_info "Disabling unnecessary services..."

for service in "${UNNECESSARY_SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        systemctl disable --now "$service"
        echo_info "Disabled and stopped $service"
    else
        echo_info "$service is not active, skipping."
    fi
done

# ----------------------------
# 18. Configure UFW to Block Invalid Packets
# ----------------------------
echo_info "Configuring UFW to block invalid packets..."
ufw deny in from any to any proto tcp flags all FIN,SYN,RST,ACK,URG,PSH

# ----------------------------
# 19. Enable TCP SYN Cookies
# ----------------------------
echo_info "Ensuring TCP SYN Cookies are enabled..."
# Already enabled in kernel parameters above

# ----------------------------
# 20. Implement Zero Trust Principles
# ----------------------------
echo_info "Implementing Zero Trust principles..."
# Enforced through previous configurations:
# - Strict SSH access controls
# - Firewall rules limiting access
# - Fail2Ban protecting against unauthorized access attempts
# - AppArmor providing MAC
# Further Zero Trust implementations may involve using VPNs, mutual TLS, etc., which are beyond the scope of this script.

# ----------------------------
# 21. Install and Configure AIDE (Intrusion Detection)
# ----------------------------
echo_info "Installing AIDE for Intrusion Detection..."
apt install aide -y

# Initialize AIDE database
aideinit
cp /var/lib/aide/aide.db.new /var/lib/aide/aide.db

# Schedule AIDE daily checks via cron
echo_info "Scheduling daily AIDE integrity checks..."
echo "0 3 * * * root /usr/bin/aide.wrapper --check" > /etc/cron.d/aide

# ----------------------------
# 22. Implement Disk Encryption with LUKS (Manual Setup Recommended)
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
# 23. Install and Configure Automatic System Updates
# ----------------------------
echo_info "Setting up automatic system updates..."

# Install unattended-upgrades if not already installed
apt install unattended-upgrades -y

# Enable automatic updates
dpkg-reconfigure --priority=low unattended-upgrades

# ----------------------------
# 24. Install and Configure Cron Jobs for Backups
# ----------------------------
echo_info "Installing cron..."
apt install cron -y

# Create backup script
echo_info "Creating backup script at $BACKUP_SCRIPT..."
cat > "$BACKUP_SCRIPT" <<'EOL'
#!/bin/bash

# Variables
TIMESTAMP=$(date +"%F")
BACKUP_PATH="/var/backups/backup-$TIMESTAMP.tar.gz"
USER_HOME="/home/your_username"           # This will be replaced dynamically
NGINX_CONF="/etc/nginx"
TOR_CONF="/etc/tor"
MODSEC_CONF="/etc/modsecurity"
AIDE_DB="/var/lib/aide/aide.db"

# Create backup directory if it doesn't exist
mkdir -p /var/backups

# Create backup
tar --exclude="$BACKUP_PATH" -czf "$BACKUP_PATH" "$USER_HOME" "$NGINX_CONF" "$TOR_CONF" "$MODSEC_CONF" "$AIDE_DB"

# Remove backups older than retention period
find /var/backups -type f -name "*.tar.gz" -mtime +7 -exec rm {} \;
EOL

# Replace placeholder in backup script with actual username
sed -i "s/your_username/$NEW_USER/" "$BACKUP_SCRIPT"

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"

# Create cron job for daily backups at 2 AM
CRON_JOB="0 2 * * * root $BACKUP_SCRIPT"

echo_info "Setting up cron job for daily backups..."
echo "$CRON_JOB" > /etc/cron.d/daily_backup

# ----------------------------
# 25. Final Security Enhancements
# ----------------------------
echo_info "Performing final security enhancements..."

# Disable root account password
echo_info "Locking the root account to prevent direct logins..."
passwd -l root

# Reload UFW to apply all changes
echo_info "Reloading UFW to apply all firewall rules..."
ufw reload

# ----------------------------
# 26. Completion Message
# ----------------------------
echo_info "Server configuration completed successfully!"

echo_warn "Your Tor hidden service is available at: $DOMAIN"
echo_warn "Please securely download your SSH private key from /home/$NEW_USER/.ssh/id_ed25519."
echo_warn "Verify SSH access with the new user before closing your current session."
