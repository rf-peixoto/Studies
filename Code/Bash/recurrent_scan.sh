#!/bin/bash

watch -n 86400 sudo nmap -sV -Pn -f --data-length 16 --script=vuln,malware -D RND:16 $1 -oX scans/$(date +"%d%m%Y").xml
