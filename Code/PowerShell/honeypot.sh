#!/bin/bash

if [ "$1" == "" ]
then
    echo "Usage $0 port"
else
    while true
    do
        nc -vnlp "$1" < banner.txt >> log.txt 2>> log.txt | echo $(date) >> log.txt;
    done
fi

