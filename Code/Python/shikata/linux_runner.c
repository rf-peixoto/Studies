// gcc -fno-stack-protector -z execstack -o runner runner.c
//./runner encoded.bin

#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

typedef void (*shellcode_func)();

int main(int argc, char *argv[]) {
    if(argc != 2) {
        fprintf(stderr, "Usage: %s <encoded_bin>\n", argv[0]);
        exit(EXIT_FAILURE);
    }
    
    // Open the encoded binary file.
    int fd = open(argv[1], O_RDONLY);
    if(fd < 0) {
        perror("open");
        exit(EXIT_FAILURE);
    }
    
    // Get the file size.
    off_t size = lseek(fd, 0, SEEK_END);
    lseek(fd, 0, SEEK_SET);
    
    // Allocate an executable memory region.
    void *exec_mem = mmap(NULL, size, PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if(exec_mem == MAP_FAILED) {
        perror("mmap");
        exit(EXIT_FAILURE);
    }
    
    // Read the file into memory.
    if(read(fd, exec_mem, size) != size) {
        perror("read");
        exit(EXIT_FAILURE);
    }
    close(fd);
    
    // Cast the memory to a function and call it.
    shellcode_func sc = (shellcode_func)exec_mem;
    sc();
    
    // Unmap the memory.
    munmap(exec_mem, size);
    
    return 0;
}
