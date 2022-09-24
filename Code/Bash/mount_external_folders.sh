# Check:
cat /etc/exports

# Check from outside:
showmount -e [IP]

# Mount:
mount -o rw,vers=2 [IP]:/path /local/path

# Auto:
host $1 | head -n 1 | cut -d " " -f 4 | showmount -e
