#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
    set -- /data/domains.txt --output-dir /output
fi

if [ ! -f "$1" ]; then
    echo "[-] Domains file not found inside container: $1" >&2
    echo "    Put your list at ./data/domains.txt or override the compose command." >&2
    exit 1
fi

exec python /app/scan.py "$@"
