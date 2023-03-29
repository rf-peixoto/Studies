#!/bin/bash
sudo nmap -n [IP] -sS -p 80,443 --script:http.enum.nse
