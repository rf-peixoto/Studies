# sudo apt install gnupg ssss qrencode

# CREATE:
#!/bin/bash

set -euo pipefail

### CONFIGURATION ###
PAYLOAD="$1"  # e.g., ./payload.txt
THRESHOLD=3   # Minimum number of parties needed
TOTAL_SHARES=5
SYMMETRIC_KEY="./redbutton.key"
ENCRYPTED_PAYLOAD="payload.enc.gpg"
KEY_SHARES_DIR="./shares"
#####################

echo "[*] Generating a 256-bit symmetric key..."
openssl rand -base64 32 > "$SYMMETRIC_KEY"

echo "[*] Encrypting payload with symmetric GPG key..."
gpg --symmetric --cipher-algo AES256 --batch --passphrase-file "$SYMMETRIC_KEY" --output "$ENCRYPTED_PAYLOAD" "$PAYLOAD"

echo "[*] Splitting key into $TOTAL_SHARES shares (threshold: $THRESHOLD)..."
mkdir -p "$KEY_SHARES_DIR"
ssss-split -t "$THRESHOLD" -n "$TOTAL_SHARES" -w "Multiplayer Red Button" < "$SYMMETRIC_KEY" > "$KEY_SHARES_DIR/shares.txt"

echo "[*] Extracting individual share files..."
split -l 1 "$KEY_SHARES_DIR/shares.txt" "$KEY_SHARES_DIR/share_"

# Optional: Create QR codes for each share (for offline distribution)
echo "[*] Generating QR codes for each share..."
for share in "$KEY_SHARES_DIR"/share_*; do
    QRNAME="${share}.png"
    qrencode -o "$QRNAME" < "$share"
done

echo "[✔] Done. Summary:"
echo "    - Encrypted payload: $ENCRYPTED_PAYLOAD"
echo "    - Key shares:        $KEY_SHARES_DIR/share_*"
echo "    - QR codes:          $KEY_SHARES_DIR/share_*.png"
echo
echo ">>> Distribute each share securely to trusted parties."
echo ">>> To decrypt, collect at least $THRESHOLD shares and run the recovery script."


# RECOVER:
#!/bin/bash

set -euo pipefail

### CONFIGURATION ###
ENCRYPTED_PAYLOAD="payload.enc.gpg"
RECONSTRUCTED_KEY="./recovered.key"
#####################

echo "[*] Please enter at least the required number of key shares, one per line (CTRL+D to end):"
ssss-combine -t 3 > "$RECONSTRUCTED_KEY"

echo "[*] Decrypting payload using reconstructed key..."
gpg --batch --yes --decrypt --passphrase-file "$RECONSTRUCTED_KEY" "$ENCRYPTED_PAYLOAD"
