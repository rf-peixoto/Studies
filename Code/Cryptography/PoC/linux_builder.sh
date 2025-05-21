# Install dependencies (if not already present)
sudo apt-get install build-essential

# Compile with POSIX threads and X/Open feature test macro
gcc -std=c11 -D_XOPEN_SOURCE=500 \
    encryptor.c wip_trivium_2304.c \
    -O2 -lpthread -o encryptor
