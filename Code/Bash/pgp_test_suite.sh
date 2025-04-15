#!/bin/bash
set -e

# =================== CONFIGURATION ===================
TEST_DIR="pgp_test_suite"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"
LOG="testlog.txt"
echo "[•] Starting PGP misuse test suite..." > "$LOG"

# =================== UTILITY FUNCTIONS ===================
function log() {
    echo -e "[+] $1" | tee -a "$LOG"
}

function separator() {
    echo -e "\n--- $1 ---\n" >> "$LOG"
}

# =================== SCENARIO 1 ===================
separator "SCENARIO 1: Signature Confusion — Multiple Signers"

log "Generating two test keys: Legit and Malicious"
gpg --batch --passphrase '' --quick-generate-key "Legit User <legit@example.com>" default default 0
gpg --batch --passphrase '' --quick-generate-key "Malicious Actor <malicious@example.com>" default default 0

echo "Important update coming soon." > msg1.txt

gpg --local-user "legit@example.com" --clearsign msg1.txt -o signed_by_legit.asc
gpg --local-user "malicious@example.com" --clearsign msg1.txt -o signed_by_malicious.asc

log "Signed message by both users created."
log "Verifying legit signature:"
gpg --verify signed_by_legit.asc >> "$LOG" 2>&1
log "Verifying malicious signature:"
gpg --verify signed_by_malicious.asc >> "$LOG" 2>&1

# =================== SCENARIO 2 ===================
separator "SCENARIO 2: Signature Verification with Weak Hash (SHA1)"
echo "Weak hash test." > msg2.txt
gpg --digest-algo SHA1 --clearsign msg2.txt -o signed_sha1.asc

log "Verifying SHA-1 signed message:"
gpg --verify signed_sha1.asc >> "$LOG" 2>&1

# =================== SCENARIO 3 ===================
separator "SCENARIO 3: Poisoned UID"
log "Injecting a poisoned UID into legit@example.com"

gpg --batch --command-fd 0 --edit-key "legit@example.com" >> "$LOG" 2>&1 <<EOF
adduid
Malicious UID
hacker@fake.com
comment
Ouch
save
EOF

log "Exporting and re-importing poisoned key"
gpg --export -a "legit@example.com" > poisoned_legit.asc
gpg --delete-key --yes "legit@example.com"
gpg --import poisoned_legit.asc >> "$LOG" 2>&1

log "Poisoned key present with malicious UID"

# =================== SCENARIO 4 ===================
separator "SCENARIO 4: Expired Key Signature"

log "Generating short-lived key for test..."
gpg --quick-generate-key "Short Key <short@expire.com>" default default 1m

echo "Short-lived key test" > msg3.txt
sleep 70

log "Trying to sign with expired key:"
if gpg --local-user "short@expire.com" --clearsign msg3.txt -o signed_expired.asc >> "$LOG" 2>&1; then
    log "Signature succeeded (unexpected)"
else
    log "Signature failed due to expiration (expected)"
fi

# =================== SCENARIO 5 ===================
separator "SCENARIO 5: Revoked Key"

log "Generating revocation cert for legit@example.com"
gpg --output revoke_cert.asc --gen-revoke "legit@example.com" >> "$LOG" 2>&1
gpg --import revoke_cert.asc >> "$LOG" 2>&1

log "Verifying previously signed message (should now show revoked key):"
gpg --verify signed_by_legit.asc >> "$LOG" 2>&1

# =================== SCENARIO 6 ===================
separator "SCENARIO 6: Signature Without Public Key"

log "Creating detached signature"
echo "Detached test" > msg4.txt
gpg --local-user "malicious@example.com" --armor --detach-sign msg4.txt -o msg4.txt.asc

log "Deleting malicious@example.com key"
gpg --delete-secret-keys --yes "malicious@example.com" >> "$LOG" 2>&1
gpg --delete-keys --yes "malicious@example.com" >> "$LOG" 2>&1

log "Attempting to verify signature with missing key:"
gpg --verify msg4.txt.asc msg4.txt >> "$LOG" 2>&1

# =================== WRAP-UP ===================
separator "SUMMARY"
log "All scenarios executed. Check $TEST_DIR/$LOG for details."

echo -e "\n[✔] Test suite completed."
