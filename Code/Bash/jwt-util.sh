#!/bin/bash

if [ "$1" == "" ]
then
  echo "jwt-utils.sh - Usage: $0 <jwt> <output file>"
else
  # Delimiter:
  IFS='.'
  # Split:
  read -ra tmp <<< "$1"

  # Decode:
  for value in "${tmp[@]}";
  do
    echo $value | base64 -d
  done
fi
