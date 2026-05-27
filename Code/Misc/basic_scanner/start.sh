#!/usr/bin/env bash
# start.sh - Activates the local venv, ensures Docker is reachable, then runs the scanner inside Docker.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

info() { printf '[*] %s\n' "$*"; }
err()  { printf '[-] %s\n' "$*" >&2; }

COMPOSE_CMD=()

if [ ! -x "$VENV_DIR/bin/python" ]; then
    err "Local venv was not found at $VENV_DIR. Run ./install.sh first."
    exit 1
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

if ! command -v docker >/dev/null 2>&1; then
    err "Docker was not found. Run ./install.sh after installing Docker."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    info "Docker daemon is not reachable. Trying to start it."
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl start docker || true
    elif command -v service >/dev/null 2>&1; then
        sudo service docker start || true
    fi
    sleep 2
fi

if ! docker info >/dev/null 2>&1; then
    err "Docker daemon is still not reachable. Run: sudo systemctl enable --now docker"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    err "Docker Compose was not found. Run ./install.sh after installing Docker Compose."
    exit 1
fi

if [ $# -lt 1 ]; then
    echo "Usage: $0 <domains_list.txt> [scanner options]"
    echo "Example: $0 domains.txt --skip-nuclei"
    echo "Example: $0 domains.txt --domains-concurrency 3 --nuclei-severity medium,high,critical"
    exit 1
fi

DOMAINS_FILE="$1"
shift

if [ ! -f "$DOMAINS_FILE" ]; then
    err "Domains file not found: $DOMAINS_FILE"
    exit 1
fi

mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/scan_results"
cp "$DOMAINS_FILE" "$SCRIPT_DIR/data/domains.txt"

cat <<MSG
[*] Starting scan inside Docker.
    Input:   $DOMAINS_FILE
    Output:  $SCRIPT_DIR/scan_results
    Limits:  4.0 CPUs, 10 GB RAM
    Venv:    $VENV_DIR
MSG

"${COMPOSE_CMD[@]}" run --rm scanner /data/domains.txt --output-dir /output "$@"
