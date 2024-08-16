#!/bin/bash

# Function to check if Tor service is running
check_tor() {
    if systemctl is-active --quiet tor; then
        echo "Tor service is running."
    else
        echo "Tor service is not running. Starting Tor..."
        sudo systemctl start tor
        if systemctl is-active --quiet tor; then
            echo "Tor service started successfully."
        else
            echo "Failed to start Tor service."
            exit 1
        fi
    fi
}

# Function to check Proxychains configuration
check_proxychains() {
    CONFIG_FILE="/etc/proxychains.conf"
    REQUIRED_CONFIG="socks4 127.0.0.1 9050"
    if grep -q "^$REQUIRED_CONFIG" "$CONFIG_FILE"; then
        echo "Proxychains is configured correctly."
    else
        echo "Proxychains configuration is incorrect. Fixing it..."
        if sudo sed -i "s/^#socks4 127.0.0.1 9050/$REQUIRED_CONFIG/" "$CONFIG_FILE"; then
            echo "Proxychains configuration fixed successfully."
        else
            echo "Failed to fix Proxychains configuration."
            exit 1
        fi
    fi
}

# Function to run a command on an onion site using Proxychains
run_command_on_onion_site() {
    ONION_SITE=$1
    COMMAND=$2

    echo "Running command on $ONION_SITE..."
    proxychains $COMMAND $ONION_SITE
}

# Main script execution
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <onion-site> <command>"
    exit 1
fi

ONION_SITE=$1
COMMAND=$2

check_tor
check_proxychains
run_command_on_onion_site $ONION_SITE "$COMMAND"
