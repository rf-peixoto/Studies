#!/usr/bin/env bash
set -euo pipefail

#########################################################
# Multi-user Kali SSH container provisioner
#
# Config precedence (lowest -> highest):
#   1. Built-in defaults below
#   2. config.env (next to this script, or --config PATH)
#   3. Command-line flags (--total, --mem, --cpus, ...)
#########################################################

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

#########################################################
# BUILT-IN DEFAULTS  (override via config.env or flags)
#########################################################

TOTAL_USERS=5

BASE_DIR="$PWD/kali_container_vps"
IMAGE_NAME="multiuser-kali-ssh:latest"
CONTAINER_PREFIX="user"
SSH_USER="user"

# Resource limits per container. Empty string = no limit for that dimension.
MEM_LIMIT="8g"
CPU_LIMIT="2"          # number of cores, e.g. "1.5"; "" to disable
PIDS_LIMIT="512"       # max processes; "" to disable
DISK_LIMIT="10g"       # per-container writable-layer cap; needs a quota-capable
                       # storage driver (xfs+pquota / btrfs / zfs). "" to disable.
REQUIRE_DISK_QUOTA=0   # 1 = abort if the driver can't enforce DISK_LIMIT

SSH_PORT_START=65535
SERVICE_PORT_START=20001

# Networking
NETWORK_NAME="kalinet"
NETWORK_MODE="isolated"        # isolated = one bridge per user (users can't see
                               # each other); shared = all users on one bridge
ALLOW_TCP_FORWARDING="no"      # "yes" if users need SSH tunneling / pivoting

# Lifetime
DEFAULT_TTL_DAYS=0             # 0 = containers never auto-expire

# Access files
PUBLIC_IP=""                   # leave empty to auto-detect the server's public IP

#########################################################
# RUNTIME STATE (do not edit)
#########################################################

MODE="default"
ADD_USERS=0
SPEC=""
PURGE_KEYS=0
ASSUME_YES=0
DRY_RUN=0
TTL_DAYS=""            # per-invocation TTL override (create/add/format)
RESTORE_FILE=""
EXEC_CMD=()
DISK_QUOTA_OK=0
SERVER_IP="YOUR_SERVER_IP"

# CLI override capture (applied after config.env is sourced)
OVER_CONFIG=""
OVER_TOTAL=""; OVER_MEM=""; OVER_CPUS=""; OVER_PIDS=""; OVER_DISK=""
OVER_IMAGE=""; OVER_SSH_USER=""; OVER_BASE_DIR=""; OVER_PUBLIC_IP=""

log()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[-]\033[0m $*" >&2; }
dbg()  { echo -e "\033[1;34m[dry-run]\033[0m $*" >&2; }

#########################################################
# USAGE
#########################################################

usage() {
    cat <<EOF
Usage: sudo $0 [command] [modifiers]

Provisioning:
  (no command)             Create users 1..TOTAL_USERS ($TOTAL_USERS). Existing ones untouched.
  --add-users N            Add N new users after the highest existing number.

Lifecycle (TARGET = all | N | A-B | 1,3,5):
  --list, --status         Table of every managed container (ports, state, health,
                           live CPU/MEM, key status, expiry).
  --info    TARGET         Reprint the full access block for the given user(s).
  --start   TARGET         Start container(s).
  --stop    TARGET         Stop container(s).
  --restart TARGET         Restart container(s).
  --logs    TARGET         Show recent sshd logs for container(s).
  --exec    TARGET -- CMD  Run CMD inside each selected container.
  --remove  TARGET         Delete container(s). Keys are KEPT unless --purge-keys.
  --format  TARGET         Recreate container(s) fresh, REUSING key + ports (+ remaining TTL).

Image:
  --rebuild-image          Rebuild the base image (--no-cache); containers untouched.
  --format-image           Rebuild image fresh AND recreate every container, each
                           keeping its key, ports and remaining TTL.

Backup / keys:
  --backup      TARGET     Tar each user's home (excluding shared ~/data) into backups/.
  --restore     TARGET     Restore a user's home from their latest backup
                           (or --restore-file PATH).
  --rotate-key  TARGET     Issue a NEW key pair and revoke the old one.

Expiry (opt-in):
  --ttl-days N             With create/add/format*: containers auto-expire after N days.
  --reap                   Remove containers whose TTL has passed.
  --install-reaper         Install a daily systemd timer (or cron) that runs --reap.
  --uninstall-reaper       Remove that timer/cron.

Networking (exposed-server hardening, best-effort iptables):
  --lockdown-lan           Block containers from reaching private LAN + cloud metadata.
  --unlock-lan             Remove those block rules.

Teardown:
  --prune                  Remove ALL managed containers + networks (typed confirm).

Modifiers:
  --purge-keys             With --remove/--prune: also delete SSH key pair(s).
  -y, --yes                Skip confirmation prompts.
  --dry-run                Print actions without changing anything.
  --config PATH            Use an alternate config.env.
  --total N | --mem V | --cpus V | --pids V | --disk V
  --image V | --ssh-user V | --base-dir V | --public-ip V
  --restore-file PATH      Explicit archive for --restore.
  -h, --help               This help.

Examples:
  sudo $0
  sudo $0 --add-users 2 --ttl-days 7
  sudo $0 --list
  sudo $0 --exec all -- sudo apt-get install -y nmap
  sudo $0 --remove 4,5 --purge-keys
  sudo $0 --format 1-3
  sudo $0 --backup all
  sudo $0 --install-reaper
EOF
}

#########################################################
# ARGUMENT PARSING
#########################################################

require_spec() {
    if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        err "$1 requires a target: all | N | A-B | 1,3,5"
        exit 1
    fi
}

require_num() {
    if [[ -z "${2:-}" || ! "${2:-}" =~ ^[0-9]+$ ]]; then
        err "$1 requires a non-negative integer."
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --add-users)     MODE="add"; require_num "$1" "${2:-}"; ADD_USERS="$2"; shift 2 ;;
            --list|--status) MODE="list"; shift ;;
            --info)          MODE="info";    require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --start)         MODE="start";   require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --stop)          MODE="stop";    require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --restart)       MODE="restart"; require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --logs)          MODE="logs";    require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --remove|--rm|--delete) MODE="remove"; require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --format)        MODE="format";  require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --backup)        MODE="backup";  require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --restore)       MODE="restore"; require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --rotate-key)    MODE="rotate";  require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
            --exec)
                MODE="exec"; require_spec "$1" "${2:-}"; SPEC="$2"; shift 2
                if [[ "${1:-}" != "--" ]]; then err "--exec TARGET -- <command>"; exit 1; fi
                shift; EXEC_CMD=( "$@" )
                if (( ${#EXEC_CMD[@]} == 0 )); then err "--exec needs a command after --"; exit 1; fi
                break ;;
            --format-image)  MODE="format-image"; shift ;;
            --rebuild-image) MODE="rebuild-image"; shift ;;
            --reap)          MODE="reap"; shift ;;
            --install-reaper)   MODE="install-reaper"; shift ;;
            --uninstall-reaper) MODE="uninstall-reaper"; shift ;;
            --lockdown-lan)  MODE="lockdown-lan"; shift ;;
            --unlock-lan)    MODE="unlock-lan"; shift ;;
            --prune)         MODE="prune"; shift ;;
            --ttl-days)      require_num "$1" "${2:-}"; TTL_DAYS="$2"; shift 2 ;;
            --purge-keys)    PURGE_KEYS=1; shift ;;
            -y|--yes)        ASSUME_YES=1; shift ;;
            --dry-run)       DRY_RUN=1; shift ;;
            --config)        OVER_CONFIG="${2:-}"; shift 2 ;;
            --total)         require_num "$1" "${2:-}"; OVER_TOTAL="$2"; shift 2 ;;
            --mem)           OVER_MEM="${2:-}"; shift 2 ;;
            --cpus)          OVER_CPUS="${2:-}"; shift 2 ;;
            --pids)          OVER_PIDS="${2:-}"; shift 2 ;;
            --disk)          OVER_DISK="${2:-}"; shift 2 ;;
            --image)         OVER_IMAGE="${2:-}"; shift 2 ;;
            --ssh-user)      OVER_SSH_USER="${2:-}"; shift 2 ;;
            --base-dir)      OVER_BASE_DIR="${2:-}"; shift 2 ;;
            --public-ip)     OVER_PUBLIC_IP="${2:-}"; shift 2 ;;
            --restore-file)  RESTORE_FILE="${2:-}"; shift 2 ;;
            -h|--help)       usage; exit 0 ;;
            *)               err "Unknown option: $1"; usage; exit 1 ;;
        esac
    done
}

