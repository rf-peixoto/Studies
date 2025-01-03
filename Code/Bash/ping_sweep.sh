#!/bin/bash
host=$1

for ip in $(seq 1 254)
do
  ping -w 1 -c 1 $host.$ip | grep "64 bytes";
done

# Or:
# fping -a -g 127.0.0.0/24
