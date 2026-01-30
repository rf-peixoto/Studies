#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# Minimal per-host ACME (acme.sh) wildcard issuance via Cloudflare DNS-01
# - Creates /etc/cert-agent.env with CF_Token
# - Installs acme.sh (under /root/.acme.sh)
# - Issues/renews a wildcard + apex cert once (EC-256)
# - Installs cert/key to /etc/ssl/<zone>/
# - Reloads nginx
# - Installs a host agent wrapper: /usr/local/sbin/cert-agent-renew
#
# Assumptions:
# - You run this as root (recommended).
# - nginx is already installed and configured to use the installed cert paths,
#   OR you will update your nginx config after the script to point to:
#     ssl_certificate     /etc/ssl/<zone>/fullchain.pem;
#     ssl_certificate_key /etc/ssl/<zone>/privkey.pem;
# - DNS for <zone> is hosted on Cloudflare and the token can edit DNS TXT records.
# ------------------------------------------------------------

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Please run as root (e.g., sudo -i; then run this script)." >&2
    exit 1
  fi
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

detect_pkg_mgr() {
  if have_cmd apt-get; then echo "apt"
  elif have_cmd dnf; then echo "dnf"
  elif have_cmd yum; then echo "yum"
  elif have_cmd apk; then echo "apk"
  else
    echo "unknown"
  fi
}

install_deps() {
  local pmgr
  pmgr="$(detect_pkg_mgr)"

  case "$pmgr" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -y
      apt-get install -y curl socat openssl ca-certificates
      ;;
    dnf)
      dnf install -y curl socat openssl ca-certificates
      ;;
    yum)
      yum install -y curl socat openssl ca-certificates
      ;;
    apk)
      apk add --no-cache curl socat openssl ca-certificates
      ;;
    *)
      echo "WARNING: Unknown package manager. Please ensure curl, socat, openssl are installed." >&2
      ;;
  esac
}

prompt() {
  local var_name="$1"
  local msg="$2"
  local secret="${3:-false}"
  local default="${4:-}"

  local val=""
  if [[ "$secret" == "true" ]]; then
    read -r -s -p "${msg}${default:+ [$default]}: " val
    echo
  else
    read -r -p "${msg}${default:+ [$default]}: " val
  fi

  if [[ -z "$val" && -n "$default" ]]; then
    val="$default"
  fi

  if [[ -z "$val" ]]; then
    echo "ERROR: ${var_name} cannot be empty." >&2
    exit 1
  fi

  printf -v "$var_name" '%s' "$val"
}

write_env_file() {
  local cf_token="$1"
  local env_path="/etc/cert-agent.env"

  umask 077
  cat > "$env_path" <<EOF
# Root-readable only. Used by acme.sh dns_cf plugin.
CF_Token=${cf_token}
EOF
  chown root:root "$env_path"
  chmod 600 "$env_path"
  echo "OK: wrote $env_path (mode 600)"
}

install_acmesh() {
  if [[ -x "/root/.acme.sh/acme.sh" ]]; then
    echo "OK: acme.sh already installed at /root/.acme.sh/acme.sh"
    return 0
  fi

  echo "Installing acme.sh..."
  curl -fsSL https://get.acme.sh | sh -s email="$1"
  if [[ ! -x "/root/.acme.sh/acme.sh" ]]; then
    echo "ERROR: acme.sh installation did not produce /root/.acme.sh/acme.sh" >&2
    exit 1
  fi
  echo "OK: installed acme.sh"
}

ensure_nginx() {
  if ! have_cmd nginx; then
    echo "WARNING: nginx not found in PATH. This script will still proceed, but reload will fail." >&2
  fi
  if have_cmd systemctl; then
    systemctl is-enabled nginx >/dev/null 2>&1 || true
  fi
}

