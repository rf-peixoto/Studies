#!/usr/bin/env bash
# Extract all third-party (non-system) apps from a connected Android device/emulator.
# Each app is saved under ./extracted_apks/<package>/ with all APK files (base + splits).
# Usage: ./extract_3p_apks.sh [output_dir]
# Example: ./extract_3p_apks.sh /tmp/apk_dump

set -euo pipefail

OUTDIR="${1:-./extracted_apks}"

# --- Colors (TTY-aware) ---
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'
else
  BOLD=""; DIM=""; RESET=""; RED=""; GREEN=""; YELLOW=""; BLUE=""
fi

log()   { printf '%s\n' "$*"; }
info()  { printf '%s[i]%s %s\n' "$BLUE" "$RESET" "$*"; }
ok()    { printf '%s[+]%s %s\n' "$GREEN" "$RESET" "$*"; }
warn()  { printf '%s[!]%s %s\n' "$YELLOW" "$RESET" "$*"; }
err()   { printf '%s[x]%s %s\n' "$RED" "$RESET" "$*" >&2; }

# --- Preflight ---
if ! command -v adb >/dev/null 2>&1; then
  err "adb not found in PATH."
  exit 2
fi

adb start-server >/dev/null 2>&1 || true

# Try root on emulators; skip failure silently on physical devices.
if ! adb shell 'id -u' 2>/dev/null | grep -qx '0'; then
  adb root >/dev/null 2>&1 || true
  sleep 1
fi

mkdir -p "$OUTDIR"

info "Enumerating third-party packages…"
pkgs=()
# Avoid pipe-to-while subshells; use process substitution to fill array robustly.
while IFS= read -r pkg; do
  [ -n "$pkg" ] && pkgs+=("$pkg")
done < <(adb shell pm list packages -3 \
      | sed 's/^package://g' \
      | tr -d '\r' \
      | sort -u)

if [ "${#pkgs[@]}" -eq 0 ]; then
  warn "No third-party packages found."
  exit 0
fi

info "Output directory: ${BOLD}${OUTDIR}${RESET}"
info "Found ${#pkgs[@]} packages."

for pkg in "${pkgs[@]}"; do
  printf '%s\n' ""
  log "${BOLD}==>${RESET} ${pkg}"

  dest="$OUTDIR/$pkg"
  mkdir -p "$dest"

  # Collect all APK paths for the package (base + splits).
  apk_paths=()
  while IFS= read -r p; do
    [ -n "$p" ] && apk_paths+=("$p")
  done < <(adb shell pm path "$pkg" \
        | sed 's/^package://g' \
        | tr -d '\r' \
        | awk '!seen[$0]++')   # de-dup just in case

  if [ "${#apk_paths[@]}" -eq 0 ]; then
    warn "No APK paths returned by 'pm path'; skipping."
    continue
  fi

  # Pull each APK. Use directory dest to preserve original filenames.
  for remote in "${apk_paths[@]}"; do
    if adb pull -a "$remote" "$dest/" >/dev/null 2>&1; then
      ok "pulled $(basename "$remote")"
    else
      err "failed to pull $remote"
    fi
  done
done

printf '\n'
ok "Done. All APKs saved under: ${BOLD}${OUTDIR}${RESET}"
