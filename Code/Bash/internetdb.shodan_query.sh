#!/bin/bash

curl https://internetdb.shodan.io/$(host $1 | head -n1 | cut -d " " -f 4) | jq
