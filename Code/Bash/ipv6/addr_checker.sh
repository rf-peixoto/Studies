#!/bin/bash

# Colors
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

# Function to check reachability
test_ipv6() {
    local ip="$1"
    local iface="$2"
    local external_status="${RED}Fail${RESET}"
    local local_status="${RED}Fail${RESET}"

    # Test external reachability
    if ping6 -c 1 -W 1 "$ip" &>/dev/null; then
        external_status="${GREEN}Success${RESET}"
    fi

    # Test local (LAN) reachability
    if ping6 -c 1 -W 1 -I "$iface" "$ip" &>/dev/null; then
        local_status="${YELLOW}Success${RESET}"
    fi

    echo -e "\t${CYAN}$ip${RESET}: Ext: $external_status | LAN: $local_status"
}

echo -e "\n${CYAN}Testing IPv6 Addresses...${RESET}"

# Iterate over interfaces and IPv6 addresses
for iface in "${!ipv6_map[@]}"; do
    echo -e "${CYAN}$iface:${RESET}"
    for ip in ${ipv6_map[$iface]}; do
        # Skip link-local addresses (fe80::/10)
        [[ $ip =~ ^fe80:: ]] && continue
        test_ipv6 "$ip" "$iface"
    done
done

echo -e "${CYAN}Done.${RESET}"
