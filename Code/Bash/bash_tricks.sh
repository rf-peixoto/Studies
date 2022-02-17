# Define variable:
export varname="value"
echo $varname

# Get actual PID:
echo "$$"

# Check env vars:
env

# Nmap Host Scanning:
nmap -sn 127.0.0.1/24 -oG output.txt

# Try to Bypass IDS/IPS:
nmap -v -D RND:64 -sV -T2 --top-ports=50 --open

# Disable bash log in this session:
unset HITSFILE #.bash_history


# Change ELF banner with bless:
# 1) Find bin with.
whereis [bin] # Ex: whereis sshd
# You can check it with: strings [bin]
# 2) Open ELF with bless:;
bless [bin]
# Search banner by string and save.
# Save in original folder.
# Done. :)

# Change Linux Default TTL:
/proc/sys/net/ipv4/ip_default_ttl # 

# Check subfolders size:
du -h -max-depth=2
