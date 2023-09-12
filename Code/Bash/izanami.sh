#!/bin/bash
# ------------------------------------------------------- #
# Author: https://www.linkedin.com/in/rf-peixoto/
# a.k.a Corvo
# ------------------------------------------------------- #

VERSION="v1.3.0"

# Setup colors:
CLEAR='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;32m'

# ------------------------------------------------------- #
# Usage:
# ------------------------------------------------------- #
usage() {
  cat <<EOF
    izanami ${VERSION}
    Usage ${0##*/} domain

    Ex: ${0##*/} domain.com

EOF
}

# Check args:
if [[ -z $1 || $1 = @(-h|--help) ]]; then
  usage
  exit $(( $# ? 0 : 1 ))
fi
# ------------------------------------------------------- #
# Banner:
# ------------------------------------------------------- #
clear
echo -e "${GREEN}"
echo -e "                                          イザナミ"
echo -e " _____ ______ _______ __   _ _______ _______ _____"
echo -e "   |    ____/ |_____| | \  | |_____| |  |  |   |"
echo -e " __|__ /_____ |     | |  \_| |     | |  |  | __|__"
echo -e "    ${VERSION}"
echo -e "${CLEAR}"

# ------------------------------------------------------- #
# Start:
# ------------------------------------------------------- #
echo ""
echo -e "[${BLUE}*${CLEAR}] Preparing output directory for ${GREEN}$1${CLEAR}"
mkdir $1

# ------------------------------------------------------- #
# Find subdomains:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Looking for subdomains."
echo $1 > $1/subdomains.txt
assetfinder $1 | sort -u >> $1/subdomains.txt
echo -e "    Found ${BLUE}$(wc -l $1/subdomains.txt | cut -d ' ' -f 1)${CLEAR} targets."

# ------------------------------------------------------- #
# Scan with nuclei:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Scanning web assets."
nuclei -env-vars -silent -l $1/subdomains.txt > $1/nuclei.txt

# ------------------------------------------------------- #
# Port scan with naabu, nmap and internetdb:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Looking on InternetDB."
curl -s https://internetdb.shodan.io/$(host $1 | head -n 1 | cut -d " " -f 4) | jq > $1/internetdb.json

echo -e "[${BLUE}*${CLEAR}] Scanning ports."
naabu -silent -list $1/subdomains.txt -sD -display-cdn -scan-all-ips | sort -u > $1/naabu.txt
echo -e "    Found ${BLUE}$(wc -l $1/naabu.txt | cut -d ' ' -f 1)${CLEAR} ports."


#sudo nmap -sV -Pn -f --data-length 16 --script=vuln,malware -D RND:16 $1 -oG $1/nmap.txt > /dev/null
#sudo nmap --spoof-mac=6 -sV -Pn --reason -f --data-length 16 --script=vuln,malware -D RND:16 -iL $1/subdomains.txt -oG $1/nmap.txt > /dev/null

# ------------------------------------------------------- #
# Get links with katana::
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Collecting visible links."
katana -d 3 -silent -u http://$1 | sort -u > $1/katana.txt
echo -e "    Found ${BLUE}$(wc -l $1/katana.txt | cut -d ' ' -f 1)${CLEAR} links."


# ------------------------------------------------------- #
# Analyze SSL/TLS:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Scanning SSL/TLS."
python -m sslyze --targets_in $1/subdomains.txt > $1/sslyze.json 2>/dev/null

# ------------------------------------------------------- #
# SQLMap scan:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Looking for injection."
# sqlmap -u 'http://$1/' --random-agent --forms --crawl 10 --batch --skip-waf --dbs --level 5 --no-logging --output-dir=$1/sqlmap.txt

# ------------------------------------------------------- #
# Webscan with ZAP:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Starting scan on OWASP ZAP."
# curl "http://localhost:8080/JSON/ascan/action/scan/?apikey=APIKEY&url=$1&recurse=true&inScopeOnly=&scanPolicyName=&method=&postData=&contextId="
# curl "http://localhost:8080/JSON/core/view/alerts/?apikey=APIKEY&baseurl=$1&start=0&count=10"

# ------------------------------------------------------- #
# Compressing results:
# ------------------------------------------------------- #
echo -e "[${BLUE}*${CLEAR}] Packing results."
#7z a '$1_"`date +"%d%m%Y"`".7z' $1/* > /dev/null
7z a $1.7z $1/* > /dev/null

# Remove tmp files:
rm *.txt 2>/dev/null && rm ~/.config/nuclei/*.cfg 2>/dev/null
echo ""

# Notify on GNOME:
echo -e "[${BLUE}*${CLEAR}] Finished."
notify-send "Finished scan on $1"
