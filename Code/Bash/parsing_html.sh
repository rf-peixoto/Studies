#!/bin/bash

echo "Retrieving web content."
curl $1 | grep href | cut -d "/" -f 3 | grep "\." | cut -d "\"" -f 1 | grep -v "<l" 2>/dev/null > "$1.txt"
echo "Checking hosts."
for url in $(cat "$1.txt");
do
  host url | grep "has address"
done;
