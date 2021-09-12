while [ true ]; do head -n 100 /dev/urandom; sleep .1; done | hexdump -C
