#!/bin/bash

sudo nmap -sV -Pn -f --data-length 16 --script=vuln -D RND:16 $1 -T 2 -oG $1.txt
