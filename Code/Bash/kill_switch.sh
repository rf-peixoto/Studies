#!/bin/bash
# sudo dnf install NetworkManager smartmontools util-linux -y

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for 'yes' argument to skip confirmation
if [[ " $* " =~ " -y " || " $* " =~ " --yes " || " $* " =~ " yes " ]]; then
    AUTO_CONFIRM=true
else
    AUTO_CONFIRM=false
fi

# Warning before running the script
echo -e "${RED}WARNING: This script will permanently erase most data from your system. Run at your own risk.${NC}"
echo -e "${YELLOW}Please ensure that all data has been backed up and drive encryption is considered before proceeding.${NC}"

# Prompt user to continue if not auto confirmed
if [ "$AUTO_CONFIRM" = false ]; then
    read -p "Are you sure you want to proceed? (yes/no) " response
    if [[ "$response" != "yes" ]]; then
        echo -e "${RED}Exit: User terminated the process.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✔ Starting the wipe process...${NC}"

# System integrity check
if [ ! -f /bin/bash ] || [ ! -f /usr/bin/sudo ]; then
    echo -e "${RED}✖ System integrity check failed. Critical binaries are missing.${NC}"
    exit 1
fi

# Check and list all drives health
echo -e "${YELLOW}Checking all drives' health...${NC}"
for dev in /dev/sd[a-z]; do
    health=$(sudo smartctl -H $dev | grep "PASSED" || echo "FAIL")
    if [[ $health == *"FAIL"* ]]; then
        echo -e "${RED}✖ Drive $dev may be failing.${NC}"
    else
        echo -e "${GREEN}✔ Drive $dev is healthy.${NC}"
    fi
done

# Kill internet connection
nmcli networking off && echo -e "${GREEN}✔ Internet connection disabled.${NC}" || echo -e "${RED}✖ Failed to disable internet connection.${NC}"

# Remove all known networks (prevent reconnection)
nmcli --fields UUID con show | tail -n +2 | awk '{print $1}' | xargs nmcli con delete uuid && echo -e "${GREEN}✔ Known networks removed.${NC}" || echo -e "${RED}✖ Failed to remove known networks.${NC}"

# Wipe all user data, user configuration, databases, virtual machines, and media
rm -rf /home/* && echo -e "${GREEN}✔ User data and configurations wiped.${NC}" || echo -e "${RED}✖ Failed to wipe user data and configurations.${NC}"

# Clear all system logs
rm -rf /var/log/* && echo -e "${GREEN}✔ System logs cleared.${NC}" || echo -e "${RED}✖ Failed to clear system logs.${NC}"

# Wipe package manager caches
apt-get clean && yum clean all && echo -e "${GREEN}✔ Package manager caches cleared.${NC}" || echo -e "${RED}✖ Failed to clear package manager caches.${NC}"

# Wipe filesystem signatures
for dev in /dev/sd[a-z]; do
    wipefs -a $dev && echo -e "${GREEN}✔ Wiped filesystem metadata from $dev.${NC}" || echo -e "${RED}✖ Failed to wipe filesystem metadata from $dev.${NC}"
done

# Secure erase for SSDs using blkdiscard
for ssd in $(lsblk -d -o name,type | grep 'disk' | awk '{print $1}'); do
    blkdiscard /dev/$ssd && echo -e "${GREEN}✔ Securely erased $ssd.${NC}" || echo -e "${RED}✖ Failed to securely erase $ssd.${NC}"
done

# Delete all users but the root
awk -F':' '{ if ($3 >= 1000) print $1 }' /etc/passwd | xargs -I {} userdel -r {} && echo -e "${GREEN}✔ Non-root users deleted.${NC}" || echo -e "${RED}✖ Failed to delete non-root users.${NC}"

# Wipe terminal history
history -c && rm ~/.bash_history && echo -e "${GREEN}✔ Terminal history wiped.${NC}" || echo -e "${RED}✖ Failed to wipe terminal history.${NC}"

# Identify and wipe swap using parallel jobs
cat /proc/swaps | awk '{if (NR>1) print $1}' | xargs -P 0 -I {} bash -c '{
    swapoff {} && dd if=/dev/zero of={} bs=1M && mkswap {} && echo -e "${GREEN}✔ Swap wiped on {}.${NC}" || echo -e "${RED}✖ Failed to wipe swap on {}.${NC}"
}'

# Clear and reset the bootloader
BOOT_DEV=$(lsblk -no pkname $(findmnt / -o source -n))
dd if=/dev/zero of=/dev/$BOOT_DEV bs=512 count=1 && echo -e "${GREEN}✔ Bootloader reset.${NC}" || echo -e "${RED}✖ Failed to reset bootloader.${NC}"

# Reboot the machine
echo -e "${GREEN}✔ Rebooting the system...${NC}"
reboot
