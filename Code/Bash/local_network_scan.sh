#!/bin/bash
host=$1

for ip in $(seq 1 254)
do
  arping -c 1 $host.$ip | grep "60 bytes"
done
