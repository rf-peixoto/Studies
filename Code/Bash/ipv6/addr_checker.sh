#!/bin/bash

# Colors
RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
CYAN="\033[1;36m"
RESET="\033[0m"

echo -e "${CYAN}Scanning IPv6 Addresses...${RESET}"

# Get IPv6 addresses and their interfaces
interfaces=$(ip -6 a | awk '/^[0-9]+:/ {iface=$2} /inet6/ {print iface, $2}' | sed 's/://g')

declare -A ipv6_map
for line in $interfaces; do
    iface=$(echo "$line" | awk '{print $1}')
    ip=$(echo "$line" | awk '{print $2}')
    ipv6_map["$iface"]+="$ip "
done

# Display results
for iface in "${!ipv6_map[@]}"; do
    echo -e "${BLUE}$iface:${RESET} ${YELLOW}${ipv6_map[$iface]}${RESET}"
done

# Function to check reachability
test_ipv6() {
    ip="$1"
    
    # Test external reachability
    if ping6 -c 1 -W 1 "$ip" &> /dev/null; then
        echo -e "${GREEN}[++] Reachable (Public/External): $ip${RESET}"
    fi

    # Test local (LAN) reachability
    if ping6 -c 1 -W 1 -I "$(ip route get 8.8.8.8 | awk '{print $5}')" "$ip" &> /dev/null; then
        echo -e "${YELLOW}[+] Reachable (Local/LAN): $ip${RESET}"
    fi
}

echo -e "\n${CYAN}Testing IPv6 Addresses...${RESET}"

# Iterate over found IPv6 addresses
for iface in "${!ipv6_map[@]}"; do
    for ip in ${ipv6_map[$iface]}; do
        if [[ $ip =~ ^fe80:: ]]; then
            continue # Skip link-local addresses
        fi
        test_ipv6 "$ip"
    done
done

echo -e "${CYAN}Done.${RESET}"
