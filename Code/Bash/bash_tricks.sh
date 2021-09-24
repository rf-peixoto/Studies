# Define variable:
export varname="value"
echo $varname

# Get actual PID:
echo "$$"

# Check env vars:
env

# Nmap Host Scanning:
nmap -sn 127.0.0.1/24 -oG output.txt
