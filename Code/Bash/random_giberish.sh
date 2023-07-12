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
