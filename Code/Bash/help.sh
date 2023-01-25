#!/bin/bash

# Help text:
usage() {
  cat <<EOF
Usage: ${0##*/} [stugg]

Your:
  Help text.

EOF
}

if [[ -z $1 || $1 = @(-h|--help) ]]; then
  usage
  exit $(( $# ? 0 : 1 ))
fi

# Your code stuff:
echo "I work here."
