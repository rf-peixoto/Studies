strace -ff -e trace=write -e write=1,2 -p $1
