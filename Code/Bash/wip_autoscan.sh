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
mkdir $1

# Subdomains:
echo $1 > $1/subdomains.txt
assetfinder $1 | sort -u >> $1/subdomains.txt
echo -e "    Found ${BLUE}$(wc -l $1/subdomains.txt)${CLEAR} targets."

# Nuclei:
echo -e "[${BLUE}*${CLEAR}] Now scanning. This can take a while."
nuclei -follow-host-redirects -env-vars -silent -l $1/subdomains.txt -o $1/nuclei.txt

# naabu/nmap:
echo -e "[${BLUE}*${CLEAR}] Scanning ports."
naabu -silent -list $1/subdomains.txt -sD -display-cdn -scan-all-ips | sort -u > $1/naabu.txt
sudo nmap --spoof-mac=6 -sV -Pn --reason -f --data-length 16 --script=vuln,malware -D RND:16 -iL $1/subdomains.txt -oG $1/nmap.txt 2>/dev/null

# sqlmap:
sqlmap -u 'http://$1/' --random-agent --forms --crawl 10 --batch --skip-waf --dbs --level 5 --no-logging --output-dir=$1/sqlmap.txt

# ZAP main URL:
# curl "http://localhost:8080/JSON/ascan/action/scan/?apikey=API&url=$1&recurse=true&inScopeOnly=&scanPolicyName=&method=&postData=&contextId="
# curl "http://localhost:8080/JSON/core/view/alerts/?apikey=API&baseurl=$1&start=0&count=10"


# Print results:
echo ""
echo -e "[${BLUE}*${CLEAR}] Results:"
echo -e "[${BLUE}low${CLEAR}]"
grep --color='auto' -r '\[low\]' $1/nuclei.txt
echo -e "[${YELLOW}medium${CLEAR}]"
grep --color='auto' -r '\[medium\]' $1/nuclei.txt
echo -e "[${RED}high${CLEAR}]"
grep --color='auto' -r '\[high\]' $1/nuclei.txt
echo -e "[${RED}critical${CLEAR}]"
grep --color='auto' -r '\[critical\]' $1/nuclei.txt
echo -e "[${GREEN}unknow${CLEAR}]"
grep --color='auto' -r '\[unknow\]' $1/nuclei.txt
echo -e "[${GREEN}cve${CLEAR}]"
grep --color='auto' -r '\[cve\]' $1/nuclei.txt

# Remove tmp files:
rm *.txt 2>/dev/null && rm ~/.config/nuclei/*.cfg 2>/dev/null
echo ""

# Notify on GNOME:
notify-send "Finished scan on $1"
