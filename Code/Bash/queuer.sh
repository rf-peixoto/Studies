#!/usr/bin/env bash
set -euo pipefail

# finder.sh
# Usage:
#   ./finder.sh "example.com" /path/to/root
#   ./finder.sh --generate-filelist /path/to/root
#
# Notes:
# - Always uses fixed-string search (-F). Dots in domains are literal.
# - Skips file paths > 96 chars.
# - Drops matched lines > 96 chars.
#
# Env tuning (HDD-friendly defaults):
#   RG_THREADS=2
#   XARGS_P=1

MAX_LEN=96

for cmd in rg find xargs awk wc sed mv rm mkdir; do
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

generate_filelist() {
  local root="$1"
  if [[ ! -d "$root" ]]; then
    echo "Error: ROOT directory does not exist: $root" >&2
    exit 1
  fi

  local tmp_list="${FILELIST}.tmp.$$"
  rm -f -- "$tmp_list"

  # Newline-delimited file list as requested (-print).
  # - Case-insensitive .txt: -iname '*.txt'
  # - Suppress permission errors: 2>/dev/null
  # - Skip file paths longer than MAX_LEN.
  find "$root" -type f -iname '*.txt' -print 2>/dev/null \
    | awk -v m="$MAX_LEN" 'length($0) <= m' \
    > "$tmp_list"

  if [[ ! -s "$tmp_list" ]]; then
    rm -f -- "$tmp_list"
    echo "Error: generated filelist is empty after filtering." >&2
    echo "Possible causes:" >&2
    echo "  - No *.txt files under: $root" >&2
    echo "  - Permission issues prevented traversal" >&2
    echo "  - Most paths exceed ${MAX_LEN} characters" >&2
    exit 1
  fi

  mv -f -- "$tmp_list" "$FILELIST"
  echo "Filelist generated at: $FILELIST"
}

# Option: generate filelist only
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

# Ensure cached filelist exists
if [[ ! -f "$FILELIST" || ! -s "$FILELIST" ]]; then
  generate_filelist "$ROOT"
fi

# Fresh search cleanup (keep filelist cache)
rm -f -- "$RAW_FILE" "$FINAL_FILE"

# Search:
# - Use GNU xargs delimiter as newline to preserve spaces in paths.
# - Always -F, suppress filenames, suppress errors.
# - Filter out matched lines longer than MAX_LEN immediately.
#
# Exit codes: rg returns 0 matches found, 1 no matches; both are acceptable.
set +e
START_NS=$(date +%s%N)
xargs -d $'\n' -a "$FILELIST" -P "$XARGS_P" rg -F --threads "$RG_THREADS" --no-filename --no-messages -- "$DOMAIN" \
  | awk -v m="$MAX_LEN" 'length($0) <= m' \
  > "$RAW_FILE"
RG_EXIT=${PIPESTATUS[0]}
set -e

if [[ "$RG_EXIT" -ne 0 && "$RG_EXIT" -ne 1 ]]; then
  echo "Error: rg failed with exit code $RG_EXIT" >&2
  exit "$RG_EXIT"
fi

# Deduplicate (fast for thousands of lines)
awk '!seen[$0]++' "$RAW_FILE" > "$FINAL_FILE"

# Calculate time:
END_NS=$(date +%s%N)
ELAPSED_NS=$((END_NS - START_NS))

# Convert to human-readable: HH:MM:SS.mmm
ELAPSED_MS=$((ELAPSED_NS / 1000000))
MS=$((ELAPSED_MS % 1000))
TOTAL_S=$((ELAPSED_MS / 1000))
S=$((TOTAL_S % 60))
TOTAL_M=$((TOTAL_S / 60))
M=$((TOTAL_M % 60))
H=$((TOTAL_M / 60))

TIME_FMT=$(printf "%02d:%02d:%02d.%03d" "$H" "$M" "$S" "$MS")

LINE_COUNT="$(wc -l < "$FINAL_FILE" | tr -d '[:space:]')"
ESCAPED_FINAL_FILE="$(printf '%s' "$FINAL_FILE" | sed 's/\\/\\\\/g; s/"/\\"/g')"
printf '{"output":"%s","lines":%s,"time":"%s"}\n' "$ESCAPED_FINAL_FILE" "$LINE_COUNT" "$TIME_FMT"
