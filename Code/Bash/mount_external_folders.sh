# Check:
cat /etc/exports

# Check from outside:
showmount -e [IP]

# Mount:
mount -o rw,vers=2 [IP]:/path /local/path
