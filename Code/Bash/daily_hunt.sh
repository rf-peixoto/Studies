#!/bin/bash

clear
echo "[*] Starting usernames scan..."
for user in $(cat userlists/CLIENT/users.txt)
do
  echo "    Now scanning $user";
  python3 sherlock/sherlock/sherlock.py $user --nsfw --proxy localhost:9050 --folderoutput tmp/ >> results/client_results.txt 2>/dev/null;
done
cat results/client_results.txt | sort -u > results/usernames.txt 2>/dev/null
rm tmp/*.txt results/client_username_results.txt


echo "[*] Starting dorks scan..."
cat userlists/CLIENT/keywords.txt | while read LINE;
do
  echo "    Now scanning $LINE";
  ./go-dork_1.0.2_linux_amd64 --proxy localhost:9050 -e Google -p 3 -q '$LINE DORK' >> results/client_dork_results.txt 2>/dev/null;
  #sleep 3;
  ./go-dork_1.0.2_linux_amd64 --proxy localhost:9050 -e Bing -p 3 -q '$LINE DORK' >> results/client_dork_results.txt 2>/dev/null;
  #sleep 3;
  ./go-dork_1.0.2_linux_amd64 --proxy localhost:9050 -e Ask -p 3 -q '$LINE DORK' >> results/client_dork_results.txt 2>/dev/null;
  #sleep 3;
  ./go-dork_1.0.2_linux_amd64 --proxy localhost:9050 -e Yahoo -p 3 -q '$LINE DORK' >> results/client_dork_results.txt 2>/dev/null;
  #sleep 3;
done
cat results/client_dork_results.txt | sort -u > results/dorks.txt 2>/dev/null
rm results/client_dork_results.txt

echo "[*] Done"
