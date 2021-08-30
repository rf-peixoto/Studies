#!/bin/bash

if [ "$1" == "" ]
then
  echo "Usage: $0 \[Network. Ex: 10.0.0, 192.168.0\]"
else
  for ip in {1..255};
  do
    ping -c 1 $1.$ip | grep "64 bytes" | cut -d " " -f 4 | sed 's/.$//';
  done;
fi;