load_config() {
    local cfg="${OVER_CONFIG:-$SCRIPT_DIR/config.env}"
    if [[ -n "$OVER_CONFIG" && ! -f "$OVER_CONFIG" ]]; then
        err "Config file not found: $OVER_CONFIG"; exit 1
    fi
    if [[ -f "$cfg" ]]; then
        # shellcheck disable=SC1090
        source "$cfg"
        log "Loaded config: $cfg"
    fi
    # CLI overrides win over config + defaults
    [[ -n "$OVER_TOTAL"     ]] && TOTAL_USERS="$OVER_TOTAL"
    [[ -n "$OVER_MEM"       ]] && MEM_LIMIT="$OVER_MEM"
    [[ -n "$OVER_CPUS"      ]] && CPU_LIMIT="$OVER_CPUS"
    [[ -n "$OVER_PIDS"      ]] && PIDS_LIMIT="$OVER_PIDS"
    [[ -n "$OVER_DISK"      ]] && DISK_LIMIT="$OVER_DISK"
    [[ -n "$OVER_IMAGE"     ]] && IMAGE_NAME="$OVER_IMAGE"
    [[ -n "$OVER_SSH_USER"  ]] && SSH_USER="$OVER_SSH_USER"
    [[ -n "$OVER_BASE_DIR"  ]] && BASE_DIR="$OVER_BASE_DIR"
    [[ -n "$OVER_PUBLIC_IP" ]] && PUBLIC_IP="$OVER_PUBLIC_IP"
    [[ -n "$TTL_DAYS"       ]] && DEFAULT_TTL_DAYS="$TTL_DAYS"
}

#########################################################
# HELPERS: safe mutation + confirmation
#########################################################

# Run a state-changing command, or just print it under --dry-run.
mutate() {
    if (( DRY_RUN )); then dbg "$*"; return 0; fi
    "$@"
}

