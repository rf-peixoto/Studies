#!/bin/bash

########################################
# Decrypt *.enc Files in User Home Dirs
########################################

# Color definitions
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
RESET="\033[0m"

# Hardcoded decryption password
PASSWORD="HardC0dedExample"

# Print banner
echo -e "${GREEN}========================================="
echo -e "      Decrypting Original Home Files      "
echo -e "=========================================${RESET}"

# Function: decrypt_files_in_directory
# Recursively finds and decrypts all *.enc files in the specified directory
decrypt_files_in_directory() {
    local dir_path="$1"
    echo -e "${BLUE}Scanning for .enc files in: ${dir_path}${RESET}"

    # Find all .enc files under this directory
    find "${dir_path}" -type f -name "*.enc" | while read -r enc_file; do
        # Original file name is the same but without .enc extension
        local original_file="${enc_file%.enc}"

        echo -e "${YELLOW}Decrypting: ${enc_file}${RESET}"
        # Perform AES-256-CBC decryption
        openssl enc -d -aes-256-cbc \
            -in "${enc_file}" \
            -out "${original_file}" \
            -pass pass:"${PASSWORD}" 2>/dev/null

        if [ $? -ne 0 ]; then
            echo -e "${RED}Error decrypting file: ${enc_file}${RESET}"
        else
            echo -e "${GREEN}Decrypted file restored: ${original_file}${RESET}"
            # Remove the .enc file after successful decryption
            rm -f "${enc_file}"
        fi
    done
}

########################################
# MAIN SCRIPT LOGIC
########################################
if [ "$(id -u)" -eq 0 ]; then
    # Script is running as root, decrypt all users' homes plus /root
    echo -e "${BLUE}Running as root: Decrypting all user home directories and /root...${RESET}"

    # Decrypt in /home/*
    for user_home in /home/*; do
        if [ -d "${user_home}" ]; then
            decrypt_files_in_directory "${user_home}"
        fi
    done

    # Also handle /root, if it exists
    if [ -d "/root" ]; then
        decrypt_files_in_directory "/root"
    fi
else
    # Running as a non-root user: only decrypt the current user's home folder
    current_user="$(whoami)"
    home_dir="/home/${current_user}"

    echo -e "${BLUE}Running as user: ${current_user}${RESET}"

    if [ -d "${home_dir}" ]; then
        decrypt_files_in_directory "${home_dir}"
    else
        echo -e "${RED}Error: Home directory not found for user ${current_user}.${RESET}"
        exit 1
    fi
fi

echo -e "${GREEN}Decryption process complete. All *.enc files have been processed.${RESET}"
exit 0
