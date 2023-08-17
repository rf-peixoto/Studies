#!/bin/bash

# Get subdomain list; todo

# Check each one of then:
for sub in $(cat $1);
do
  echo $i - $(curl -s -o /dev/null -w %{http_code}" $i) >> sub-checked.txt;
done
