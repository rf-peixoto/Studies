#!/bin/bash

# Function to print section headers
print_section() {
  echo -e "\n=== $1 ==="
}

# Function to filter environment variables
filter_env() {
  env | grep -vE "^(HOME=|PWD=|USER=|LOGNAME=|SHELL=|TERM=|LANG=|SHLVL=|_=|PATH=|XDG_.*=|LS_COLORS=|MAIL=)"
}

# Function to filter and format running processes
filter_processes() {
  ps aux | awk '/(sshd|telnetd|rdesktop|ldapsearch|smbclient|<other relevant process keywords>)/ {print $2, $11, $1}'
}

# Log file path
log_file=~/Downloads/system_check.log

# Redirect script output to log file
exec > "$log_file" 2>&1

# Function to log messages to both console and log file
log() {
  echo "$1"
  echo "$1" >> "$log_file"
}

# Function to check for command availability and run it
check_command() {
  local command_name=$1
  if ! command -v "$command_name" &>/dev/null; then
    log "Error: $command_name not found."
    exit 1
  fi
}

# System Information
print_section "System Information"
distro=$(lsb_release -d | cut -f2-)
kernel=$(uname -r)
users=$(cut -d: -f1 /etc/passwd | sort)
log "Linux Distribution: $distro"
log "Kernel Version: $kernel"
log "Users: $users"

# Network and Remote Access
print_section "Network and Remote Access"
check_command dpkg
installed_vpn=$(dpkg -l | grep -i 'vpn\|remote' | awk '{print $2}')
log "Installed VPN and Remote Access Software: $installed_vpn"
log "Network Configuration:"
cat /etc/network/interfaces >> "$log_file"

# Check SSH, Telnet, RDP, AD, and other network connections
print_section "Network Connections"
log "SSH Connections:"
netstat -tn | grep -E '22'
log "Telnet Connections:"
netstat -tn | grep -E '23'
log "RDP Connections:"
netstat -tn | grep -E '3389'
log "Active Directory (AD) Connections:"
# Use a command or tool specific to your AD configuration to check AD connections.

# Filtered Running Processes
print_section "Filtered Running Processes"
check_command ps
filter_processes >> "$log_file"

# Firewall Rules
print_section "Firewall Rules"
check_command ufw
ufw_status=$(ufw status 2>/dev/null)
if [ -n "$ufw_status" ]; then
  log "$ufw_status"
else
  log "UFW is not installed."
fi

check_command iptables
iptables_rules=$(iptables -L)
log "iptables Rules:"
echo "$iptables_rules" >> "$log_file"

# Environment Variables
print_section "User Environment Variables"
filter_env >> "$log_file"

log "Script execution completed. Log saved to $log_file"
