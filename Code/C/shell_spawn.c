#include <stdio.h>
int main()
    {
    char *args[2];
    args[0] = "/bin/sh";
    args[1] = NULL;
    execve("/bin/sh", args, NULL);
    return 0;
}
