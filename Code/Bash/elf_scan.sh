#!/bin/bash
file $1 > $1_scan.txt #General info
ldd $1 >> $1_scan.txt #Shared object dependencies. Ex: file.so
#ltrace $1 #libraries
#hexdump $1 #Dump hex
#strings $1 #Extract strings
readelf -h $1 >> $1_scan.txt
#objdump -d $1 #Disassembly
#strace $1 #System calls
nm $1 >> $1_scan.txt #Extract symbols
#gdb $1 #Debug
