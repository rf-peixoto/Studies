#!/usr/bin/env bash
#
# install.sh - provision proxyd on a fresh VPS.
#
# What it does:
#   * installs a Go toolchain if a suitable one is not present
#   * builds the static, dependency-free proxyd binary
#   * creates a locked-down system user and directory layout
#   * installs a hardened systemd unit (auto-restart, sandboxed)
#   * installs a logrotate policy (weekly, xz -9e max compression, >=3 months)
#   * opens the proxy ports in ufw or iptables
#
# Re-running is safe: it rebuilds the binary and refreshes units without
# clobbering your existing config.json or tokens.json.
#
set -euo pipefail

# ------------------------------------------------------------------ settings
PREFIX_BIN=/opt/proxyd
CONF_DIR=/etc/proxyd
LOG_DIR=/var/log/proxyd
RUN_DIR=/run/proxyd
SVC_USER=proxyd
SVC_GROUP=proxyd
GO_MIN_MAJOR=1
GO_MIN_MINOR=21
GO_VERSION="${GO_VERSION:-1.22.6}"   # used only for the tarball fallback
HTTP_PORT="${HTTP_PORT:-8080}"
SOCKS_PORT="${SOCKS_PORT:-1080}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/proxyd"

msg()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "install.sh must be run as root (use sudo)."
[ -d "$SRC_DIR" ]    || die "Go source not found at $SRC_DIR"

# --------------------------------------------------------------- dependencies
install_pkgs() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends ca-certificates curl xz-utils logrotate
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl xz logrotate
  elif command -v yum >/dev/null 2>&1; then
    yum install -y ca-certificates curl xz logrotate
  else
    warn "No known package manager found; ensure curl, xz and logrotate exist."
  fi
}

go_ok() {
  command -v go >/dev/null 2>&1 || return 1
  local v; v="$(go version | awk '{print $3}' | sed 's/go//')"
  local maj min; maj="${v%%.*}"; min="$(echo "$v" | cut -d. -f2)"
  [ "$maj" -gt "$GO_MIN_MAJOR" ] && return 0
  [ "$maj" -eq "$GO_MIN_MAJOR" ] && [ "$min" -ge "$GO_MIN_MINOR" ] && return 0
  return 1
}

ensure_go() {
  if go_ok; then msg "Using existing Go: $(go version)"; return; fi
  msg "Installing Go toolchain..."
  # First try the distro package; it is simplest and needs no external fetch.
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends golang-go || true
  fi
  if go_ok; then msg "Using distro Go: $(go version)"; return; fi

  # Fallback: official tarball.
  local arch; arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) die "Unsupported CPU architecture for Go tarball: $arch" ;;
  esac
  local tgz="go${GO_VERSION}.linux-${arch}.tar.gz"
  msg "Downloading $tgz ..."
  curl -fSL "https://go.dev/dl/${tgz}" -o "/tmp/${tgz}" \
    || die "Failed to download Go. Check network/egress settings."
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "/tmp/${tgz}"
  export PATH="/usr/local/go/bin:$PATH"
  ln -sf /usr/local/go/bin/go /usr/local/bin/go
  go_ok || die "Go install failed."
  msg "Installed $(go version)"
}

# ---------------------------------------------------------------- build step
build_binary() {
  msg "Building proxyd (stdlib only, no external modules)..."
  install -d "$PREFIX_BIN"
  ( cd "$SRC_DIR" && CGO_ENABLED=0 GOFLAGS=-mod=mod go build -trimpath -o "$PREFIX_BIN/proxyd" . )
  chown root:root "$PREFIX_BIN/proxyd"
  chmod 0755 "$PREFIX_BIN/proxyd"
  msg "Binary installed at $PREFIX_BIN/proxyd"
}

# ------------------------------------------------------------ user + layout
setup_user_and_dirs() {
  if ! getent group "$SVC_GROUP" >/dev/null; then groupadd --system "$SVC_GROUP"; fi
  if ! getent passwd "$SVC_USER" >/dev/null; then
    useradd --system --gid "$SVC_GROUP" --no-create-home \
            --home-dir /nonexistent --shell /usr/sbin/nologin "$SVC_USER"
  fi
  install -d -o "$SVC_USER" -g "$SVC_GROUP" -m 0750 "$CONF_DIR"
  install -d -o "$SVC_USER" -g "$SVC_GROUP" -m 0750 "$LOG_DIR"
  install -d -o "$SVC_USER" -g "$SVC_GROUP" -m 0750 "$RUN_DIR"

  # config.json: install default only if missing, then set port overrides.
  if [ ! -f "$CONF_DIR/config.json" ]; then
    sed -e "s/\":8080\"/\":${HTTP_PORT}\"/" -e "s/\":1080\"/\":${SOCKS_PORT}\"/" \
        "$SCRIPT_DIR/config.example.json" > "$CONF_DIR/config.json"
    chown "$SVC_USER:$SVC_GROUP" "$CONF_DIR/config.json"; chmod 0640 "$CONF_DIR/config.json"
    msg "Wrote default config to $CONF_DIR/config.json"
  else
    warn "Keeping existing $CONF_DIR/config.json"
  fi

  # tokens.json: create empty store if missing.
  if [ ! -f "$CONF_DIR/tokens.json" ]; then
    echo '{"tokens":[]}' > "$CONF_DIR/tokens.json"
    chown "$SVC_USER:$SVC_GROUP" "$CONF_DIR/tokens.json"; chmod 0640 "$CONF_DIR/tokens.json"
  fi

  # proxyd.env: launch flags for systemd (start.sh rewrites this).
  if [ ! -f "$CONF_DIR/proxyd.env" ]; then
    echo 'PROXYD_ARGS=' > "$CONF_DIR/proxyd.env"
    chown "$SVC_USER:$SVC_GROUP" "$CONF_DIR/proxyd.env"; chmod 0640 "$CONF_DIR/proxyd.env"
  fi
}

