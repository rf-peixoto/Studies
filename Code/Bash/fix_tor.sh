#!/usr/bin/env bash
set -Eeuo pipefail

#############################
# Config
#############################

HS_DIR="${HS_DIR:-/var/lib/tor/privatechat_hidden_service}"
HS_PORT="${HS_PORT:-80}"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-80}"

TORRC="${TORRC:-/etc/tor/torrc}"
TORRC_D_DIR="${TORRC_D_DIR:-/etc/tor/torrc.d}"
PRIVATECHAT_CONF="${PRIVATECHAT_CONF:-${TORRC_D_DIR}/privatechat.conf}"
TOR_SERVICE="${TOR_SERVICE:-tor}"

MANAGED_BEGIN="# >>> privatechat hidden service >>>"
MANAGED_END="# <<< privatechat hidden service <<<"

#############################
# Pretty output
#############################

if [[ -t 1 ]]; then
    RED=$'\033[1;31m'
    GREEN=$'\033[1;32m'
    YELLOW=$'\033[1;33m'
    BLUE=$'\033[1;34m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
else
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    BOLD=""
    RESET=""
fi

log()  { printf "%s[+]%s %s\n" "$GREEN" "$RESET" "$*"; }
warn() { printf "%s[!]%s %s\n" "$YELLOW" "$RESET" "$*" >&2; }
err()  { printf "%s[-]%s %s\n" "$RED" "$RESET" "$*" >&2; }
die()  { err "$*"; exit 1; }

#############################
# Requirements
#############################

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "run this script with sudo"
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

#############################
# Detection helpers
#############################

detect_tor_service() {
    if systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "${TOR_SERVICE}.service"; then
        printf '%s.service\n' "${TOR_SERVICE}"
        return 0
    fi
    if systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "${TOR_SERVICE}"; then
        printf '%s\n' "${TOR_SERVICE}"
        return 0
    fi

    local svc
    svc="$(systemctl list-unit-files --type=service --no-legend 2>/dev/null \
        | awk '{print $1}' \
        | grep -Ei '^tor(@[^[:space:]]+)?(\.service)?$' \
        | head -n1 || true)"
    [[ -n "$svc" ]] || die "could not find a Tor systemd service"
    printf '%s\n' "$svc"
}

detect_tor_user() {
    local owner=""
    local parent_owner=""

    if [[ -d "$HS_DIR" ]]; then
        owner="$(stat -c '%U' "$HS_DIR" 2>/dev/null || true)"
        if [[ -n "$owner" && "$owner" != "root" && "$owner" != "UNKNOWN" ]]; then
            printf '%s\n' "$owner"
            return 0
        fi
    fi

    if [[ -d /var/lib/tor ]]; then
        parent_owner="$(stat -c '%U' /var/lib/tor 2>/dev/null || true)"
        if [[ -n "$parent_owner" && "$parent_owner" != "root" && "$parent_owner" != "UNKNOWN" ]]; then
            printf '%s\n' "$parent_owner"
            return 0
        fi
    fi

    for u in toranon tor debian-tor; do
        if id -u "$u" >/dev/null 2>&1; then
            printf '%s\n' "$u"
            return 0
        fi
    done

    return 1
}

#############################
# File cleanup
#############################

backup_file() {
    local f="$1"
    if [[ -f "$f" ]]; then
        local ts
        ts="$(date +%Y%m%d_%H%M%S)"
        cp -a "$f" "${f}.bak.${ts}"
        log "backup created: ${f}.bak.${ts}"
    fi
}

remove_managed_block_from_torrc() {
    [[ -f "$TORRC" ]] || die "torrc not found: $TORRC"

    backup_file "$TORRC"

    local tmp
    tmp="$(mktemp)"

    awk -v begin="$MANAGED_BEGIN" -v end="$MANAGED_END" '
        $0 == begin { skip=1; next }
        $0 == end   { skip=0; next }
        !skip       { print }
    ' "$TORRC" > "$tmp"

    cat "$tmp" > "$TORRC"
    rm -f "$tmp"

    log "removed old managed block from $TORRC (if present)"
}

remove_old_privatechat_conf() {
    if [[ -f "$PRIVATECHAT_CONF" ]]; then
        backup_file "$PRIVATECHAT_CONF"
        rm -f "$PRIVATECHAT_CONF"
        log "removed old $PRIVATECHAT_CONF"
    fi
}

