#!/bin/bash

# ------------------------------------------------------------------------- $
# Make backup:
if [ ! -d "$bkp" ]; then
  echo "[+] Creating backup..."
  mkdir bkp 2>/dev/null
  cp $1 bkp/$1.bkp
fi
# ------------------------------------------------------------------------- $


# ------------------------------------------------------------------------- $
# Clean bad chars
echo "[+] Cleaning..."
iconv -f utf-8 -t utf-8 -c $1 > clean_1.txt
sed 's/\r$//' clean_1.txt > clean.txt
# ------------------------------------------------------------------------- $


# ------------------------------------------------------------------------- $
# Parse:
echo "[+] Parsing..."
# User name:
grep -iEoH "^User.*|^Login.*" clean.txt | cut -d " " -f 2 > tmp_user
# Password:
grep -iEoH "^Pass.*" clean.txt | cut -d " " -f 2 > tmp_pass
# URL:
grep -iEoH "^Host.*|^Url.*" clean.txt | cut -d " " -f 2 > tmp_url
# ------------------------------------------------------------------------- $


# ------------------------------------------------------------------------- $
# Save:
echo "[+] Saving..."
paste tmp_user tmp_pass tmp_url -d "," > "parsed.$1"
#nl "parsed.$1" > tmp.output.$1
sed 's/clean.txt//' parsed.$1 > tmp.output.$1 #tmp.output.$1 >tmp2.output.$1
awk '{print $0,",Botnet Stealer|"}' tmp.output.$1 | sort -u  > output.$1 # tmp2.output.$1 > output.$1
# ------------------------------------------------------------------------- $


# ------------------------------------------------------------------------- $
# Remove tmp files:
echo "[+] Removing tmp files..."
rm clean_1.txt clean.txt tmp_user tmp_pass tmp_url parsed.$1 tmp.output.$1 tmp2.output.$1 2>/dev/null
echo "[+] Saved as output.$1 and done."
# ------------------------------------------------------------------------- $
