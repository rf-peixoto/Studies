_start:
add r0, pc, #12
mov r1, #0
mov r2, #0
mov r7, #11 ;execve system call ID
svc #1
.ascii "/bin/sh\0"
