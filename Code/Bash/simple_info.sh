#!/usr/bin/env bash

# ===== System Information Script =====

echo "========================================"
echo "           SYSTEM INFORMATION           "
echo "========================================"
echo

# --- Host & OS ---
echo ">>> Host & OS"
echo "Hostname       : $(hostname)"
echo "OS             : $(uname -o 2>/dev/null || echo "Unknown")"
echo "Kernel         : $(uname -r)"
echo "Architecture   : $(uname -m)"
echo "Uptime         : $(uptime -p)"
echo

# --- CPU ---
echo ">>> CPU"
CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs)
CPU_CORES=$(nproc)
echo "Model          : ${CPU_MODEL:-Unknown}"
echo "Cores          : $CPU_CORES"
echo

# --- Memory ---
echo ">>> Memory (RAM)"
read TOTAL USED FREE <<< $(free -m | awk '/^Mem:/ {print $2, $3, $4}')
PERCENT_USED=$(awk "BEGIN {printf \"%.2f\", ($USED/$TOTAL)*100}")
echo "Total          : ${TOTAL} MB"
echo "Used           : ${USED} MB"
echo "Free           : ${FREE} MB"
echo "Usage          : ${PERCENT_USED}%"
echo

# --- Disk ---
echo ">>> Disk Usage"
df -h --output=source,size,used,avail,pcent,target | grep -v tmpfs | grep -v udev
echo

# --- Network ---
echo ">>> Network"
echo "IP Addresses:"
ip -brief addr show | awk '{print $1, $3}'
echo
echo "Default Gateway:"
ip route | awk '/default/ {print $3}'
echo

echo "========================================"
