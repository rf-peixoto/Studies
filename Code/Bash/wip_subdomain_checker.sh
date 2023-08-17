#!/bin/bash

# Get subdomain list; todo
assetfinder $1 | sort -u >> subdomains.txt

# Check each one of then:
for sub in $(cat subdomains.txt);
do
  echo $sub - $(curl -s -o /dev/null -w %{http_code}" $ub) >> sub-checked.txt;
done
