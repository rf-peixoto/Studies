#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Fedora Tor reinstall + fixed ownership + diagnostics
# ==============================================================================

EXCLUDE_COUNTRIES=("{de}" "{fr}" "{us}")

SOCKS_BIND_ADDR="127.0.0.1"
SOCKS_PORT="9050"

TOR_REPO_FILE="/etc/yum.repos.d/Tor.repo"
TOR_CONFIG_FILE="/etc/tor/torrc"
TOR_DATA_DIR="/var/lib/tor"

CHECK_TOR_URL="https://check.torproject.org/api/ip"
FALLBACK_IP_URL="https://api.ipify.org"

REMOVE_PACKAGES=(
  tor
  torsocks
  proxychains-ng
)

INSTALL_PACKAGES=(
  tor
  torsocks
  proxychains-ng
  curl
  iproute
  lsof
)

C_RESET='\033[0m'
C_RED='\033[31m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_BLUE='\033[34m'

msg()  { printf "${C_BLUE}[*]${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}[+]${C_RESET} %s\n" "$*"; }
warn() { printf "${C_YELLOW}[!]${C_RESET} %s\n" "$*" >&2; }
die()  { printf "${C_RED}[-]${C_RESET} %s\n" "$*" >&2; exit 1; }

require_root() {
    [[ "$EUID" -eq 0 ]] || die "Run as root"
}

join_by_comma() {
    local IFS=","
    printf '%s' "$*"
}

stop_tor() {
    msg "Stopping Tor..."
    systemctl stop tor 2>/dev/null || true
    systemctl disable tor 2>/dev/null || true
    ok "Tor stopped."
}

remove_old() {
    msg "Removing previous installation..."
    dnf -y remove "${REMOVE_PACKAGES[@]}" || true
    rm -rf /etc/tor /var/lib/tor /var/log/tor /run/tor
    rm -f /etc/yum.repos.d/Tor.repo
    ok "Old installation removed."
}

install_repo() {
    msg "Writing Tor repository..."
    cat > "${TOR_REPO_FILE}" <<'EOF'
[tor]
name=Tor for Fedora $releasever - $basearch
baseurl=https://rpm.torproject.org/fedora/$releasever/$basearch
enabled=1
gpgcheck=1
gpgkey=https://rpm.torproject.org/fedora/public_gpg.key
cost=100
EOF
}

install_packages() {
    msg "Installing packages..."
    dnf -y clean all
    dnf -y makecache
    dnf -y install "${INSTALL_PACKAGES[@]}"
    ok "Packages installed."
}

write_torrc() {
    msg "Writing torrc..."

    mkdir -p /etc/tor

    local exclude_line
    exclude_line="$(join_by_comma "${EXCLUDE_COUNTRIES[@]}")"

    cat > "${TOR_CONFIG_FILE}" <<EOF
SocksPort ${SOCKS_BIND_ADDR}:${SOCKS_PORT}
AvoidDiskWrites 1
ExcludeNodes ${exclude_line}
StrictNodes 1
EOF

    chmod 0644 "${TOR_CONFIG_FILE}"

    ok "torrc written."
}

fix_permissions() {
    msg "Fixing Tor filesystem ownership..."

    mkdir -p /var/lib/tor
    mkdir -p /var/log/tor

    chown -R toranon:toranon /var/lib/tor
    chmod 700 /var/lib/tor

    ok "Ownership fixed."
}

verify_config() {
    msg "Verifying config as toranon..."

    sudo -u toranon tor --verify-config -f "${TOR_CONFIG_FILE}" || {
        warn "Verification failed"
        cat "${TOR_CONFIG_FILE}"
        exit 1
    }

    ok "Config verified."
}

check_port_conflict() {
    msg "Checking port conflict..."

    if lsof -i :"${SOCKS_PORT}" >/dev/null 2>&1; then
        warn "Port ${SOCKS_PORT} already in use:"
        lsof -i :"${SOCKS_PORT}"
        die "Port conflict"
    fi

    ok "Port free."
}

start_tor() {
    msg "Starting Tor..."
    systemctl daemon-reload
    systemctl enable --now tor
    sleep 5
    ok "Tor started."
}

check_service() {
    msg "Checking service..."
    systemctl is-active --quiet tor || {
        journalctl -u tor -b -n 100 --no-pager
        die "Tor service failed"
    }
    ok "Service active."
}

check_listener() {
    msg "Checking listener..."
    ss -ltn | grep ":${SOCKS_PORT}" || {
        journalctl -u tor -b -n 100 --no-pager
        die "No listener on ${SOCKS_PORT}"
    }
    ok "Listener active."
}

test_direct_proxy() {
    msg "Testing direct SOCKS proxy..."

    curl --proxy "socks5h://${SOCKS_BIND_ADDR}:${SOCKS_PORT}" \
         --max-time 30 \
         "${CHECK_TOR_URL}" || {
        warn "Primary check failed, trying fallback..."
        curl --proxy "socks5h://${SOCKS_BIND_ADDR}:${SOCKS_PORT}" \
             --max-time 30 \
             "${FALLBACK_IP_URL}" || die "SOCKS proxy failed"
    }

    ok "SOCKS proxy works."
}

test_torsocks() {
    msg "Testing torsocks..."
    torsocks curl --max-time 30 "${CHECK_TOR_URL}" || die "torsocks failed"
    ok "torsocks works."
}

test_proxychains() {
    msg "Testing proxychains..."
    proxychains4 -q curl --max-time 30 "${CHECK_TOR_URL}" || die "proxychains failed"
    ok "proxychains works."
}

main() {
    require_root
    stop_tor
    remove_old
    install_repo
    install_packages
    write_torrc
    fix_permissions
    verify_config
    check_port_conflict
    start_tor
    check_service
    check_listener
    test_direct_proxy
    test_torsocks
    test_proxychains

    echo
    ok "All checks passed."
    echo "SOCKS proxy: ${SOCKS_BIND_ADDR}:${SOCKS_PORT}"
}

main
