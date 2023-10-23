#!/bin/zsh

# Check the NTP service at domain.com
ntpq -pn $(host $1 | cut -d " " -f 4)