confirm() {
    local prompt="$1"
    (( ASSUME_YES )) && return 0
    (( DRY_RUN ))    && return 0
    local ans=""
    read -r -p "$prompt [y/N] " ans || true
    [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# Typed confirmation for the most destructive actions.
confirm_typed() {
    local phrase="$1"
    (( ASSUME_YES )) && return 0
    (( DRY_RUN ))    && return 0
    local ans=""
    read -r -p "Type '$phrase' to proceed: " ans || true
    [[ "$ans" == "$phrase" ]]
}

#########################################################
# DISCOVERY
#########################################################

list_existing_user_numbers() {
    docker ps -a --filter "label=kali.managed=1" --format '{{.Names}}' 2>/dev/null \
        | grep -E "^${CONTAINER_PREFIX}_[0-9]+$" \
        | sed -E "s/^${CONTAINER_PREFIX}_([0-9]+)$/\1/" \
        | sort -n || true
}

get_existing_max_user_number() { list_existing_user_numbers | tail -n 1; }
get_existing_count()           { list_existing_user_numbers | grep -c . || true; }
container_exists()             { docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }

label_of() { docker inspect -f "{{ index .Config.Labels \"$2\" }}" "$1" 2>/dev/null || true; }

ports_of() {
    local num="$1"
    echo "$((SSH_PORT_START - num + 1)) $((SERVICE_PORT_START + num - 1))"
}

# Expand a TARGET spec into a sorted, unique list of numbers.
parse_spec_to_numbers() {
    local spec="$1"; local -a nums=()
    if [[ "$spec" == "all" ]]; then
        mapfile -t nums < <(list_existing_user_numbers)
    else
        local IFS=','; read -ra parts <<< "$spec"; local part
        for part in "${parts[@]}"; do
            if [[ "$part" =~ ^[0-9]+$ ]]; then
                nums+=("$part")
            elif [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                local a="${BASH_REMATCH[1]}" b="${BASH_REMATCH[2]}" i t
                if (( a > b )); then t="$a"; a="$b"; b="$t"; fi
                for ((i=a; i<=b; i++)); do nums+=("$i"); done
            else
                err "Invalid target part: '$part' (use all | N | A-B | 1,3,5)"; exit 1
            fi
        done
    fi
    (( ${#nums[@]} == 0 )) && return 0
    printf '%s\n' "${nums[@]}" | sort -n -u
}

SELECTED=()
resolve_spec() {
    mapfile -t SELECTED < <(parse_spec_to_numbers "$1")
    if (( ${#SELECTED[@]} == 0 )); then
        warn "No matching containers for target: $1"; exit 0
    fi
}

#########################################################
# PUBLIC IP
#########################################################

detect_public_ip() {
    if [[ -n "$PUBLIC_IP" ]]; then SERVER_IP="$PUBLIC_IP"; return; fi
    local ip="" url
    for url in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
        ip=$(curl -fsS --max-time 5 "$url" 2>/dev/null | tr -d '[:space:]' || true)
        if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then SERVER_IP="$ip"; return; fi
    done
    ip=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1 || true)
    [[ -n "$ip" ]] && SERVER_IP="$ip" || SERVER_IP="YOUR_SERVER_IP"
}

#########################################################
# TTL HELPERS
#########################################################

now_epoch() { date +%s; }

# Resolve the expiry epoch for a (re)created container.
#   $1 = user number, $2 = "preserve" to reuse an existing container's expiry
resolve_expiry_epoch() {
    local num="$1" preserve="${2:-}" old=""
    if [[ -n "$TTL_DAYS" && "$TTL_DAYS" -gt 0 ]]; then
        echo $(( $(now_epoch) + TTL_DAYS * 86400 )); return
    fi
    if [[ "$preserve" == "preserve" ]]; then
        old=$(label_of "${CONTAINER_PREFIX}_${num}" kali.expiry)
        if [[ "$old" =~ ^[0-9]+$ ]]; then echo "$old"; return; fi
    fi
    if (( DEFAULT_TTL_DAYS > 0 )); then
        echo $(( $(now_epoch) + DEFAULT_TTL_DAYS * 86400 )); return
    fi
    echo 0
}

human_expiry() {
    local epoch="$1" now days when
    if [[ ! "$epoch" =~ ^[0-9]+$ ]] || (( epoch == 0 )); then echo "never"; return; fi
    now="$(now_epoch)"
    if (( epoch <= now )); then echo "EXPIRED"; return; fi
    days=$(( (epoch - now) / 86400 ))
    when="$(date -d "@$epoch" '+%Y-%m-%d' 2>/dev/null || echo "$epoch")"
    if (( days == 0 )); then echo "<1d ($when)"; else echo "${days}d ($when)"; fi
}

#########################################################
# FIREWALL (host, per published port)
#########################################################

open_firewall_port() {
    local port="$1"
    if command -v ufw >/dev/null 2>&1 && ufw status | grep -qi active; then
        mutate ufw allow "${port}/tcp" >/dev/null; log "UFW allowed TCP $port"; return
    fi
    if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        mutate firewall-cmd --permanent --add-port="${port}/tcp" >/dev/null
        mutate firewall-cmd --reload >/dev/null; log "firewalld allowed TCP $port"; return
    fi
    if command -v iptables >/dev/null 2>&1; then
        if ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT >/dev/null 2>&1; then
            mutate iptables -I INPUT -p tcp --dport "$port" -j ACCEPT; log "iptables allowed TCP $port"
        fi
        return
    fi
    warn "No supported firewall manager found for TCP $port"
}

close_firewall_port() {
    local port="$1"
    if command -v ufw >/dev/null 2>&1 && ufw status | grep -qi active; then
        mutate ufw delete allow "${port}/tcp" >/dev/null 2>&1 || true; return
    fi
    if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        mutate firewall-cmd --permanent --remove-port="${port}/tcp" >/dev/null 2>&1 || true
        mutate firewall-cmd --reload >/dev/null 2>&1 || true; return
    fi
    if command -v iptables >/dev/null 2>&1; then
        mutate iptables -D INPUT -p tcp --dport "$port" -j ACCEPT >/dev/null 2>&1 || true; return
    fi
}

#########################################################
# LAN LOCKDOWN (best-effort, exposed-server hardening)
#########################################################

LOCKDOWN_CHAIN="DOCKER-USER"
PRIVATE_NETS=(10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.169.254/32)

lockdown_lan() {
    if ! command -v iptables >/dev/null 2>&1; then err "iptables not found."; exit 1; fi
    warn "Blocking container egress to: ${PRIVATE_NETS[*]}"
    warn "If your DNS resolver lives on a private IP, containers may lose name resolution."
    confirm "Apply LAN lockdown now?" || { warn "Aborted."; return; }
    # Let already-established flows return, then drop new traffic to private ranges.
    if ! iptables -C "$LOCKDOWN_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN >/dev/null 2>&1; then
        mutate iptables -I "$LOCKDOWN_CHAIN" 1 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
    fi
    local net
    for net in "${PRIVATE_NETS[@]}"; do
        if ! iptables -C "$LOCKDOWN_CHAIN" -d "$net" -j DROP >/dev/null 2>&1; then
            mutate iptables -A "$LOCKDOWN_CHAIN" -d "$net" -j DROP
        fi
    done
    log "LAN lockdown applied on chain $LOCKDOWN_CHAIN."
}

unlock_lan() {
    if ! command -v iptables >/dev/null 2>&1; then err "iptables not found."; exit 1; fi
    local net
    for net in "${PRIVATE_NETS[@]}"; do
        mutate iptables -D "$LOCKDOWN_CHAIN" -d "$net" -j DROP >/dev/null 2>&1 || true
    done
    mutate iptables -D "$LOCKDOWN_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN >/dev/null 2>&1 || true
    log "LAN lockdown rules removed."
}

#########################################################
# NETWORK
#########################################################

network_for() {
    if [[ "$NETWORK_MODE" == "shared" ]]; then echo "$NETWORK_NAME"; else echo "${NETWORK_NAME}_$1"; fi
}

ensure_network() {
    local net="$1"
    if ! docker network inspect "$net" >/dev/null 2>&1; then
        mutate docker network create --label kali.managed=1 "$net" >/dev/null
        log "Created network: $net"
    fi
}

remove_network_if_managed() {
    local net="$1"
    [[ "$NETWORK_MODE" == "shared" ]] && return   # keep the shared net around
    if docker network inspect "$net" >/dev/null 2>&1; then
        mutate docker network rm "$net" >/dev/null 2>&1 || true
    fi
}

#########################################################
# IMAGE
#########################################################

generate_dockerfile() {
    local dockerfile="$BASE_DIR/docker/Dockerfile"
    log "Writing Kali Dockerfile..."
    # apt is pinned to Kali's Cloudflare CDN (kali.download over HTTP) instead of
    # the http.kali.org redirector, which was bouncing packages to a mirror with
    # an invalid TLS cert ("certificate verify failed"). Retries absorb blips.
    cat > "$dockerfile" <<EOF
FROM kalilinux/kali-rolling

RUN set -eux; \\
    echo 'deb http://kali.download/kali kali-rolling main contrib non-free non-free-firmware' > /etc/apt/sources.list; \\
    echo 'Acquire::Retries "5";'          >  /etc/apt/apt.conf.d/99custom; \\
    echo 'Acquire::http::Timeout "60";'   >> /etc/apt/apt.conf.d/99custom; \\
    echo 'Acquire::https::Timeout "60";'  >> /etc/apt/apt.conf.d/99custom; \\
    apt-get update; \\
    DEBIAN_FRONTEND=noninteractive apt-get install -y \\
    openssh-server sudo ca-certificates curl nano vim net-tools iproute2 procps less bash-completion iputils-ping; \\
    apt-get clean; \\
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash $SSH_USER && \\
    usermod -aG sudo $SSH_USER && \\
    echo "$SSH_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$SSH_USER && \\
    chmod 0440 /etc/sudoers.d/$SSH_USER

RUN mkdir -p /var/run/sshd /home/$SSH_USER/.ssh && \\
    chmod 700 /home/$SSH_USER/.ssh && \\
    chown -R $SSH_USER:$SSH_USER /home/$SSH_USER/.ssh

RUN ssh-keygen -A && \\
    sed -i 's/^#\\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && \\
    sed -i 's/^#\\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config && \\
    sed -i 's/^#\\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \\
    sed -i 's/^#\\?X11Forwarding .*/X11Forwarding no/' /etc/ssh/sshd_config && \\
    printf '%s\\n' \\
      'AllowUsers $SSH_USER' \\
      'PermitEmptyPasswords no' \\
      'ChallengeResponseAuthentication no' \\
      'KbdInteractiveAuthentication no' \\
      'MaxAuthTries 3' \\
      'LoginGraceTime 20' \\
      'ClientAliveInterval 300' \\
      'ClientAliveCountMax 2' \\
      'AllowAgentForwarding no' \\
      'AllowTcpForwarding $ALLOW_TCP_FORWARDING' \\
      >> /etc/ssh/sshd_config

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD pidof sshd >/dev/null 2>&1 || exit 1

CMD ["/usr/sbin/sshd", "-D", "-e"]
EOF
}

build_image() {
    local nocache="${1:-}"
    generate_dockerfile
    if [[ -n "$nocache" ]]; then
        log "Building image (no cache): $IMAGE_NAME"
        mutate docker build --no-cache -t "$IMAGE_NAME" "$BASE_DIR/docker"
    else
        log "Building image: $IMAGE_NAME"
        mutate docker build -t "$IMAGE_NAME" "$BASE_DIR/docker"
    fi
}

ensure_image() {
    if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
        log "Image present: $IMAGE_NAME (use --rebuild-image to refresh)"
    else
        build_image
    fi
}

# Probe whether the storage driver can enforce a per-container disk cap.
check_disk_quota() {
    DISK_QUOTA_OK=0
    [[ -z "$DISK_LIMIT" ]] && return
    if (( DRY_RUN )); then DISK_QUOTA_OK=1; return; fi
    if docker run --rm --storage-opt "size=$DISK_LIMIT" "$IMAGE_NAME" true >/dev/null 2>&1; then
        DISK_QUOTA_OK=1
        log "Disk quota supported; enforcing size=$DISK_LIMIT per container."
    else
        if (( REQUIRE_DISK_QUOTA )); then
            err "Storage driver can't enforce size=$DISK_LIMIT (REQUIRE_DISK_QUOTA=1)."; exit 1
        fi
        warn "Storage driver can't enforce a per-container disk cap; continuing without it."
        warn "To enable: overlay2 on XFS with pquota, or btrfs/zfs. See docs. (REQUIRE_DISK_QUOTA=1 to hard-fail.)"
    fi
}

#########################################################
# ACCESS FILES
#########################################################

write_header() {
    cat > "$1" <<EOF
KALI CONTAINER ACCESS FILE
Generated at: $(date)
Server IP:    $SERVER_IP

Base directory:   $BASE_DIR
SSH user:         $SSH_USER   (passwordless sudo inside the container)
Per-container:    mem=$MEM_LIMIT cpus=${CPU_LIMIT:-unlimited} pids=${PIDS_LIMIT:-unlimited} disk=${DISK_LIMIT:-unlimited}
Network mode:     $NETWORK_MODE
TCP forwarding:   $ALLOW_TCP_FORWARDING

Shared data folder (all containers): $SHARED_DATA_DIR
Mounted at ~/data (host /data) with sticky-bit (1777): everyone reads/writes,
only the owner deletes their own files.

EOF
}

setup_access_files() {
    write_header "$RUN_ACCESS_FILE"
    write_header "$SUMMARY_FILE"
    if [[ ! -f "$ACCESS_FILE" ]]; then
        write_header "$ACCESS_FILE"
    else
        cat >> "$ACCESS_FILE" <<EOF


============================================================
NEW RUN: $(date)
============================================================

EOF
    fi
}

# Render the human-readable access block for a user (stdout).
render_user_block() {
    local num="$1" expiry="${2:-0}"
    local name="${CONTAINER_PREFIX}_${num}"
    local ssh_port service_port; read -r ssh_port service_port < <(ports_of "$num")
    local key="$BASE_DIR/keys/${name}_ed25519"
    cat <<EOF

============================================================
USER $num  ($name)
============================================================

SSH username:   $SSH_USER
SSH port:       $ssh_port
Service port:   $service_port
Private key:    $key
Expires:        $(human_expiry "$expiry")

SSH command:
ssh -i "$key" -p $ssh_port $SSH_USER@$SERVER_IP

SFTP command:
sftp -i "$key" -P $ssh_port $SSH_USER@$SERVER_IP

Privilege: passwordless sudo. Example:
  sudo apt update && sudo apt install -y nmap tmux git

Service exposure: bind inside the container to 0.0.0.0:$service_port
External access:  $SERVER_IP:$service_port
  python3 -m http.server $service_port --bind 0.0.0.0

Admin:
  docker exec -it $name bash
  docker logs $name
  docker restart $name
  docker rm -f $name

Shared data folder: ~/data (container) == /data (host), sticky-bit 1777.
  cp myfile.txt ~/data/     # share
  ls ~/data/                # see others' shared files

EOF
}

append_summary() {
    local num="$1" status="$2" expiry="${3:-0}"
    local name="${CONTAINER_PREFIX}_${num}"
    local ssh_port service_port; read -r ssh_port service_port < <(ports_of "$num")
    local key="$BASE_DIR/keys/${name}_ed25519"
    cat >> "$SUMMARY_FILE" <<EOF
$name
  Status:   $status
  SSH:      ssh -i "$key" -p $ssh_port $SSH_USER@$SERVER_IP
  Service:  $SERVER_IP:$service_port
  Key:      $key
  Expires:  $(human_expiry "$expiry")

EOF
}

#########################################################
# CONTAINER CREATION
#########################################################

# create_user_container NUM [EXPIRY_EPOCH]
create_user_container() {
    local num="$1" expiry="${2:-0}"
    local name="${CONTAINER_PREFIX}_${num}"
    local ssh_port service_port; read -r ssh_port service_port < <(ports_of "$num")
    local key="$BASE_DIR/keys/${name}_ed25519"
    local net; net="$(network_for "$num")"

    log "Processing $name  (ssh:$ssh_port svc:$service_port mem:$MEM_LIMIT cpus:${CPU_LIMIT:-∞} ttl:$(human_expiry "$expiry"))"

    open_firewall_port "$ssh_port"
    open_firewall_port "$service_port"

    if container_exists "$name"; then
        warn "Exists, not modified: $name"
        append_summary "$num" "already exists, not modified" "$(label_of "$name" kali.expiry)"
        return
    fi

    if (( DRY_RUN )); then
        dbg "would create $name on $net (key: $key)"
        return
    fi

    if [[ ! -f "$key" ]]; then
        ssh-keygen -t ed25519 -f "$key" -N "" -C "$name" >/dev/null
        chmod 600 "$key"
        log "Generated key: $key"
    else
        warn "Reusing existing key: $key"
    fi

    ensure_network "$net"

    local now; now="$(now_epoch)"
    local -a run_args=(
        -d --name "$name" --hostname "$name" --restart unless-stopped
        --network "$net"
        --memory "$MEM_LIMIT" --memory-swap "$MEM_LIMIT"
        --label kali.managed=1 --label "kali.user=$num" --label "kali.created=$now"
    )
    [[ -n "$CPU_LIMIT"  ]] && run_args+=( --cpus "$CPU_LIMIT" )
    [[ -n "$PIDS_LIMIT" ]] && run_args+=( --pids-limit "$PIDS_LIMIT" )
    [[ -n "$DISK_LIMIT" ]] && (( DISK_QUOTA_OK )) && run_args+=( --storage-opt "size=$DISK_LIMIT" )
    (( expiry > 0 )) && run_args+=( --label "kali.expiry=$expiry" )
    run_args+=(
        -p "${ssh_port}:22"
        -p "${service_port}:${service_port}"
        -v "${SHARED_DATA_DIR}:/home/$SSH_USER/data"
        "$IMAGE_NAME"
    )

    docker run "${run_args[@]}" >/dev/null

    docker cp "${key}.pub" "$name:/home/$SSH_USER/.ssh/authorized_keys"
    docker exec "$name" chown -R "$SSH_USER:$SSH_USER" "/home/$SSH_USER/.ssh"
    docker exec "$name" chmod 700 "/home/$SSH_USER/.ssh"
    docker exec "$name" chmod 600 "/home/$SSH_USER/.ssh/authorized_keys"
    docker exec "$name" chmod 1777 "/home/$SSH_USER/data"

    local block; block="$(render_user_block "$num" "$expiry")"
    echo "$block" >> "$ACCESS_FILE"
    echo "$block" >> "$RUN_ACCESS_FILE"
    append_summary "$num" "created" "$expiry"
}

#########################################################
# LIFECYCLE
#########################################################

list_containers() {
    local -a nums; mapfile -t nums < <(list_existing_user_numbers)
    if (( ${#nums[@]} == 0 )); then warn "No managed containers found."; return; fi

    # One stats snapshot for all containers.
    declare -A CPU MEMS
    if ! (( DRY_RUN )); then
        local line n c m
        while IFS=$'\t' read -r n c m; do CPU["$n"]="$c"; MEMS["$n"]="$m"; done \
            < <(docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null || true)
    fi

    printf '%-9s %-8s %-8s %-9s %-9s %-8s %-6s %-14s %s\n' \
        CONTAINER SSH SVC STATE HEALTH CPU KEY EXPIRES MEM
    printf '%-9s %-8s %-8s %-9s %-9s %-8s %-6s %-14s %s\n' \
        --------- --- --- ----- ------ --- --- ------- ---
    local num name state health ssh_port service_port key keystat exp cpu mem
    for num in "${nums[@]}"; do
        name="${CONTAINER_PREFIX}_${num}"
        read -r ssh_port service_port < <(ports_of "$num")
        state=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo unknown)
        health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$name" 2>/dev/null || echo -)
        key="$BASE_DIR/keys/${name}_ed25519"; keystat=missing; [[ -f "$key" ]] && keystat=present
        exp=$(human_expiry "$(label_of "$name" kali.expiry)")
        cpu="${CPU[$name]:--}"; mem="${MEMS[$name]:--}"
        printf '%-9s %-8s %-8s %-9s %-9s %-8s %-6s %-14s %s\n' \
            "$name" "$ssh_port" "$service_port" "$state" "$health" "$cpu" "$keystat" "$exp" "$mem"
    done
}

info_containers() {
    local num
    for num in "$@"; do
        local name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            render_user_block "$num" "$(label_of "$name" kali.expiry)"
        else
            warn "No such container: $name"
        fi
    done
}

_simple_op() {  # $1 = docker verb, $2.. = numbers
    local verb="$1"; shift
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            mutate docker "$verb" "$name" >/dev/null && log "${verb^}ed: $name"
        else
            warn "No such container: $name"
        fi
    done
}
start_containers()   { _simple_op start   "$@"; }
stop_containers()    { _simple_op stop    "$@"; }
restart_containers() { _simple_op restart "$@"; }

logs_containers() {
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            echo "==================== $name ===================="
            docker logs --tail 40 "$name" 2>&1 || true
        else
            warn "No such container: $name"
        fi
    done
}

exec_containers() {
    local num name rc
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if ! container_exists "$name"; then warn "No such container: $name"; continue; fi
        echo "==================== $name ===================="
        if (( DRY_RUN )); then dbg "docker exec $name ${EXEC_CMD[*]}"; continue; fi
        rc=0
        docker exec "$name" bash -lc "$(printf '%q ' "${EXEC_CMD[@]}")" || rc=$?
        (( rc != 0 )) && warn "$name: command exited $rc"
    done
}

remove_containers() {
    local num name ssh_port service_port key net
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if ! container_exists "$name"; then warn "No such container: $name"; continue; fi
        net="$(network_for "$num")"
        mutate docker rm -f "$name" >/dev/null && log "Removed: $name"
        read -r ssh_port service_port < <(ports_of "$num")
        close_firewall_port "$ssh_port"; close_firewall_port "$service_port"
        remove_network_if_managed "$net"
        key="$BASE_DIR/keys/${name}_ed25519"
        if (( PURGE_KEYS )); then
            mutate rm -f "$key" "${key}.pub"; warn "Purged key pair for $name"
        else
            log "Kept key for $name (use --purge-keys to delete)"
        fi
    done
}

format_containers() {
    local num name expiry
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        expiry="$(resolve_expiry_epoch "$num" preserve)"
        if container_exists "$name"; then
            log "Formatting $name (fresh container; same key, ports, remaining TTL)"
            mutate docker rm -f "$name" >/dev/null
        else
            warn "$name doesn't exist yet; creating it"
        fi
        create_user_container "$num" "$expiry"
    done
}

format_image() {
    local -a nums; mapfile -t nums < <(list_existing_user_numbers)
    build_image --no-cache
    check_disk_quota
    if (( ${#nums[@]} == 0 )); then warn "No containers to recreate; image rebuilt only."; return; fi
    log "Recreating ${#nums[@]} container(s) on the fresh image (keys, ports, TTL kept)"
    local num expiry
    for num in "${nums[@]}"; do
        expiry="$(resolve_expiry_epoch "$num" preserve)"
        mutate docker rm -f "${CONTAINER_PREFIX}_${num}" >/dev/null 2>&1 || true
        create_user_container "$num" "$expiry"
    done
}

#########################################################
# BACKUP / RESTORE / KEY ROTATION
#########################################################

BACKUP_DIR_NAME="backups"

backup_containers() {
    local num name file ts bdir="$BASE_DIR/$BACKUP_DIR_NAME"
    mkdir -p "$bdir"
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if ! container_exists "$name"; then warn "No such container: $name"; continue; fi
        ts="$(date +%Y%m%d_%H%M%S)"
        file="$bdir/${name}_${ts}.tar.gz"
        if (( DRY_RUN )); then dbg "would back up $name home -> $file"; continue; fi
        # Exclude the shared bind mount from the per-user backup.
        if docker exec "$name" tar czf - -C "/home/$SSH_USER" --exclude=./data . > "$file" 2>/dev/null; then
            log "Backed up $name -> $file"
        else
            err "Backup failed for $name"; rm -f "$file"
        fi
    done
}

restore_containers() {
    local num name file bdir="$BASE_DIR/$BACKUP_DIR_NAME"
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if ! container_exists "$name"; then warn "No such container: $name"; continue; fi
        if [[ -n "$RESTORE_FILE" ]]; then
            file="$RESTORE_FILE"
        else
            file=$(ls -1t "$bdir/${name}_"*.tar.gz 2>/dev/null | head -n1 || true)
        fi
        if [[ -z "$file" || ! -f "$file" ]]; then warn "No backup found for $name"; continue; fi
        confirm "Restore $name home from $(basename "$file")? This overwrites current files." || { warn "Skipped $name"; continue; }
        if (( DRY_RUN )); then dbg "would restore $file into $name"; continue; fi
        docker exec -i "$name" tar xzf - -C "/home/$SSH_USER" < "$file"
        docker exec "$name" chown -R "$SSH_USER:$SSH_USER" "/home/$SSH_USER"
        log "Restored $name from $(basename "$file")"
    done
}

rotate_key() {
    local num name key ts archive
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if ! container_exists "$name"; then warn "No such container: $name"; continue; fi
        key="$BASE_DIR/keys/${name}_ed25519"
        confirm "Rotate key for $name? The current key stops working immediately." || { warn "Skipped $name"; continue; }
        if (( DRY_RUN )); then dbg "would rotate key for $name"; continue; fi
        if [[ -f "$key" ]]; then
            ts="$(date +%Y%m%d_%H%M%S)"; archive="$BASE_DIR/keys/archive"; mkdir -p "$archive"
            mv "$key" "$archive/${name}_ed25519.$ts"
            mv "${key}.pub" "$archive/${name}_ed25519.pub.$ts" 2>/dev/null || true
            warn "Archived old key -> $archive/${name}_ed25519.$ts"
        fi
        ssh-keygen -t ed25519 -f "$key" -N "" -C "$name" >/dev/null; chmod 600 "$key"
        docker cp "${key}.pub" "$name:/home/$SSH_USER/.ssh/authorized_keys"
        docker exec "$name" chown "$SSH_USER:$SSH_USER" "/home/$SSH_USER/.ssh/authorized_keys"
        docker exec "$name" chmod 600 "/home/$SSH_USER/.ssh/authorized_keys"
        local ssh_port service_port; read -r ssh_port service_port < <(ports_of "$num")
        log "New key for $name: $key"
        echo "  ssh -i \"$key\" -p $ssh_port $SSH_USER@$SERVER_IP"
    done
}

#########################################################
# REAP + REAPER INSTALL
#########################################################

reap() {
    local -a nums due=(); mapfile -t nums < <(list_existing_user_numbers)
    local num name exp now; now="$(now_epoch)"
    for num in "${nums[@]}"; do
        name="${CONTAINER_PREFIX}_${num}"
        exp="$(label_of "$name" kali.expiry)"
        [[ "$exp" =~ ^[0-9]+$ ]] && (( exp > 0 && exp <= now )) && due+=("$num")
    done
    if (( ${#due[@]} == 0 )); then log "Nothing to reap."; return; fi
    warn "Expired containers: ${due[*]/#/${CONTAINER_PREFIX}_}"
    confirm "Remove ${#due[@]} expired container(s)?" || { warn "Aborted."; return; }
    remove_containers "${due[@]}"
}

REAPER_UNIT="kali-container-reaper"

install_reaper() {
    local cfg_flag=""
    [[ -n "$OVER_CONFIG" ]] && cfg_flag="--config $OVER_CONFIG"
    if command -v systemctl >/dev/null 2>&1; then
        mutate bash -c "cat > /etc/systemd/system/${REAPER_UNIT}.service" <<EOF
[Unit]
Description=Reap expired Kali containers
[Service]
Type=oneshot
ExecStart=$SCRIPT_PATH --reap --yes $cfg_flag
EOF
        mutate bash -c "cat > /etc/systemd/system/${REAPER_UNIT}.timer" <<EOF
[Unit]
Description=Daily reap of expired Kali containers
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
EOF
        mutate systemctl daemon-reload
        mutate systemctl enable --now "${REAPER_UNIT}.timer"
        log "Installed systemd timer ${REAPER_UNIT}.timer (daily)."
    else
        mutate bash -c "cat > /etc/cron.d/${REAPER_UNIT}" <<EOF
# Daily reap of expired Kali containers
17 3 * * * root $SCRIPT_PATH --reap --yes $cfg_flag >/var/log/${REAPER_UNIT}.log 2>&1
EOF
        log "Installed cron job /etc/cron.d/${REAPER_UNIT} (daily 03:17)."
    fi
}

uninstall_reaper() {
    if command -v systemctl >/dev/null 2>&1; then
        mutate systemctl disable --now "${REAPER_UNIT}.timer" >/dev/null 2>&1 || true
        mutate rm -f "/etc/systemd/system/${REAPER_UNIT}.service" "/etc/systemd/system/${REAPER_UNIT}.timer"
        mutate systemctl daemon-reload
    fi
    mutate rm -f "/etc/cron.d/${REAPER_UNIT}"
    log "Reaper uninstalled."
}

#########################################################
# PRUNE (full teardown of managed objects)
#########################################################

prune_all() {
    local -a nums; mapfile -t nums < <(list_existing_user_numbers)
    warn "This removes ALL ${#nums[@]} managed container(s) and their managed networks."
    (( PURGE_KEYS )) && warn "--purge-keys set: SSH keys will also be deleted."
    confirm_typed "prune" || { warn "Aborted."; return; }
    (( ${#nums[@]} > 0 )) && remove_containers "${nums[@]}"
    # Remove any leftover managed networks.
    local net
    while read -r net; do
        [[ -n "$net" ]] && mutate docker network rm "$net" >/dev/null 2>&1 || true
    done < <(docker network ls --filter "label=kali.managed=1" --format '{{.Name}}' 2>/dev/null || true)
    log "Prune complete."
}

#########################################################
# PROVISIONING
#########################################################

provision_range() {
    local start="$1" end="$2"
    if (( end > 1000 )); then err "Refusing user numbers > 1000."; exit 1; fi
    if (( SERVICE_PORT_START + end - 1 > 65535 )); then err "Service port overflow."; exit 1; fi
    if (( SSH_PORT_START - end + 1 < 1024 )); then err "SSH ports would enter privileged range."; exit 1; fi

    ensure_image
    check_disk_quota
    setup_access_files

    local num expiry
    for ((num=start; num<=end; num++)); do
        expiry="$(resolve_expiry_epoch "$num")"
        create_user_container "$num" "$expiry"
    done
}

print_footer() {
    log "Done."
    echo; echo "Master access file: $ACCESS_FILE"
    echo "This run:           $RUN_ACCESS_FILE"
    echo "Summary:            $SUMMARY_FILE"; echo
    cat "$SUMMARY_FILE"
}

#########################################################
# MAIN
#########################################################

main() {
    parse_args "$@"
    load_config

    if [[ $EUID -ne 0 ]]; then err "Run as root: sudo $0"; exit 1; fi
    if ! command -v docker >/dev/null 2>&1; then err "Docker is not installed."; exit 1; fi

    # Derived paths (after config/overrides settle BASE_DIR)
    mkdir -p "$BASE_DIR/keys" "$BASE_DIR/docker" "$BASE_DIR/runs" "$BASE_DIR/data"
    SHARED_DATA_DIR="$BASE_DIR/data"
    chmod 1777 "$SHARED_DATA_DIR"
    ACCESS_FILE="$BASE_DIR/access.txt"
    RUN_ACCESS_FILE="$BASE_DIR/runs/access_$(date +%Y%m%d_%H%M%S).txt"
    SUMMARY_FILE="$BASE_DIR/summary.txt"

    (( DRY_RUN )) && warn "DRY-RUN: no changes will be made."
    detect_public_ip
    log "Server IP: $SERVER_IP"

    case "$MODE" in
        default)
            (( TOTAL_USERS < 1 )) && { err "TOTAL_USERS must be >= 1."; exit 1; }
            log "Ensuring users 1..$TOTAL_USERS exist"
            provision_range 1 "$TOTAL_USERS"; print_footer ;;

        add)
            (( ADD_USERS < 1 )) && { err "--add-users needs N >= 1."; exit 1; }
            local emax; emax="$(get_existing_max_user_number)"; [[ -z "$emax" ]] && emax=0
            log "Highest existing user: $emax; adding $ADD_USERS"
            provision_range $((emax + 1)) $((emax + ADD_USERS)); print_footer ;;

        list)            list_containers ;;
        info)            resolve_spec "$SPEC"; info_containers   "${SELECTED[@]}" ;;
        start)           resolve_spec "$SPEC"; start_containers  "${SELECTED[@]}" ;;
        stop)            resolve_spec "$SPEC"; stop_containers   "${SELECTED[@]}" ;;
        restart)         resolve_spec "$SPEC"; restart_containers "${SELECTED[@]}" ;;
        logs)            resolve_spec "$SPEC"; logs_containers   "${SELECTED[@]}" ;;
        exec)            resolve_spec "$SPEC"; exec_containers   "${SELECTED[@]}" ;;

        remove)
            resolve_spec "$SPEC"
            confirm "Remove: ${SELECTED[*]/#/${CONTAINER_PREFIX}_} ?" || { warn "Aborted."; exit 0; }
            remove_containers "${SELECTED[@]}" ;;

        format)
            ensure_image; check_disk_quota; setup_access_files
            resolve_spec "$SPEC"
            confirm "Format (wipe + recreate): ${SELECTED[*]/#/${CONTAINER_PREFIX}_} ?" || { warn "Aborted."; exit 0; }
            format_containers "${SELECTED[@]}"; print_footer ;;

        format-image)
            confirm "Rebuild image and recreate ALL containers?" || { warn "Aborted."; exit 0; }
            setup_access_files; format_image; print_footer ;;

        rebuild-image)
            build_image --no-cache
            log "Image rebuilt. Existing containers keep the old image until formatted."
            log "Run: sudo $0 --format-image   (or --format TARGET)" ;;

        backup)          resolve_spec "$SPEC"; backup_containers  "${SELECTED[@]}" ;;
        restore)         resolve_spec "$SPEC"; restore_containers "${SELECTED[@]}" ;;
        rotate)          resolve_spec "$SPEC"; rotate_key         "${SELECTED[@]}" ;;

        reap)            reap ;;
        install-reaper)  install_reaper ;;
        uninstall-reaper) uninstall_reaper ;;
        lockdown-lan)    lockdown_lan ;;
        unlock-lan)      unlock_lan ;;
        prune)           prune_all ;;

        *) err "Unhandled mode: $MODE"; exit 1 ;;
    esac
}

if [[ "${KALI_LIB_ONLY:-0}" != "1" ]]; then
    main "$@"
fi
