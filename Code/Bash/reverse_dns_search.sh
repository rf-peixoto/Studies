
# In seq: IP Block
for ip in $(seq 1 255); do host -t ptr "127.0.0.$ip";done

# or dig -x IP +noall +short
# Ref: https://fabianlee.org/2023/03/24/bash-using-dig-for-reverse-dns-lookup-by-ip/
#prefix=192.168.1
#for i in $(seq 32 254); do echo "$prefix.$i,$(dig -x $prefix.$i +noall +short)"; done
