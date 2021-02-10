#!/bin/bash
for server in $(host -t ns $1 | cut -d " " -f4):
do
    host -l -a $1 $server
done
