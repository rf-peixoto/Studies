#!/usr/bin/env bash
# watch -n 60 this_file.sh

set -euo pipefail

dir="${1:-.}"

if ! command -v md5sum >/dev/null 2>&1; then
  echo "md5sum not found" >&2
  exit 1
fi

declare -A seen
removed=0
kept=0

# Process files in a stable order; handle any filename safely
find "$dir" -xdev -type f -print0 | sort -z | while IFS= read -r -d '' file; do
  # Skip unreadable files
  if [[ ! -r "$file" ]]; then
    continue
  fi

  sum="$(md5sum -- "$file" | awk '{print $1}')"

  if [[ -n "${seen[$sum]+x}" ]]; then
    echo "Removing duplicate: $file (same as ${seen[$sum]})"
    rm -f -- "$file"
    removed=$((removed+1))
  else
    seen[$sum]="$file"
    kept=$((kept+1))
  fi
done

echo "Done. Kept: $kept, Removed duplicates: $removed"
