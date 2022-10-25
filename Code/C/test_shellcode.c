#include <stdio.h>
#include <string.h>

unsigned char shell[] = "Put your shellcode here.";

int main() {
  printf("Shellcode size: %zu\n", strlen(shell));
  int (*ret)() = (int(*)())shell;
  ret();
}
