#!/usr/bin/env bash

# In order for this to work, you must change app.py __main__:

#import os
#
#if __name__ == "__main__":
#    host = os.getenv("HOST", "127.0.0.1")
#    port = int(os.getenv("PORT", "5000"))
#    socketio.run(app, host=host, port=port, debug=False)


set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_FILE="${APP_DIR}/app.py"

TORRC="/etc/tor/torrc"
HS_DIR="/var/lib/tor/cryptochat_hidden_service"
HS_HOSTNAME_FILE="${HS_DIR}/hostname"
CONFIG_BEGIN="# >>> cryptochat hidden service >>>"
CONFIG_END="# <<< cryptochat hidden service <<<"

print_info() {
    printf '\033[1;37m[INFO]\033[0m %s\n' "$1"
}

print_warn() {
    printf '\033[1;33m[WARN]\033[0m %s\n' "$1"
}

print_error() {
    printf '\033[1;31m[ERR ]\033[0m %s\n' "$1" >&2
}

die() {
    print_error "$1"
    exit 1
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "This script must be run as root. Use: sudo ./start.sh"
    fi
}

check_dependencies() {
    command -v tor >/dev/null 2>&1 || die "Tor is not installed."
    command -v systemctl >/dev/null 2>&1 || die "systemctl is not available on this system."
    command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
    [[ -f "${APP_FILE}" ]] || die "Could not find app.py in ${APP_DIR}"
    [[ -f "${TORRC}" ]] || die "Could not find Tor config at ${TORRC}"
}

detect_tor_service_name() {
    if systemctl list-unit-files | grep -q '^tor\.service'; then
        echo "tor"
        return
    fi

    if systemctl list-unit-files | grep -q '^tor@default\.service'; then
        echo "tor@default"
        return
    fi

    die "Could not determine Tor systemd service name."
}

ensure_tor_user() {
    if id -u debian-tor >/dev/null 2>&1; then
        echo "debian-tor"
        return
    fi

    if id -u tor >/dev/null 2>&1; then
        echo "tor"
        return
    fi

    die "Could not find a Tor service user (expected 'debian-tor' or 'tor')."
}

ensure_hidden_service_dir() {
    local tor_user="$1"

    mkdir -p "${HS_DIR}"
    chown -R "${tor_user}:${tor_user}" "${HS_DIR}"
    chmod 0700 "${HS_DIR}"
}

ensure_torrc_block() {
    if grep -Fq "${CONFIG_BEGIN}" "${TORRC}"; then
        print_info "Hidden service block already exists in torrc."
        return
    fi

    print_info "Appending hidden service configuration to ${TORRC}."

    cat >> "${TORRC}" <<EOF

${CONFIG_BEGIN}
HiddenServiceDir ${HS_DIR}
HiddenServicePort 80 127.0.0.1:80
${CONFIG_END}
EOF
}

validate_tor_config() {
    print_info "Validating Tor configuration."
    tor --verify-config -f "${TORRC}" >/dev/null
}

restart_tor() {
    local tor_service="$1"

    print_info "Restarting Tor service: ${tor_service}"
    systemctl daemon-reload
    systemctl restart "${tor_service}"
    systemctl enable "${tor_service}" >/dev/null 2>&1 || true
    systemctl is-active --quiet "${tor_service}" || die "Tor service failed to start."
}

wait_for_onion() {
    print_info "Waiting for Tor to generate the hidden service hostname."

    for _ in $(seq 1 30); do
        if [[ -f "${HS_HOSTNAME_FILE}" ]]; then
            local onion
            onion="$(tr -d '\r\n' < "${HS_HOSTNAME_FILE}")"
            if [[ -n "${onion}" ]]; then
                echo "${onion}"
                return
            fi
        fi
        sleep 1
    done

    die "Timed out waiting for ${HS_HOSTNAME_FILE}"
}

kill_existing_python_on_80() {
    if command -v ss >/dev/null 2>&1; then
        local pids
        pids="$(ss -ltnp '( sport = :80 )' 2>/dev/null | awk -F'pid=' '/python|gunicorn|flask/ {print $2}' | awk -F',' '{print $1}' | sort -u || true)"
        if [[ -n "${pids}" ]]; then
            print_warn "Existing process(es) already listening on port 80: ${pids}"
            print_warn "Stopping them."
            kill -9 ${pids} || true
            sleep 1
        fi
    fi
}

start_app() {
    cd "${APP_DIR}"

    export HOST="127.0.0.1"
    export PORT="80"

    print_info "Starting Flask app on http://127.0.0.1:80"
    print_warn "This uses the Flask development server. Use Gunicorn or uWSGI later for production."

    exec python3 app.py
}

main() {
    require_root
    check_dependencies

    local tor_service
    tor_service="$(detect_tor_service_name)"

    local tor_user
    tor_user="$(ensure_tor_user)"

    ensure_hidden_service_dir "${tor_user}"
    ensure_torrc_block
    validate_tor_config
    restart_tor "${tor_service}"

    local onion
    onion="$(wait_for_onion)"

    printf '\n'
    printf '\033[1;32m[ONION]\033[0m %s\n' "http://${onion}"
    printf '\n'

    kill_existing_python_on_80
    start_app
}

main "$@"
