#!/bin/bash

# Config URLs:
OPENPHISH='https://openphish.com/feed.txt'
MALWAREFILTER='https://malware-filter.gitlab.io/malware-filter/phishing-filter-domains.txt'
PHISHSTATS='https://phishstats.info/phish_score.csv'

# Download:
clear && echo '[*] Downloading feeds.'
wget -q $OPENPHISH
wget -q $MALWAREFILTER
wget -q $PHISHSTATS

# Find stuff:
echo ''
for word in $(cat keywords):
do
  grep --color='auto' -h $word *.txt *.csv 2>/dev/null
done;

# Wipe out trash:
rm *.txt *.csv
