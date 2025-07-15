#!/bin/bash

# =======================
# VeraCrypt Hidden Volume Creator
# =======================
# Creates a VeraCrypt volume with a hidden inner volume
# Optional: keyfiles
# Auto-mounts both volumes after creation for verification
# Cleans sensitive traces from shell history

# ========== USER INPUT ==========
clear
echo "==== VeraCrypt Hidden Volume Generator ===="
echo "This script will create a standard outer volume, then a hidden volume inside it."
echo ""

read -p "Full path for the volume to be created (e.g., /home/user/secrets.vc): " VC_PATH
read -p "Total volume size (e.g., 100M, 1G): " VC_SIZE

echo ""
read -s -p "Password for OUTER (decoy) volume: " VC_PASS
echo ""
read -s -p "Password for HIDDEN (real) volume: " VC_HIDDEN_PASS
echo ""

read -p "Do you want to use a keyfile? [y/N]: " USE_KEYFILE

KEYFILE=""
if [[ "$USE_KEYFILE" == "y" || "$USE_KEYFILE" == "Y" ]]; then
    read -p "Path to keyfile (e.g., /home/user/key.jpg): " KEYFILE
    if [[ ! -f "$KEYFILE" ]]; then
        echo "[!] Keyfile not found. Exiting."
        exit 1
    fi
fi

MOUNT_PATH="/mnt/veracrypt_hidden"
mkdir -p "$MOUNT_PATH"

# ========== CREATE OUTER VOLUME ==========
echo "[+] Creating outer volume..."
veracrypt --text --create "$VC_PATH" \
  --size="$VC_SIZE" \
  --encryption=AES --hash=SHA-512 \
  --volume-type=normal \
  --filesystem=FAT \
  --password="$VC_PASS" \
  --keyfiles="$KEYFILE" \
  --pim=0 --random-source=/dev/urandom \
  --non-interactive

if [ $? -ne 0 ]; then
  echo "[!] Failed to create outer volume."
  exit 1
fi

# ========== CREATE HIDDEN VOLUME ==========
echo "[+] Creating hidden volume inside the outer volume..."
veracrypt --text --create "$VC_PATH" \
  --encryption=AES --hash=SHA-512 \
  --volume-type=hidden \
  --filesystem=FAT \
  --password="$VC_PASS" \
  --hidden-password="$VC_HIDDEN_PASS" \
  --keyfiles="$KEYFILE" \
  --pim=0 --random-source=/dev/urandom \
  --non-interactive

if [ $? -ne 0 ]; then
  echo "[!] Failed to create hidden volume."
  exit 1
fi

# ========== AUTO-MOUNT BOTH VOLUMES ==========
echo "[+] Mounting outer volume to verify..."

veracrypt --text --mount "$VC_PATH" "$MOUNT_PATH" \
  --password="$VC_PASS" \
  --keyfiles="$KEYFILE" \
  --pim=0

echo "[+] Outer volume mounted at $MOUNT_PATH"
echo "Press Enter to unmount and mount the hidden volume."
read

veracrypt --text --dismount "$MOUNT_PATH"

echo "[+] Mounting hidden volume..."

veracrypt --text --mount "$VC_PATH" "$MOUNT_PATH" \
  --password="$VC_HIDDEN_PASS" \
  --keyfiles="$KEYFILE" \
  --pim=0 --protect-hidden=no

echo "[+] Hidden volume mounted at $MOUNT_PATH"
echo "Press Enter to dismount and continue."
read

veracrypt --text --dismount "$MOUNT_PATH"

# ========== CLEANUP AND HISTORY SANITIZATION ==========
echo "[*] Secure cleanup and history sanitization..."

# Wipe mount path and keyfile path traces from Bash history
HIST_FILE="$HOME/.bash_history"
TMP_HISTORY=$(mktemp)

# Save all lines that do NOT reference VeraCrypt paths, passwords, or keyfiles
grep -vE "veracrypt|${VC_PATH}|${KEYFILE}|${VC_PASS}|${VC_HIDDEN_PASS}" "$HIST_FILE" > "$TMP_HISTORY"

# Overwrite history file securely
shred -u "$HIST_FILE"
mv "$TMP_HISTORY" "$HIST_FILE"
chmod 600 "$HIST_FILE"
history -c && history -r

echo "[✓] Done."

# ========== INSTRUCTIONS ==========
echo ""
echo "========== Usage Instructions =========="
echo "To mount the OUTER (decoy) volume:"
echo "  veracrypt --text --mount \"$VC_PATH\" /mnt/veracrypt1"
[[ -n "$KEYFILE" ]] && echo "    --keyfiles=\"$KEYFILE\""
echo ""
echo "To mount the HIDDEN (real) volume:"
echo "  veracrypt --text --mount \"$VC_PATH\" /mnt/veracrypt1 \\"
echo "    --password=\"<real_password>\" --protect-hidden=no"
[[ -n "$KEYFILE" ]] && echo "    --keyfiles=\"$KEYFILE\""
echo ""
echo "To unmount:"
echo "  veracrypt --text --dismount /mnt/veracrypt1"
echo ""