# ---------------------------------------------------------------- systemd
install_systemd() {
  msg "Installing systemd unit..."
  cat > /etc/systemd/system/proxyd.service <<EOF
[Unit]
Description=proxyd authenticated HTTP/HTTPS/SOCKS5 forward proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SVC_USER
Group=$SVC_GROUP
EnvironmentFile=-$CONF_DIR/proxyd.env
ExecStart=$PREFIX_BIN/proxyd serve --config $CONF_DIR/config.json \$PROXYD_ARGS
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=2
RuntimeDirectory=proxyd
RuntimeDirectoryMode=0750

# --- sandboxing / hardening ---
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
ReadWritePaths=$LOG_DIR $CONF_DIR
# Needed only if you bind to a privileged port (<1024):
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable proxyd >/dev/null 2>&1 || true
  msg "systemd unit installed and enabled."
}

# ---------------------------------------------------------------- logrotate
install_logrotate() {
  msg "Installing logrotate policy (weekly, xz -9e, >=3 months retention)..."
  local xz; xz="$(command -v xz || echo /usr/bin/xz)"
  cat > /etc/logrotate.d/proxyd <<EOF
$LOG_DIR/*.log {
    weekly
    rotate 16
    missingok
    notifempty
    dateext
    compress
    delaycompress
    compresscmd $xz
    uncompresscmd $(command -v unxz || echo /usr/bin/unxz)
    compressext .xz
    compressoptions -9e
    create 0640 $SVC_USER $SVC_GROUP
    sharedscripts
    postrotate
        if [ -f $RUN_DIR/proxyd.pid ]; then
            kill -USR1 "\$(cat $RUN_DIR/proxyd.pid)" 2>/dev/null || true
        fi
    endscript
}
EOF
  msg "logrotate policy installed at /etc/logrotate.d/proxyd"
}

# ---------------------------------------------------------------- firewall
open_ports() {
  msg "Opening proxy ports ${HTTP_PORT}/tcp and ${SOCKS_PORT}/tcp..."
  if command -v ufw >/dev/null 2>&1 && ufw status >/dev/null 2>&1; then
    ufw allow "${HTTP_PORT}/tcp"  || true
    ufw allow "${SOCKS_PORT}/tcp" || true
    msg "ufw rules added."
  elif command -v iptables >/dev/null 2>&1; then
    iptables -C INPUT -p tcp --dport "${HTTP_PORT}" -j ACCEPT 2>/dev/null || \
      iptables -A INPUT -p tcp --dport "${HTTP_PORT}" -j ACCEPT
    iptables -C INPUT -p tcp --dport "${SOCKS_PORT}" -j ACCEPT 2>/dev/null || \
      iptables -A INPUT -p tcp --dport "${SOCKS_PORT}" -j ACCEPT
    warn "iptables rules added in-memory. Persist them (netfilter-persistent save) to survive reboot."
  else
    warn "No ufw/iptables found; open ${HTTP_PORT} and ${SOCKS_PORT} at your cloud firewall."
  fi
}

# ---------------------------------------------------------------- main
install_pkgs
ensure_go
build_binary
setup_user_and_dirs
install_systemd
install_logrotate
open_ports

cat <<EOF

$(msg "proxyd installed successfully.")

Next steps:
  1. Create a token:      sudo ./token.sh add  --user alice --days 30 --rate 10
  2. Start the proxy:     sudo ./start.sh --http $HTTP_PORT --socks $SOCKS_PORT
  3. Watch logs:          sudo tail -f $LOG_DIR/proxyd.log

Client usage:
  HTTP/HTTPS:  curl -x http://alice:<TOKEN>@<SERVER_IP>:$HTTP_PORT   https://example.com
  SOCKS5:      curl -x socks5h://alice:<TOKEN>@<SERVER_IP>:$SOCKS_PORT https://example.com
EOF
