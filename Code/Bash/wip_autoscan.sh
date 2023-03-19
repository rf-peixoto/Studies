#!/bin/bash

# Usage:
usage() {
  cat <<EOF
    Usage ${0##*/} domain

    Ex: ${0##*/} domain.com

EOF
}


# Check args:
if [[ -z $1 || $1 = @(-h|--help) ]]; then
  usage
  exit $(( $# ? 0 : 1 ))
fi
clear

# SETUP:
CLEAR='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;32m'

# Start:
echo -e "[${BLUE}*${CLEAR}] Running on ${GREEN}$1${CLEAR}"

# Subdomains:
assetfinder $1 | sort -u > subdomains.txt
echo -e "    Found ${BLUE}$(wc -l subdomains.txt)${CLEAR} targets."

# Nuclei:
echo -e "[${BLUE}*${CLEAR}] Now scanning. This can take a while."
proxychains -q nuclei -env-vars -no-meta -scan-all-ips -silent -l subdomains.txt -o nuclei.txt

# Print results:
echo -e "[${BLUE}*${CLEAR}] Results:"
echo -e "[${BLUE}low${CLEAR}]"
grep -r '\[low\]' nuclei.txt
echo -e "[${YELLOW}medium${CLEAR}]"
grep -r '\[medium\]' nuclei.txt
echo -e "[${RED}high${CLEAR}]"
grep -r '\[high\]' nuclei.txt
echo -e "[${RED}critical${CLEAR}]"
grep -r '\[critical\]' nuclei.txt
echo -e "[${GREEN}unknow${CLEAR}]"
grep -r '\[unknow\]' nuclei.txt
echo -e "[${GREEN}cve${CLEAR}]"
grep -r '\[cve\]' nuclei.txt

# Remove tmp files:
rm *.txt