issue_and_install_cert() {
  local zone="$1"
  local wildcard="*.${zone}"
  local apex="${zone}"
  local acme="/root/.acme.sh/acme.sh"
  local cert_dir="/etc/ssl/${zone}"
  local key_path="${cert_dir}/privkey.pem"
  local chain_path="${cert_dir}/fullchain.pem"

  mkdir -p "$cert_dir"
  chown root:root "$cert_dir"
  chmod 700 "$cert_dir"

  # Load CF token for this shell session (acme.sh reads it)
  # shellcheck disable=SC1091
  source /etc/cert-agent.env

  echo "Issuing (or renewing if needed) EC-256 cert for: ${wildcard}, ${apex}"
  # Use Let's Encrypt production by default.
  # For initial testing, you can add: --staging
  "$acme" --issue --dns dns_cf -d "$wildcard" -d "$apex" --keylength ec-256 --ecc

  echo "Installing cert to:"
  echo "  key:   $key_path"
  echo "  chain: $chain_path"

  "$acme" --install-cert -d "$wildcard" --ecc \
    --key-file "$key_path" \
    --fullchain-file "$chain_path" \
    --reloadcmd "systemctl reload nginx"

  chown root:root "$key_path" "$chain_path"
  chmod 600 "$key_path" "$chain_path"

  echo "OK: installed cert files"

  if have_cmd systemctl; then
    echo "Reloading nginx..."
    systemctl reload nginx || {
      echo "ERROR: nginx reload failed. Check nginx config and certificate paths." >&2
      exit 1
    }
    echo "OK: nginx reloaded"
  else
    echo "WARNING: systemctl not available; nginx reload not executed." >&2
  fi

  echo "Deployed certificate details:"
  openssl x509 -in "$chain_path" -noout -subject -issuer -enddate -fingerprint -sha256
}

install_agent_wrapper() {
  local wrapper="/usr/local/sbin/cert-agent-renew"

  cat > "$wrapper" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ZONE="${1:-}"
if [[ -z "$ZONE" ]]; then
  echo "usage: cert-agent-renew <zone>" >&2
  exit 2
fi

ACME="/root/.acme.sh/acme.sh"
if [[ ! -x "$ACME" ]]; then
  echo "ERROR: acme.sh not found at $ACME" >&2
  exit 1
fi

ENV_FILE="/etc/cert-agent.env"
if [[ ! -r "$ENV_FILE" ]]; then
  echo "ERROR: env file not readable: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

WILDCARD="*.${ZONE}"
APEX="${ZONE}"
CERT_DIR="/etc/ssl/${ZONE}"
KEY_PATH="${CERT_DIR}/privkey.pem"
CHAIN_PATH="${CERT_DIR}/fullchain.pem"
RELOAD_CMD="systemctl reload nginx"

install -d -m 700 "$CERT_DIR"

# Renew/issue if needed (acme.sh is idempotent)
"$ACME" --issue --dns dns_cf -d "$WILDCARD" -d "$APEX" --keylength ec-256 --ecc >/tmp/acme_${ZONE}.out 2>/tmp/acme_${ZONE}.err || true

# Install (idempotent) + reload
"$ACME" --install-cert -d "$WILDCARD" --ecc \
  --key-file "$KEY_PATH" \
  --fullchain-file "$CHAIN_PATH" \
  --reloadcmd "$RELOAD_CMD" >/tmp/install_${ZONE}.out 2>/tmp/install_${ZONE}.err

chown root:root "$KEY_PATH" "$CHAIN_PATH"
chmod 600 "$KEY_PATH" "$CHAIN_PATH"

NOT_AFTER="$(openssl x509 -in "$CHAIN_PATH" -noout -enddate | cut -d= -f2)"
FPR="$(openssl x509 -in "$CHAIN_PATH" -noout -fingerprint -sha256 | cut -d= -f2)"

printf '{"ok":true,"zone":"%s","not_after":"%s","fingerprint_sha256":"%s"}\n' \
  "$ZONE" "$NOT_AFTER" "$FPR"
EOF

  chown root:root "$wrapper"
  chmod 755 "$wrapper"
  echo "OK: installed agent wrapper at $wrapper"
}

print_nginx_snippet() {
  local zone="$1"
  cat <<EOF

------------------------------------------------------------
nginx TLS config snippet (ensure your server block uses these):
  ssl_certificate     /etc/ssl/${zone}/fullchain.pem;
  ssl_certificate_key /etc/ssl/${zone}/privkey.pem;

After updating nginx config:
  nginx -t && systemctl reload nginx
------------------------------------------------------------

EOF
}

main() {
  require_root
  install_deps

  local ZONE CF_TOKEN EMAIL
  prompt ZONE "Enter your DNS zone (apex), e.g. example.com"
  prompt CF_TOKEN "Enter your Cloudflare API Token (Zone:DNS:Edit for ${ZONE})" true
  prompt EMAIL "Enter email for Let's Encrypt account registration" false "admin@${ZONE}"

  write_env_file "$CF_TOKEN"
  ensure_nginx
  install_acmesh "$EMAIL"
  install_agent_wrapper
  issue_and_install_cert "$ZONE"
  print_nginx_snippet "$ZONE"

  echo "DONE."
  echo "You can test the agent wrapper with:"
  echo "  /usr/local/sbin/cert-agent-renew ${ZONE}"
}

main "$@"
