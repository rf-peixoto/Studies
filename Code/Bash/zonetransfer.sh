#!/bin/bash

dns_list=$(host -t ns $1 | cut -d " " -f4)
for dns in $dns_list
do
    host -l -a $1 $dns;
done

