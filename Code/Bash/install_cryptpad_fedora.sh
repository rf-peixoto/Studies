#!/bin/bash

set -e

# Function to prompt for user input with default
prompt_default() {
    local PROMPT="$1"
    local DEFAULT="$2"
    read -p "$PROMPT [$DEFAULT]: " INPUT
    echo "${INPUT:-$DEFAULT}"
}

echo "[*] CryptPad Installation Script (Isolated via Podman)"
echo "--------------------------------------------------------"

# System checks
if ! grep -qi "fedora" /etc/os-release; then
    echo "[!] This script is designed for Fedora Linux only."
    exit 1
fi

# Update system
echo "[*] Updating system..."
sudo dnf update -y

# Install required packages
echo "[*] Installing dependencies..."
sudo dnf install -y podman git nodejs npm iptables

# User setup
CP_USER=$(prompt_default "Enter username to run CryptPad" "cryptpad")
if ! id "$CP_USER" &>/dev/null; then
    echo "[*] Creating user $CP_USER..."
    sudo useradd -m -s /bin/bash "$CP_USER"
fi

# Base directory
BASE_DIR="/home/$CP_USER/cryptpad"
sudo -u "$CP_USER" mkdir -p "$BASE_DIR"

# Clone repo
echo "[*] Cloning CryptPad repository..."
sudo -u "$CP_USER" git clone https://github.com/xwiki-labs/cryptpad.git "$BASE_DIR"

# Podman container creation
echo "[*] Building Podman container..."
cat <<EOF | sudo -u "$CP_USER" tee "$BASE_DIR/Containerfile"
FROM fedora:latest
RUN dnf install -y git nodejs npm && dnf clean all
WORKDIR /opt/cryptpad
COPY . /opt/cryptpad
RUN npm install && npm run build
CMD ["node", "server.js"]
EOF

cd "$BASE_DIR"
sudo -u "$CP_USER" podman build -t cryptpad-instance .

# Configuration setup
echo "[*] Configuring CryptPad instance..."

INSTANCE_NAME=$(prompt_default "Enter instance name" "My CryptPad")
INSTANCE_DESC=$(prompt_default "Enter instance description" "Encrypted collaborative workspace")
ENABLE_APPS=$(prompt_default "Enable all applications? (yes/no)" "yes")
REGISTRATION=$(prompt_default "Allow user registration? (yes/no)" "no")
GUEST_ACCESS=$(prompt_default "Allow guest access? (yes/no)" "no")
REQUIRE_2FA=$(prompt_default "Require 2FA for all users? (yes/no)" "yes")
MIN_PASS_LENGTH=$(prompt_default "Minimum password length" "16")
LOGIN_SALT=$(openssl rand -hex 16)

CONFIG_DIR="$BASE_DIR/customize"
sudo -u "$CP_USER" mkdir -p "$CONFIG_DIR"

cat <<EOF | sudo -u "$CP_USER" tee "$CONFIG_DIR/application_config.js"
AppConfig.instanceName = "$INSTANCE_NAME";
AppConfig.instanceDescription = "$INSTANCE_DESC";
AppConfig.minimumPasswordLength = $MIN_PASS_LENGTH;
AppConfig.loginSalt = "$LOGIN_SALT";
$( [ "$REGISTRATION" == "no" ] && echo "AppConfig.allowRegistration = false;" )
$( [ "$GUEST_ACCESS" == "no" ] && echo "AppConfig.registeredOnlyTypes = AppConfig.availablePadTypes;" )
$( [ "$REQUIRE_2FA" == "yes" ] && echo "AppConfig.enforceTotp = true;" )
EOF

# Podman container execution
echo "[*] Running Podman container..."
sudo -u "$CP_USER" podman run -d \
    --name cryptpad_container \
    --restart=always \
    -v "$BASE_DIR":/opt/cryptpad:Z \
    -p 3000:3000 \
    cryptpad-instance

# Generate systemd service
echo "[*] Creating systemd service..."
sudo -u "$CP_USER" podman generate systemd --name cryptpad_container --files --restart-policy=always
sudo mv container-cryptpad_container.service /etc/systemd/system/
sudo systemctl daemon-reexec
sudo systemctl enable --now container-cryptpad_container.service

# Firewall rules
echo "[*] Configuring firewall rules..."
sudo iptables -I INPUT -p tcp --dport 3000 -j ACCEPT
sudo iptables-save | sudo tee /etc/sysconfig/iptables

echo "--------------------------------------------------------"
echo "[+] CryptPad deployed at http://localhost:3000"
echo "[+] Admin setup available on first access"
