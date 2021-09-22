
# In seq: IP Block
for ip in $(seq 1 255); do host -t ptr "127.0.0.$ip";done
