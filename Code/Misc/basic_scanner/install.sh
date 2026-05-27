#!/usr/bin/env bash
# install.sh - Starts Docker, creates/updates the local Python venv, installs requirements,
# and builds the Docker image used by scan.sh/start.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

info() { printf '[*] %s\n' "$*"; }
ok()   { printf '[✓] %s\n' "$*"; }
err()  { printf '[-] %s\n' "$*" >&2; }

require_command() {
    local cmd="$1"
    local msg="$2"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        err "$msg"
        exit 1
    fi
}

require_docker_binary() {
    if ! command -v docker >/dev/null 2>&1; then
        err "Docker was not found. Install Docker Engine before running this installer."
        err "Fedora example: sudo dnf install -y docker docker-compose-plugin && sudo systemctl enable --now docker"
        exit 1
    fi
}

start_docker_daemon() {
    if docker info >/dev/null 2>&1; then
        ok "Docker daemon is reachable."
        return 0
    fi

    info "Docker is installed, but the daemon is not reachable. Trying to start it."

    if command -v systemctl >/dev/null 2>&1; then
        if systemctl list-unit-files docker.service >/dev/null 2>&1; then
            info "sudo may ask for your password to start docker.service."
            sudo systemctl start docker || true
        fi
    elif command -v service >/dev/null 2>&1; then
        info "sudo may ask for your password to start the docker service."
        sudo service docker start || true
    fi

    sleep 2

    if ! docker info >/dev/null 2>&1; then
        err "Docker daemon is still not reachable."
        err "Start Docker manually, then rerun ./install.sh."
        err "Common Linux commands:"
        err "  sudo systemctl enable --now docker"
        err "  sudo usermod -aG docker \$USER   # then log out and back in"
        exit 1
    fi

    ok "Docker daemon started and is reachable."
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(docker-compose)
    else
        err "Docker Compose was not found. Install Docker Compose v2 or legacy docker-compose."
        err "Fedora example: sudo dnf install -y docker-compose-plugin"
        exit 1
    fi
}

setup_venv() {
    require_command "$PYTHON_BIN" "Python 3 was not found. Install python3 first."

    info "Creating/updating local Python virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"

    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"

    python -m pip install --upgrade pip
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        python -m pip install -r "$SCRIPT_DIR/requirements.txt"
    else
        python -m pip install aiohttp aiodns ipwhois
    fi

    ok "Local Python venv is ready."
}

COMPOSE_CMD=()

require_docker_binary
start_docker_daemon
detect_compose
setup_venv

mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/scan_results"
chmod +x "$SCRIPT_DIR/docker-entrypoint.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/scan.sh" 2>/dev/null || true

info "Building scanner Docker image."
info "The Docker image also contains its own venv and the Go-based recon tools."
"${COMPOSE_CMD[@]}" build

ok "Install completed successfully."
cat <<'MSG'

Run a scan with:
  ./scan.sh domains.txt

scan.sh only passes the domains file and options to the Dockerized scanner.
Results will be written to:
  ./scan_results/
MSG
