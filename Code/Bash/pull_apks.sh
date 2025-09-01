#!/usr/bin/env bash
# Extract all third-party (non-system) apps from a connected Android device/emulator.

set -euo pipefail

OUTDIR="${1:-./extracted_apks}"

if ! command -v adb >/dev/null 2>&1; then
  echo "ERROR: adb not found in PATH." >&2
  exit 2
fi

# Start ADB server if needed
adb start-server >/dev/null 2>&1 || true

# Try to run adbd as root on emulators
if ! adb shell 'id -u' 2>/dev/null | grep -qx '0'; then
  adb root >/dev/null 2>&1 || true
  # adbd may restart
  sleep 1
fi

mkdir -p "$OUTDIR"

# List third-party packages (pm -3) and normalize output
pkgs="$(adb shell pm list packages -3 | sed 's/^package://g' | tr -d '\r' | sort -u)"

if [ -z "$pkgs" ]; then
  echo "No third-party packages found."
  exit 0
fi

echo "Output directory: $OUTDIR"
echo "Found third-party packages:"
echo "$pkgs" | sed 's/^/  - /'

# Loop over packages and pull their APK paths
echo "$pkgs" | while IFS= read -r pkg; do
  [ -z "$pkg" ] && continue
  echo "==> Processing $pkg"
  dest="$OUTDIR/$pkg"
  mkdir -p "$dest"

  # Get all APK paths for this package (base + splits)
  apks="$(adb shell pm path "$pkg" | sed 's/^package://g' | tr -d '\r')"

  if [ -z "$apks" ]; then
    echo "    WARN: No APK paths returned by 'pm path'; skipping."
    continue
  fi

  # Pull each APK; keep original filenames (base.apk, split_*.apk, etc.)
  echo "$apks" | while IFS= read -r remote; do
    [ -z "$remote" ] && continue
    fname="$(basename "$remote")"
    # If multiple packages happen to use the same filename, this keeps them isolated per package dir.
    if adb pull -a "$remote" "$dest/$fname" >/dev/null 2>&1; then
      echo "    pulled $fname"
    else
      echo "    ERROR: failed to pull $remote" >&2
    fi
  done
done

echo "Done."
echo "All APKs saved under: $OUTDIR"
