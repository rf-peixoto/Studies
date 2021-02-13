#!/bin/bash

if [ "$1" == "" ]
then
    echo "Usage = $0 (service or protocol name)"
else
    cat "/etc/services" | grep $1 | cut -d "/" -f 1
fi
