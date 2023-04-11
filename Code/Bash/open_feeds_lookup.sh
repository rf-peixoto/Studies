#!/bin/bash

# Manually download feeds from:
# https://com.all-url.info/
# https://www.whoisds.com/newly-registered-domains

# Config URLs:
OPENPHISH='https://openphish.com/feed.txt'
MALWAREFILTER='https://malware-filter.gitlab.io/malware-filter/phishing-filter-domains.txt'
PHISHSTATS='https://phishstats.info/phish_score.csv'
URLHAUS='https://urlhaus.abuse.ch/downloads/text/'
PHISHINGDATABASE='https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/phishing-links-NEW-today.txt'
PHISHUNT='https://phishunt.io/feed.txt'
SECURELOAD='https://secureload.tech/Phishing/Lists/Latest/'

# Download:
clear && echo '[*] Downloading feeds...'
wget -q $OPENPHISH
wget -q $MALWAREFILTER
wget -q $PHISHSTATS
wget -q $URLHAUS
wget -q $PHISHINGDATABASE -O phishdatabase.txt
wget -q $PHISHUNT -O hunt.txt
wget -q $SECURELOAD -O secureload.txt

# Prepare file:
echo '[*] Parsing...'
touch tmp
for word in $(cat keywords):
do
  grep $word -h *.txt *.csv >> tmp
done;
cat tmp | sort -u > result.txt

# Find keywords:
echo '[*] Finding keywords:'
echo ''
for word in $(cat keywords):
do
  grep --color='auto' -h $word result.txt 2>/dev/null
done;

# Wipe out trash:
echo ''
cp result.txt old/result-"`date +"%d%m%Y"`".txt
rm *.txt *.csv *.html tmp
