#!/bin/bash

########################################
# Secure Backup and Encryption Script
########################################

# Color definitions
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
RESET="\033[0m"

# Print banner
echo -e "${GREEN}========================================="
echo -e "     Secure Backup & Encryption Script    "
echo -e "=========================================${RESET}"

# Prompt for password
echo -e "${YELLOW}Enter encryption password:${RESET}"
read -s PASSWORD
echo
echo -e "${YELLOW}Re-enter encryption password:${RESET}"
read -s PASSWORD_CONFIRM
echo
if [ "${PASSWORD}" != "${PASSWORD_CONFIRM}" ]; then
    echo -e "${RED}Error: Passwords do not match.${RESET}"
    exit 1
fi

# Function to handle encryption for a specific directory
encrypt_directory() {
    local dir_name="$1"

    echo -e "${YELLOW}Compressing directory: ${dir_name}${RESET}"
    # Compress in parallel with pigz
    tar -c "${dir_name}" 2>/dev/null | pigz -9 > "${dir_name}.tar.gz"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to archive ${dir_name}.${RESET}"
        return 1
    fi

    echo -e "${YELLOW}Encrypting archive: ${dir_name}.tar.gz${RESET}"
    openssl enc -aes-256-cbc -salt \
        -in "${dir_name}.tar.gz" \
        -out "${dir_name}.tar.gz.enc" \
        -pass pass:"${PASSWORD}" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Encryption failed for ${dir_name}.${RESET}"
        # Attempt to remove partially created files if needed
        rm -f "${dir_name}.tar.gz" 2>/dev/null
        rm -f "${dir_name}.tar.gz.enc" 2>/dev/null
        return 1
    fi

    echo -e "${YELLOW}Removing unencrypted archive: ${dir_name}.tar.gz${RESET}"
    rm -f "${dir_name}.tar.gz"

    return 0
}

# Function to remove shell history files for a specific directory securely
remove_history() {
    local dir_name="$1"

    echo -e "${YELLOW}Securely removing history in: ${dir_name}${RESET}"
    shred -u "${dir_name}/.bash_history" "${dir_name}/.zsh_history" 2>/dev/null
}

# Detect if script is running as root or non-root
if [ "$(id -u)" -eq 0 ]; then
    # Running as root: encrypt home folders for all users
    echo -e "${BLUE}Script executed as root. Encrypting all home directories...${RESET}"

    cd /home || {
        echo -e "${RED}Error: Failed to change directory to /home.${RESET}"
        exit 1
    }

    for user_dir in *; do
        if [ -d "${user_dir}" ]; then
            encrypt_directory "${user_dir}"
        fi
    done

    echo -e "${YELLOW}Securely removing root user's history...${RESET}"
    shred -u /root/.bash_history /root/.zsh_history 2>/dev/null

    echo -e "${YELLOW}Securely removing history for all user directories...${RESET}"
    for user_dir in *; do
        if [ -d "${user_dir}" ]; then
            remove_history "/home/${user_dir}"
        fi
    done
else
    # Running as non-root: encrypt only the current user's home folder
    current_user="$(whoami)"
    home_dir="/home/${current_user}"

    echo -e "${BLUE}Script executed as user: ${current_user}${RESET}"

    if [ ! -d "${home_dir}" ]; then
        echo -e "${RED}Error: Home directory for user ${current_user} not found.${RESET}"
        exit 1
    fi

    cd /home || {
        echo -e "${RED}Error: Failed to change directory to /home.${RESET}"
        exit 1
    }

    encrypt_directory "${current_user}"
    remove_history "${home_dir}"
fi

echo -e "${GREEN}Process complete. Encrypted archives are ready for transfer.${RESET}"
exit 0
