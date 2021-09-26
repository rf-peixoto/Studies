#!/bin/bash

# -------------------------------------------- #
#  Print Banner:                               #
# -------------------------------------------- #
echo "+----------------------+"
echo "|   DNS Lookup v1.0.0  |"
echo "+----------------------+"
echo "   Welcome, $USER"
# -------------------------------------------- #
# Check Args:                                  #
# -------------------------------------------- #
if [ "$1" == "" ]
then
  echo "Usage: $0 [domain]"
  echo ""
  exit
fi

# -------------------------------------------- #
# List Hosts:
# -------------------------------------------- #
if [ "$(ping -n -A -c 1 -W 1 $1 2>/dev/null | grep '64 bytes')" == "" ]
then
  echo -e "\e[31m[No ICMP Response]\e[0m $1"
  if [ "$(curl -o /dev/null -s -w '%{http_code}' $1)" == "000" ]
  then
    echo -e "\e[31mCould not find this host. Sorry.\e[0m"
  else
    echo -e "\e[91mThis target has security filters. Some results may be incorrect.\e[0m"
  fi
  exit
else
  echo -e "\e[32m[Up]\e[0m $1"
fi
for host in $(host $1 | cut -d ' ' -f 4 | egrep -v 'handled|address')
do
  echo -e "\e[32m[+]\e[0m $host"
done
echo ""

# -------------------------------------------- #
# Check SPF Records                            #
# -------------------------------------------- #
spf=$(host -t txt $1 | grep .all | cut -d '"' -f 2 | grep -o '.all')
if [ "$spf" == "?all" ]
then
  echo -e "\e[32m[?]\e[0m SPF Vulnerable.";
elif [ "$spf" == "+all" ]
then
  echo -e "\e[32m[+]\e[0m SPF Vulnerable.";
elif [ "$spf" == "~all" ]
then
  echo -e "\e[91m[~]\e[0m SPF Possibly vulnerable.";
elif [ "$spf" == "-all" ]
then
  echo -e "\e[31m[-]\e[0m SPF Probably secure.";
elif [ "$spf" == "" ]
then
  echo -e "\e[31m[-]\e[0m SPF Secure."
fi
echo ""
# -------------------------------------------- #
# Look for mail server:
# -------------------------------------------- #
echo "Mail server(s):"
for i in $(host -t mx $1 | cut -d ' ' -f 7 | sed 's/.$//')
do
  echo -e "\e[32m[+]\e[0m $i";
done
echo ""
# -------------------------------------------- #
# Name Servers:
# -------------------------------------------- #
echo "Name servers found:"
for i in $(host -t ns $1 | cut -d " " -f 4 | sed 's/.$//')
do
  echo -e "\e[32m[+]\e[0m $i";
done
echo ""
