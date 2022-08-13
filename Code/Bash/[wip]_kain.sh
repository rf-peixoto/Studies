#!/bin/bash

# Kain mail parser. Work in progress.

# ---------------- #
# From:
# ---------------- #
tmp=$(grep "From: "  $1 | cut -d " " -f 3)
from=${tmp:1:len-1}
echo -e "\e[32m[\e[0mFROM\e[32m]\e[0m\t\t\t$from"

# ---------------- #
# Reply-To:
# ---------------- #
tmp=$(grep "Reply-To: "  $1 | cut -d " " -f 3)
replyto=${tmp:1:len-1}
echo -e "\e[32m[\e[0mReply-To\e[32m]\e[0m\t\t$replyto"

# ---------------- #
# To:
# ---------------- #
to=$(grep "To: "  $1 | head -n 1 | grep -E -o "\b[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+.[a-zA-Z0-9.-]+\b")
echo -e "\e[32m[\e[0mTO\e[32m]\e[0m\t\t\t$to"

# ---------------- #
# Find Sender IP
# ---------------- #
tmp=$(grep spf $1 | cut -d " " -f 6)
source_ip=${tmp::len-1}
echo -e "\e[32m[\e[0mIP\e[32m]\e[0m\t\t\t$source_ip"

# ---------------- #
# Check SPF Test:
# ---------------- #
spf=$(grep spf $1 | cut -d " " -f 2 | cut -d "=" -f 2)
if [ "$spf" == "pass" ]
then
  echo -e "\e[32m[\e[0mSPF\e[32m]\e[0m\t\t\t$spf"
else
  echo -e "\e[32m[\e[0mSPF\e[32m]\e[0m\t\t\e[31m$spf\e[0m"
fi

# ---------------- #
# Check DMARC:
# ---------------- #
dmarc=$(grep dmarc $1 | cut -d ";" -f 2 | cut -d " " -f 1 | cut -d "=" -f 2)
if [ "$dmarc" == "pass" ]
then
  echo -e "\e[32m[\e[0mDMARC\e[32m]\e[0m\t\t\t$dmarc"
else
  echo -e "\e[32m[\e[0mDMARC\e[32m]\e[0m\t\t\t\e[31m$dmarc\e[0m"
fi

# ---------------- #
# Check DKIM:
# ---------------- #
dkim=$(grep dkim $1 | cut -d " " -f 3 | cut -d "=" -f 2)
if [ "$dkim" == "pass" ]
then
  echo -e "\e[32m[\e[0mDKIM\e[32m]\e[0m\t\t\t$dkim"
else
  echo -e "\e[32m[\e[0mDKIM\e[32m]\e[0m\t\t\t\e[31m$dkim\e[0m"
fi
