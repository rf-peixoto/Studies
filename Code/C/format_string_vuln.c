#include <stdio.h>

// Exploit by overflowing the buffer and using the %p mark
// to get the actual memory address.

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

}
