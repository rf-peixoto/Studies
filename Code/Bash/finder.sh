#!/usr/bin/env bash
set -euo pipefail

# finder.sh
#
# Usage:
#   ./finder.sh "example.com" /path/to/root
#   ./finder.sh --generate-filelist /path/to/root


MAX_LEN=96

for cmd in rg find xargs awk wc sed date mkdir rm mv bash; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Error: $cmd not found in PATH." >&2; exit 1; }
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="${SCRIPT_DIR}/tmp"
mkdir -p -- "$TMP_DIR"

FILELIST="${TMP_DIR}/filelist.txt"
RAW_FILE="${TMP_DIR}/raw.txt"
FINAL_FILE="${TMP_DIR}/final.txt"

RG_THREADS="${RG_THREADS:-2}"
XARGS_P="${XARGS_P:-1}"
XARGS_N="${XARGS_N:-200}"

generate_filelist() {
  local root="$1"
  if [[ ! -d "$root" ]]; then
    echo "Error: ROOT directory does not exist: $root" >&2
    exit 1
  fi

  local tmp_list="${FILELIST}.tmp.$$"
  rm -f -- "$tmp_list"

  # NOTE: Newline-delimited lists cannot represent file paths containing newlines.
  find "$root" -type f -iname '*.txt' -print 2>/dev/null \
    | awk -v m="$MAX_LEN" 'length($0) <= m' \
    > "$tmp_list"

  if [[ ! -s "$tmp_list" ]]; then
    rm -f -- "$tmp_list"
    echo "Error: generated filelist is empty after filtering." >&2
    echo "Possible causes:" >&2
    echo "  - No *.txt files under: $root" >&2
    echo "  - Permission issues prevented traversal" >&2
    echo "  - Most file paths exceed ${MAX_LEN} characters" >&2
    exit 1
  fi

  mv -f -- "$tmp_list" "$FILELIST"
  echo "Filelist generated at: $FILELIST"
}

# Generate filelist only
if [[ "${1:-}" == "--generate-filelist" ]]; then
  ROOT="${2:-.}"
  generate_filelist "$ROOT"
  exit 0
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 \"domain\" [/search/root]" >&2
  echo "       $0 --generate-filelist [/search/root]" >&2
  exit 1
fi

DOMAIN="$1"
ROOT="${2:-.}"

if [[ -z "$DOMAIN" ]]; then
  echo "Error: domain is empty." >&2
  exit 1
fi
if [[ ! -d "$ROOT" ]]; then
  echo "Error: ROOT directory does not exist: $ROOT" >&2
  exit 1
fi

# Ensure cached filelist exists (and is non-empty)
if [[ ! -f "$FILELIST" || ! -s "$FILELIST" ]]; then
  generate_filelist "$ROOT"
fi

# Fresh search cleanup (keep filelist cache)
rm -f -- "$RAW_FILE" "$FINAL_FILE"

# Start timer for the query phase (not including filelist generation).
START_NS="$(date +%s%N)"

set +e
xargs -d $'\n' -a "$FILELIST" -P "$XARGS_P" -n "$XARGS_N" \
  bash -c '
    rg -F --threads "'"$RG_THREADS"'" --no-filename --no-messages -- "'"$DOMAIN"'" "$@"
    ec=$?
    if [[ $ec -eq 1 ]]; then
      exit 0   # "no matches" is normal; do not poison xargs
    fi
    exit $ec   # propagate real errors (e.g., 2)
  ' _ \
  | awk -v m="$MAX_LEN" 'length($0) <= m' \
  > "$RAW_FILE"
XARGS_EXIT=$?
set -e

if [[ "$XARGS_EXIT" -ne 0 ]]; then
  echo "Error: search pipeline failed (xargs exit code $XARGS_EXIT)" >&2
  exit "$XARGS_EXIT"
fi

# Deduplicate (fast for "thousands" of lines)
awk '!seen[$0]++' "$RAW_FILE" > "$FINAL_FILE"

# End timer
END_NS="$(date +%s%N)"
ELAPSED_NS=$((END_NS - START_NS))

# Human-readable: HH:MM:SS.mmm
ELAPSED_MS=$((ELAPSED_NS / 1000000))
MS=$((ELAPSED_MS % 1000))
TOTAL_S=$((ELAPSED_MS / 1000))
S=$((TOTAL_S % 60))
TOTAL_M=$((TOTAL_S / 60))
M=$((TOTAL_M % 60))
H=$((TOTAL_M / 60))
TIME_FMT="$(printf "%02d:%02d:%02d.%03d" "$H" "$M" "$S" "$MS")"

LINE_COUNT="$(wc -l < "$FINAL_FILE" | tr -d '[:space:]')"
ESCAPED_FINAL_FILE="$(printf '%s' "$FINAL_FILE" | sed 's/\\/\\\\/g; s/"/\\"/g')"

printf '{"output":"%s","lines":%s,"time":"%s"}\n' "$ESCAPED_FINAL_FILE" "$LINE_COUNT" "$TIME_FMT"
