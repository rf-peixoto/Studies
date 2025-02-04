#!/bin/bash

# Colors for readability
RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

echo -e "${CYAN}Scanning IPv6 Addresses...${RESET}"

# Extract IPv6 addresses per interface
declare -A ipv6_map

while IFS= read -r line; do
    if [[ $line =~ ^[0-9]+:\ ([a-zA-Z0-9]+): ]]; then
        iface="${BASH_REMATCH[1]}"
    elif [[ $line =~ inet6\ ([a-f0-9:]+)/[0-9]+ ]]; then
        ip="${BASH_REMATCH[1]}"
        ipv6_map["$iface"]+="$ip "
    fi
done < <(ip -6 a)

# Function to check LAN reachability
test_local_ipv6() {
    local ip="$1"
    local iface="$2"
    
    if ping6 -c 1 -W 1 -I "$iface" "$ip" &>/dev/null; then
        echo -e "\t${CYAN}$ip${RESET}: LAN: ${YELLOW}Reachable${RESET}"
    else
        echo -e "\t${CYAN}$ip${RESET}: LAN: ${RED}Not Reachable${RESET}"
    fi
}

# Function to check EXTERNAL reachability using an external pinging service
test_external_ipv6() {
    local ip="$1"

    # Test with an external service (Cloudflare or another public service)
    if curl -6 -s --max-time 3 "https://icanhazip.com" | grep -q "$ip"; then
        echo -e "\t${CYAN}$ip${RESET}: ${GREEN}Publicly Reachable (External)${RESET}"
    else
        echo -e "\t${CYAN}$ip${RESET}: ${RED}Not Publicly Accessible${RESET}"
    fi
}

echo -e "\n${CYAN}Testing IPv6 Addresses...${RESET}"

# Iterate over interfaces and IPv6 addresses
for iface in "${!ipv6_map[@]}"; do
    echo -e "${CYAN}$iface:${RESET}"
    for ip in ${ipv6_map[$iface]}; do
        # Skip link-local addresses (fe80::/10)
        [[ $ip =~ ^fe80:: ]] && continue
        test_local_ipv6 "$ip" "$iface"
        test_external_ipv6 "$ip"
    done
done

echo -e "${CYAN}Done.${RESET}"
