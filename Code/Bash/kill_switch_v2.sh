#!/bin/bash

# Kill Switch Script for Secure Data Wiping on Linux

# Required Packages: NetworkManager, smartmontools, cronie, util-linux, coreutils, hdparm
# Install missing packages if necessary
REQUIRED_PKGS=(NetworkManager smartmontools cronie util-linux coreutils hdparm)

# Function to check and install missing packages
install_missing_packages() {
    MISSING_PKGS=()
    for pkg in "${REQUIRED_PKGS[@]}"; do
        if ! rpm -q $pkg &>/dev/null; then
            MISSING_PKGS+=($pkg)
        fi
    done
    if [ ${#MISSING_PKGS[@]} -ne 0 ]; then
        echo -e "${YELLOW}Installing missing packages: ${MISSING_PKGS[@]}...${NC}"
        sudo dnf install -y "${MISSING_PKGS[@]}"
    fi
}

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}This script must be run as root. Please run with sudo or as root user.${NC}"
    exit 1
fi

# Auto-confirmation flag
AUTO_CONFIRM=false

# Function to display usage
usage() {
    echo "Usage: $0 [--yes|-y]"
    exit 1
}

# Parse command-line arguments
for arg in "$@"; do
    case $arg in
        -y|--yes|yes)
            AUTO_CONFIRM=true
            shift
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            # Unknown option
            usage
            ;;
    esac
done

# Warning before running the script
echo -e "${RED}WARNING: This script will permanently erase data from your system.${NC}"
echo -e "${RED}Ensure all important data is backed up before proceeding.${NC}"

# Prompt user to continue if not auto-confirmed
if [ "$AUTO_CONFIRM" = false ]; then
    read -p "Are you absolutely sure you want to proceed? This action cannot be undone. (yes/no) " response
    if [[ "$response" != "yes" ]]; then
        echo -e "${RED}Process terminated by user.${NC}"
        exit 1
    fi
fi

# Install missing packages
install_missing_packages

echo -e "${GREEN}✔ Starting the data wipe process...${NC}"

# System Integrity Check
if [ ! -f /bin/bash ] || [ ! -f /usr/bin/sudo ]; then
    echo -e "${RED}✖ Critical system binaries are missing. Aborting.${NC}"
    exit 1
fi

# Disable Networking
echo -e "${GREEN}Disabling all network interfaces...${NC}"
nmcli networking off
for iface in $(ls /sys/class/net/ | grep -v lo); do
    ip link set $iface down
done
echo -e "${GREEN}✔ Network interfaces disabled.${NC}"

# Flush iptables rules
echo -e "${GREEN}Flushing firewall rules...${NC}"
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
iptables -P INPUT DROP
iptables -P OUTPUT DROP
iptables -P FORWARD DROP
echo -e "${GREEN}✔ Firewall rules flushed.${NC}"

# Check and list all drives' health
echo -e "${GREEN}Checking all drives' health...${NC}"
for dev in /dev/sd[a-z] /dev/nvme[0-9]n[0-9]; do
    if [ -b "$dev" ]; then
        health=$(smartctl -H $dev | grep "SMART overall-health self-assessment test result" || echo "FAIL")
        if [[ $health == *"PASSED"* ]]; then
            echo -e "${GREEN}✔ Drive $dev is healthy.${NC}"
        else
            echo -e "${YELLOW}⚠ Drive $dev may have issues.${NC}"
        fi
    fi
done

# Unmount any mounted directories in /home
echo -e "${GREEN}Unmounting any mounted directories in /home...${NC}"
mount | grep '^/dev' | grep '/home' | awk '{print $3}' | xargs -r umount -l
echo -e "${GREEN}✔ Mounted directories in /home unmounted.${NC}"

