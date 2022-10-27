#include <stdio.h>

// Exploit by overflowing the buffer and using the %p mark
// to get the actual memory address.

int main () {
  char buffer [8];
  gets(buffer);
  printf(buffer);
  printf("\n");
}
