#!/usr/bin/env bash
set -euo pipefail

INPUT_FILE="${1:-}"

if [[ -z "$INPUT_FILE" || ! -f "$INPUT_FILE" ]]; then
  echo "Usage: $0 <file_with_domains>" >&2
  exit 1
fi

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
command -v dig >/dev/null 2>&1 || { echo "dig is required" >&2; exit 1; }

resolve_ipv4() {
  dig +short A "$1" | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/'
}

query_internetdb() {
  curl -fsS --max-time 10 "https://internetdb.shodan.io/$1"
}

while IFS= read -r raw || [[ -n "$raw" ]]; do
  domain="$(echo "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  [[ -z "$domain" ]] && continue
  [[ "$domain" == \#* ]] && continue

  ips="$(resolve_ipv4 "$domain" || true)"
  [[ -z "$ips" ]] && continue

  while IFS= read -r ip; do
    [[ -z "$ip" ]] && continue

    if db="$(query_internetdb "$ip" 2>/dev/null)"; then
      echo "{domain:${domain}, ip:${ip}, internetdb:${db}}"
    else
      echo "{domain:${domain}, ip:${ip}, internetdb:null}"
    fi

  done <<< "$ips"

done < "$INPUT_FILE"