#############################
# Config creation
#############################

ensure_torrc_d_dir() {
    mkdir -p "$TORRC_D_DIR"
    chmod 0755 "$TORRC_D_DIR"
}

write_privatechat_conf() {
    cat > "$PRIVATECHAT_CONF" <<EOF
${MANAGED_BEGIN}
HiddenServiceDir ${HS_DIR}
HiddenServicePort ${HS_PORT} ${APP_HOST}:${APP_PORT}
${MANAGED_END}
EOF
    chmod 0644 "$PRIVATECHAT_CONF"
    log "wrote clean hidden-service config to $PRIVATECHAT_CONF"
}

#############################
# Hidden service directory
#############################

prepare_hidden_service_dir() {
    local tor_user="$1"

    rm -rf "$HS_DIR"
    mkdir -p "$HS_DIR"

    chown -R "${tor_user}:${tor_user}" "$HS_DIR"
    chmod 0700 "$HS_DIR"

    log "prepared hidden service directory: $HS_DIR"
    log "owner set to: ${tor_user}:${tor_user}"
}

#############################
# Tor actions
#############################

restart_tor_service() {
    local svc="$1"
    log "restarting Tor service: $svc"
    systemctl daemon-reload || true
    systemctl restart "$svc"
}

wait_for_hostname() {
    local tries=0
    local max_tries=30
    local hostname_file="${HS_DIR}/hostname"

    while (( tries < max_tries )); do
        if [[ -f "$hostname_file" ]]; then
            local onion
            onion="$(tr -d '\r\n' < "$hostname_file")"
            if [[ "$onion" =~ ^[a-z2-7]{56}\.onion$ ]]; then
                printf '%s\n' "$onion"
                return 0
            fi
        fi
        sleep 1
        tries=$((tries + 1))
    done

    return 1
}

show_diagnostics() {
    local svc="$1"

    warn "Tor did not start cleanly or did not generate the onion hostname."
    warn "Relevant service status:"
    systemctl status "$svc" --no-pager || true

    warn "Recent Tor logs:"
    journalctl -u "$svc" -n 80 --no-pager || true

    warn "Current config files:"
    printf '--- %s ---\n' "$TORRC"
    sed -n '1,220p' "$TORRC" || true

    if [[ -f "$PRIVATECHAT_CONF" ]]; then
        printf '--- %s ---\n' "$PRIVATECHAT_CONF"
        sed -n '1,220p' "$PRIVATECHAT_CONF" || true
    fi

    if [[ -d "$HS_DIR" ]]; then
        warn "Directory details:"
        ls -ld /var/lib/tor "$HS_DIR" || true
    fi
}

#############################
# Main
#############################

main() {
    require_root
    require_cmd systemctl
    require_cmd awk
    require_cmd grep
    require_cmd sed
    require_cmd stat
    require_cmd date
    require_cmd mktemp
    require_cmd journalctl

    command -v tor >/dev/null 2>&1 || die "Tor is not installed"

    local svc
    svc="$(detect_tor_service)"
    log "detected Tor service: $svc"

    local tor_user
    tor_user="$(detect_tor_user || true)"
    [[ -n "${tor_user:-}" ]] || die "could not determine the Tor runtime user"
    log "detected Tor user: $tor_user"

    [[ -f "$TORRC" ]] || die "torrc not found: $TORRC"

    remove_managed_block_from_torrc
    remove_old_privatechat_conf
    ensure_torrc_d_dir
    write_privatechat_conf
    prepare_hidden_service_dir "$tor_user"

    restart_tor_service "$svc"

    if ! systemctl is-active --quiet "$svc"; then
        show_diagnostics "$svc"
        die "Tor service is not active after restart"
    fi

    local onion=""
    onion="$(wait_for_hostname || true)"
    if [[ -z "$onion" ]]; then
        show_diagnostics "$svc"
        die "Tor is active, but no valid onion hostname was generated"
    fi

    log "success"
    printf "%sOnion address:%s %s\n" "$BOLD" "$RESET" "$onion"
    printf "%sHidden service config:%s %s\n" "$BOLD" "$RESET" "$PRIVATECHAT_CONF"
    printf "%sHidden service dir:%s %s\n" "$BOLD" "$RESET" "$HS_DIR"
}

main "$@"
