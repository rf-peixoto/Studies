#!/bin/bash

if [ "$1" == "" ]
then
    echo "Usage = $0 (service or protocol name) |Ex: $0 tcp"
else
    cat "/etc/services" | grep $1 | cut -d "/" -f 1
fi
