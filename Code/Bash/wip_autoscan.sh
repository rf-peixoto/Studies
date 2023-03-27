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
echo $1 > subdomains.txt
assetfinder $1 | sort -u >> subdomains.txt
echo -e "    Found ${BLUE}$(wc -l subdomains.txt)${CLEAR} targets."

# Nuclei:
echo -e "[${BLUE}*${CLEAR}] Now scanning. This can take a while."
proxychains -q nuclei -env-vars -silent -l subdomains.txt -o nuclei.txt

# nmap:
# sudo nmap --spoof-mac=6 -sV -Pn --reason -f --data-length 16 --script=vuln -D RND:16 -iL subdomains.txt -oG nmap.txt 2>/dev/null

# sqlmap:
sqlmap -u 'http://$1/' --random-agent --forms --crawl 10 --batch --skip-waf --dbs --level 5

# ZAP main URL:
# curl "http://localhost:8080/JSON/ascan/action/scan/?apikey=APIKEY&url=$1&recurse=true&inScopeOnly=&scanPolicyName=&method=&postData=&contextId="
# curl "http://localhost:8080/JSON/core/view/alerts/?apikey=APIKEY&baseurl=$1&start=0&count=10"


# Print results:
echo -e "[${BLUE}*${CLEAR}] Results:"
echo -e "[${BLUE}low${CLEAR}]"
grep --color='auto' -r '\[low\]' nuclei.txt
echo -e "[${YELLOW}medium${CLEAR}]"
grep --color='auto' -r '\[medium\]' nuclei.txt
echo -e "[${RED}high${CLEAR}]"
grep --color='auto' -r '\[high\]' nuclei.txt
echo -e "[${RED}critical${CLEAR}]"
grep --color='auto' -r '\[critical\]' nuclei.txt
echo -e "[${GREEN}unknow${CLEAR}]"
grep --color='auto' -r '\[unknow\]' nuclei.txt
echo -e "[${GREEN}cve${CLEAR}]"
grep --color='auto' -r '\[cve\]' nuclei.txt

# Remove tmp files:
rm *.txt
