#!/bin/bash

# =============================================================================
# Script: setup_tor_monitoring.sh
# Description: Automates the setup of multiple Dockerized Tor nodes for
#              monitoring malicious traffic on the Tor network.
# =============================================================================

set -e

# ---------------------------- Helper Functions ----------------------------

# Function to print messages
print_message() {
    echo "====================================================================="
    echo "$1"
    echo "====================================================================="
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ---------------------------- Pre-requisite Checks ----------------------------

print_message "Starting Tor Monitoring Setup"

# Check for sudo privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo or as root."
    exit 1
fi

# Update package list
print_message "Updating package lists..."
apt-get update -y

# Install necessary packages
install_packages() {
    PACKAGE_NAME=$1
    if ! dpkg -l | grep -qw "$PACKAGE_NAME"; then
        echo "Installing $PACKAGE_NAME..."
        apt-get install -y "$PACKAGE_NAME"
    else
        echo "$PACKAGE_NAME is already installed."
    fi
}

# Install Git (optional)
install_packages "git"

# ---------------------------- Install Docker ----------------------------

if ! command_exists docker; then
    print_message "Docker not found. Installing Docker..."

    # Install prerequisites
    apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release

    # Add Docker’s official GPG key
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    # Set up the Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
      $(lsb_release -cs) stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Update package list and install Docker
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add current user to docker group (optional)
    # Uncomment the following lines if you want to run docker without sudo
    # USERNAME=$(logname)
    # usermod -aG docker "$USERNAME"
    # echo "Added $USERNAME to docker group. Please log out and log back in for changes to take effect."
else
    echo "Docker is already installed."
fi

# Verify Docker installation
if ! command_exists docker; then
    echo "Docker installation failed. Exiting."
    exit 1
fi

# ---------------------------- Install Docker Compose ----------------------------

if ! command_exists docker-compose; then
    print_message "Docker Compose not found. Installing Docker Compose..."

    # Get the latest version of Docker Compose
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/')

    # Download Docker Compose binary
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

    # Apply executable permissions
    chmod +x /usr/local/bin/docker-compose

    # Create a symlink
    ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose

    echo "Docker Compose version $(docker-compose --version) installed."
else
    echo "Docker Compose is already installed."
fi

# Verify Docker Compose installation
if ! command_exists docker-compose; then
    echo "Docker Compose installation failed. Exiting."
    exit 1
fi

# ---------------------------- User Configuration ----------------------------

# Prompt user for the number of Tor nodes
read -p "Enter the number of Tor nodes you wish to deploy (e.g., 3): " NUM_NODES

# Validate input
if ! [[ "$NUM_NODES" =~ ^[1-9][0-9]*$ ]]; then
    echo "Invalid number of nodes. Please enter a positive integer."
    exit 1
fi

# ---------------------------- Setup Directory Structure ----------------------------

PROJECT_DIR="$HOME/tor-monitoring"
TOR_NODE_DIR="$PROJECT_DIR/tor-node"
LOGS_DIR="$PROJECT_DIR/logs"

print_message "Setting up directory structure..."

mkdir -p "$TOR_NODE_DIR"
mkdir -p "$LOGS_DIR"

# ---------------------------- Create Dockerfile ----------------------------

print_message "Creating Dockerfile..."

cat > "$TOR_NODE_DIR/Dockerfile" <<EOF
FROM debian:stable-slim

# Install Tor
RUN apt-get update && \\
    apt-get install -y tor && \\
    rm -rf /var/lib/apt/lists/*

# Create directories for Tor data and logs
RUN mkdir -p /var/lib/tor && \\
    mkdir -p /var/log/tor

# Copy the Tor configuration file
COPY torrc /etc/tor/torrc

# Expose Tor ports
EXPOSE 9001 9030

# Set permissions
RUN chown -R debian-tor:debian-tor /var/lib/tor /var/log/tor

# Run Tor as the debian-tor user
USER debian-tor

# Start Tor
CMD ["tor"]
EOF

# ---------------------------- Create torrc Template ----------------------------

print_message "Creating torrc configuration template..."

cat > "$TOR_NODE_DIR/torrc" <<EOF
RunAsDaemon 1
SocksPort 0
ORPort __ORPORT__
DirPort __DIRPORT__
DataDirectory /var/lib/tor

# Log settings
Log notice file /var/log/tor/notices.log

# Relay configuration (customize as needed)
RelayBandwidthRate 100 KBytes
RelayBandwidthBurst 200 KBytes

# Exit policy (reject all exit traffic by default)
ExitPolicy reject *:*
EOF

# ---------------------------- Create docker-compose.yml ----------------------------

print_message "Generating docker-compose.yml..."

DOCKER_COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

cat > "$DOCKER_COMPOSE_FILE" <<EOF
version: '3.8'

services:
EOF

for i in $(seq 1 "$NUM_NODES"); do
    NODE_NAME="tor-node$i"
    HOST_ORPORT=$((9000 + i))
    HOST_DIRPORT=$((9030 + i))
    LOG_DIR="$LOGS_DIR/node$i"
    DATA_VOLUME="tor-node${i}-data"

    mkdir -p "$LOG_DIR"

    # Customize torrc for each node by replacing placeholders
    # Create a unique torrc for each node
    cat > "$TOR_NODE_DIR/torrc.node$i" <<EOL
RunAsDaemon 1
SocksPort 0
ORPort 9001
DirPort 9030
DataDirectory /var/lib/tor

# Log settings
Log notice file /var/log/tor/notices.log

# Relay configuration (customize as needed)
RelayBandwidthRate 100 KBytes
RelayBandwidthBurst 200 KBytes

# Exit policy (reject all exit traffic by default)
ExitPolicy reject *:*
EOF

    # Append service definition to docker-compose.yml
    cat >> "$DOCKER_COMPOSE_FILE" <<EOL
  $NODE_NAME:
    build: ./tor-node
    container_name: $NODE_NAME
    ports:
      - "${HOST_ORPORT}:9001"
      - "${HOST_DIRPORT}:9030"
    volumes:
      - ./logs/node$i:/var/log/tor
      - $DATA_VOLUME:/var/lib/tor
    restart: unless-stopped

EOL
done

# Add volumes section
echo "volumes:" >> "$DOCKER_COMPOSE_FILE"
for i in $(seq 1 "$NUM_NODES"); do
    echo "  tor-node${i}-data:" >> "$DOCKER_COMPOSE_FILE"
done

# ---------------------------- Modify torrc for Each Node ----------------------------

print_message "Configuring torrc for each Tor node..."

for i in $(seq 1 "$NUM_NODES"); do
    NODE_TORRC="$TOR_NODE_DIR/torrc.node$i"
    # Replace ORPort and DirPort with internal container ports if necessary
    # Currently, all nodes use the same internal ports (9001 and 9030)
    # Host ports are mapped uniquely
    # If you need unique internal ports, modify accordingly
    :
done

# ---------------------------- Create Project Script ----------------------------

# The Dockerfile copies a generic torrc; to have unique configurations per node,
# it's better to modify the Dockerfile or use environment variables.

# ---------------------------- Deploy Docker Containers ----------------------------

print_message "Deploying Docker containers with Docker Compose..."

cd "$PROJECT_DIR"

docker-compose up -d --build

# ---------------------------- Post-Setup Instructions ----------------------------

print_message "Tor Monitoring Setup Completed Successfully!"

echo ""
echo "====================================================================="
echo "Accessing Logs:"
echo "Logs for each Tor node are stored in the following directories:"
for i in $(seq 1 "$NUM_NODES"); do
    echo " - Node $i: $PROJECT_DIR/logs/node$i/notices.log"
done
echo ""
echo "You can monitor the logs using commands like:"
for i in $(seq 1 "$NUM_NODES"); do
    echo " - To tail logs for Node $i:"
    echo "    tail -f $PROJECT_DIR/logs/node$i/notices.log"
done
echo "====================================================================="
echo ""

# Optional: Provide instructions for stopping the containers
echo "To stop and remove the containers, run the following command in the project directory:"
echo "    docker-compose down"
echo ""

# Optional: Suggest how to add more nodes
echo "To add more Tor nodes, rerun the script with a higher number of nodes or manually update the docker-compose.yml file."
echo ""

# ---------------------------- End of Script ----------------------------
