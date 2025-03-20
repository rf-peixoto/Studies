#!/bin/bash
# This script installs Tor and configures it as an exit node.
# DISCLAIMER: Operating a Tor exit node may have legal and operational implications.
# Ensure compliance with all applicable laws and regulations before proceeding.

# Update package lists and install Tor
sudo apt-get update
sudo apt-get install -y tor

# Backup the existing torrc file
sudo cp /etc/tor/torrc /etc/tor/torrc.backup

# Write a new torrc configuration for an exit node
sudo tee /etc/tor/torrc > /dev/null << 'EOF'
# Basic Tor configuration for an exit relay

# Run Tor as a daemon
RunAsDaemon 1

# Disable the SOCKS port (this relay does not provide client services)
SocksPort 0

# Set the ORPort for relay communications (adjust as needed)
ORPort 9001

# Advertise this relay as an exit node.
ExitRelay 1

# Define exit policies:
# Allow outbound traffic on ports 80 (HTTP) and 443 (HTTPS) only,
# then reject all other outbound traffic.
ExitPolicy accept *:80
ExitPolicy accept *:443
ExitPolicy reject *:*

# Logging configuration:
# Logs are saved to /var/log/tor/tor.log.
Log notice file /var/log/tor/tor.log
EOF

# Create the Tor log directory if it does not exist and set ownership
sudo mkdir -p /var/log/tor
sudo chown debian-tor:debian-tor /var/log/tor

# Restart Tor to apply the new configuration
sudo systemctl restart tor

echo "Tor exit node configuration complete. Logs are saved to /var/log/tor/tor.log."
