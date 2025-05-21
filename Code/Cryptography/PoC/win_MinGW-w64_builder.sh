# Install compiler and Windows SDK shfolder support
pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-mingw-w64-headers

# Compile linking against Shell32 and Shfolder for SHGetFolderPath
x86_64-w64-mingw32-gcc -std=c11 \
    encryptor.c wip_trivium_2304.c \
    -O2 \
    -lshfolder -lshell32 \
    -o encryptor.exe