# Securely delete user data
echo -e "${GREEN}Securely deleting user data in /home...${NC}"
if [ -d /home ]; then
    find /home/ -mindepth 1 -exec shred -uvz {} \; 2>/dev/null
    find /home/ -mindepth 1 -type d -exec rm -rf {} \; 2>/dev/null
    echo -e "${GREEN}✔ User data in /home securely deleted.${NC}"
else
    echo -e "${YELLOW}⚠ /home directory not found.${NC}"
fi

# Stop system logging services
echo -e "${GREEN}Stopping system logging services...${NC}"
systemctl stop rsyslog 2>/dev/null
systemctl stop systemd-journald 2>/dev/null
echo -e "${GREEN}✔ System logging services stopped.${NC}"

# Clear journal logs
echo -e "${GREEN}Clearing system logs...${NC}"
journalctl --rotate
journalctl --vacuum-time=1s
find /var/log -type f -exec shred -uvz {} \; 2>/dev/null
echo -e "${GREEN}✔ System logs cleared.${NC}"

# Wipe package manager caches
echo -e "${GREEN}Cleaning package manager caches...${NC}"
dnf clean all
echo -e "${GREEN}✔ Package manager caches cleaned.${NC}"

# Delete all users except root and system users
echo -e "${GREEN}Deleting non-root user accounts...${NC}"
for user in $(awk -F':' '{ if ($3 >= 1000 && $1 != "nobody") print $1 }' /etc/passwd); do
    pkill -KILL -u $user 2>/dev/null
    userdel -r $user 2>/dev/null
    shred -uvz /home/$user 2>/dev/null
    echo -e "${GREEN}✔ User account $user deleted.${NC}"
done

# Wipe root's histories
echo -e "${GREEN}Wiping root's shell and application histories...${NC}"
shred -uvz /root/.bash_history /root/.zsh_history /root/.python_history 2>/dev/null
echo -e "${GREEN}✔ Root's histories wiped.${NC}"

# Clear temporary directories securely
echo -e "${GREEN}Clearing temporary directories...${NC}"
find /tmp/ /var/tmp/ -type f -exec shred -uvz {} \; 2>/dev/null
find /tmp/ /var/tmp/ -mindepth 1 -type d -exec rm -rf {} \; 2>/dev/null
echo -e "${GREEN}✔ Temporary directories cleared.${NC}"

# Clear cron jobs for all users
echo -e "${GREEN}Clearing cron jobs for all users...${NC}"
for user in $(cut -f1 -d: /etc/passwd); do
    crontab -r -u $user 2>/dev/null
done
echo -e "${GREEN}✔ Cron jobs cleared.${NC}"

# Wipe swap partitions
echo -e "${GREEN}Disabling and wiping swap partitions...${NC}"
swapoff -a
for swapdev in $(cat /proc/swaps | awk '{if (NR>1) print $1}'); do
    if [ -b "$swapdev" ]; then
        shred -v -n 1 $swapdev
        mkswap $swapdev
        echo -e "${GREEN}✔ Swap partition $swapdev wiped.${NC}"
    fi
done

# Identify boot device
BOOT_DEV=$(lsblk -no pkname $(findmnt / -o source -n) | head -n1)

# Confirm before overwriting the boot device
echo -e "${RED}This will overwrite the entire boot device ($BOOT_DEV), rendering the system unbootable.${NC}"
read -p "Are you sure you want to proceed with wiping the boot device? (yes/no) " boot_response
if [[ "$boot_response" == "yes" ]]; then
    echo -e "${GREEN}Overwriting boot device /dev/$BOOT_DEV...${NC}"
    shred -v -n 1 /dev/$BOOT_DEV
    echo -e "${GREEN}✔ Boot device /dev/$BOOT_DEV securely erased.${NC}"
else
    echo -e "${YELLOW}Skipping boot device wiping.${NC}"
fi

# Power off the machine
echo -e "${GREEN}Data wipe process completed.${NC}"
echo -e "${GREEN}The system will now power off.${NC}"
sleep 5
poweroff
