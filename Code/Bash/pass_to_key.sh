#!/usr/bin/env bash
set -Eeuo pipefail

# =========================
# Config
# =========================
KEY_NAME="root_vps_ed25519"
KEY_DIR="/root/.ssh"
KEY_PATH="${KEY_DIR}/${KEY_NAME}"
AUTHORIZED_KEYS="${KEY_DIR}/authorized_keys"
BACKUP_DIR="/root/ssh-hardening-backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE_PATH="/root/${KEY_NAME}_${STAMP}.tar.gz"
SSH_CONFIG="/etc/ssh/sshd_config"

# =========================
# Helpers
# =========================
info()  { printf '[+] %s\n' "$*"; }
warn()  { printf '[!] %s\n' "$*" >&2; }
error() { printf '[-] %s\n' "$*" >&2; }
die()   { error "$*"; exit 1; }

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run this script as root."
}

find_ssh_service() {
    if systemctl list-unit-files 2>/dev/null | grep -q '^sshd\.service'; then
        echo "sshd"
    elif systemctl list-unit-files 2>/dev/null | grep -q '^ssh\.service'; then
        echo "ssh"
    else
        echo ""
    fi
}

backup_file() {
    local file="$1"
    mkdir -p "$BACKUP_DIR"
    cp -a "$file" "${BACKUP_DIR}/$(basename "$file").${STAMP}.bak"
}

ensure_line() {
    local key="$1"
    local value="$2"
    local file="$3"

    if grep -Eq "^[#[:space:]]*${key}[[:space:]]+" "$file"; then
        sed -ri "s|^[#[:space:]]*${key}[[:space:]]+.*|${key} ${value}|g" "$file"
    else
        printf '\n%s %s\n' "$key" "$value" >> "$file"
    fi
}

print_summary() {
    cat <<EOF

========================================
SSH root key login configured
========================================

Private key on VPS:
  ${KEY_PATH}

Public key on VPS:
  ${KEY_PATH}.pub

Download bundle on VPS:
  ${BUNDLE_PATH}

Public key fingerprint:
  $(ssh-keygen -lf "${KEY_PATH}.pub" | awk '{print $2"  "$3}')

Recommended next steps:
  1. Download the private key bundle NOW while this session is still open.
  2. Set strict permissions on your local machine:
       chmod 600 ${KEY_NAME}
  3. Test login in a NEW terminal before closing this one:
       ssh -i ${KEY_NAME} root@YOUR_SERVER_IP
  4. Only after successful test, close the old session.

If your SSH client is Windows OpenSSH:
  ssh -i .\\${KEY_NAME} root@YOUR_SERVER_IP

If you want to download with scp from your local machine:
  scp root@YOUR_SERVER_IP:${BUNDLE_PATH} .

IMPORTANT:
- The private key was generated on the server, which is convenient but less secure than generating it locally.
- Keep this session open until you confirm the new key-based login works.

EOF
}

# =========================
# Main
# =========================
require_root

info "Preparing directories..."
mkdir -p "$KEY_DIR" "$BACKUP_DIR"
chmod 700 "$KEY_DIR"
touch "$AUTHORIZED_KEYS"
chmod 600 "$AUTHORIZED_KEYS"

if [[ -e "$KEY_PATH" || -e "${KEY_PATH}.pub" ]]; then
    die "Key path already exists: ${KEY_PATH}. Move or remove it first."
fi

info "Generating new ED25519 SSH key pair for root..."
ssh-keygen -t ed25519 -a 100 -f "$KEY_PATH" -N "" -C "root@$(hostname)-${STAMP}" >/dev/null

info "Installing public key into authorized_keys..."
cat "${KEY_PATH}.pub" >> "$AUTHORIZED_KEYS"
sort -u "$AUTHORIZED_KEYS" -o "$AUTHORIZED_KEYS"
chmod 600 "$AUTHORIZED_KEYS"
chmod 700 "$KEY_DIR"

info "Backing up SSH configuration..."
[[ -f "$SSH_CONFIG" ]] || die "Could not find ${SSH_CONFIG}"
backup_file "$SSH_CONFIG"

info "Configuring SSH for root key-based login only..."
ensure_line "PubkeyAuthentication" "yes" "$SSH_CONFIG"
ensure_line "PermitRootLogin" "prohibit-password" "$SSH_CONFIG"
ensure_line "PasswordAuthentication" "yes" "$SSH_CONFIG"
ensure_line "KbdInteractiveAuthentication" "no" "$SSH_CONFIG"
ensure_line "ChallengeResponseAuthentication" "no" "$SSH_CONFIG"
ensure_line "PermitEmptyPasswords" "no" "$SSH_CONFIG"
ensure_line "UsePAM" "yes" "$SSH_CONFIG"

info "Validating SSH configuration..."
sshd -t || die "sshd_config validation failed. Your original config backup is in ${BACKUP_DIR}"

SERVICE_NAME="$(find_ssh_service)"
[[ -n "$SERVICE_NAME" ]] || die "Could not determine SSH service name (ssh or sshd). Reload it manually after checking config."

info "Reloading SSH service: ${SERVICE_NAME}"
systemctl reload "$SERVICE_NAME" || die "Failed to reload ${SERVICE_NAME}"

info "Creating downloadable key bundle..."
tar -czf "$BUNDLE_PATH" -C "$KEY_DIR" "$(basename "$KEY_PATH")" "$(basename "${KEY_PATH}.pub")"

chmod 600 "$KEY_PATH" "${KEY_PATH}.pub" "$BUNDLE_PATH"

print_summary
