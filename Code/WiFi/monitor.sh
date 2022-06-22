#!/bin/bash

# $1 : interface

for i in {1..11}
do
  echo "\n[+] Ouvindo canal: $i\n"
  ifconfig $1 down
  iwconfig $1 channel $i
  iwconfig $1 mode Monitor
  ifconfig $1 up
  sleep 2
  tcpdump -vv -i $1 -c 10 | grep "Beacon" | awk '{print $12, - CH $24}'
  echo "\n"
done

