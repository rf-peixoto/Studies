#!/usr/bin/env bash
set -euo pipefail

#########################################################
# CONFIGURATION
#########################################################

TOTAL_USERS=5

BASE_DIR="$PWD/kali_container_vps"
IMAGE_NAME="multiuser-kali-ssh:latest"
CONTAINER_PREFIX="user"
SSH_USER="user"
MEM_LIMIT="8g"

SSH_PORT_START=65535
SERVICE_PORT_START=20001

#########################################################

MODE="default"
ADD_USERS=0
SPEC=""
PURGE_KEYS=0

log()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[-]\033[0m $*"; }

usage() {
    cat <<EOF
Usage: sudo $0 [command]

Provisioning:
  (no command)            Create containers 1..TOTAL_USERS ($TOTAL_USERS). Existing ones untouched.
  --add-users N           Add N new users after the highest existing user number.

Lifecycle (TARGET = all | N | A-B | 1,3,5):
  --list, --status        Show every managed container with ports, state and key status.
  --start   TARGET        Start stopped container(s).
  --stop    TARGET        Stop running container(s).
  --restart TARGET        Restart container(s).
  --remove  TARGET        Delete container(s). Keys are KEPT unless --purge-keys is given.
     [--purge-keys]       When used with --remove, also delete the SSH key pair(s).
  --format  TARGET        Recreate container(s) from scratch, REUSING the same SSH key and ports.

Image:
  --rebuild-image         Rebuild the base image with --no-cache (containers untouched).
  --format-image          Rebuild the base image fresh AND recreate every existing container,
                          each keeping its credentials (SSH key) and ports.

Other:
  -h, --help              Show this help.

Examples:
  sudo $0
  sudo $0 --add-users 2
  sudo $0 --list
  sudo $0 --stop all
  sudo $0 --restart 3
  sudo $0 --remove 4,5
  sudo $0 --remove 2 --purge-keys
  sudo $0 --format 1-3
  sudo $0 --format-image
EOF
}

#########################################################
# ARGUMENT PARSING
#########################################################

require_spec() {
    # $1 = flag name, $2 = candidate value
    if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        err "$1 requires a target: all | N | A-B | 1,3,5"
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --add-users)
            MODE="add"
            if [[ -z "${2:-}" || ! "${2:-}" =~ ^[0-9]+$ ]]; then
                err "--add-users requires a positive number."
                exit 1
            fi
            ADD_USERS="$2"
            shift 2
            ;;
        --list|--status)
            MODE="list"
            shift
            ;;
        --start)
            MODE="start";   require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
        --stop)
            MODE="stop";    require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
        --restart)
            MODE="restart"; require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
        --remove|--rm|--delete)
            MODE="remove";  require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
        --format)
            MODE="format";  require_spec "$1" "${2:-}"; SPEC="$2"; shift 2 ;;
        --format-image)
            MODE="format-image"; shift ;;
        --rebuild-image)
            MODE="rebuild-image"; shift ;;
        --purge-keys)
            PURGE_KEYS=1; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

#########################################################
# PRE-FLIGHT CHECKS
#########################################################

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo $0"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed."
    exit 1
fi

mkdir -p "$BASE_DIR/keys" "$BASE_DIR/docker" "$BASE_DIR/runs" "$BASE_DIR/data"

SHARED_DATA_DIR="$BASE_DIR/data"
# Ensure the shared directory is world-readable/writable so every container
# user can read and write files regardless of the host UID mapping.
chmod 1777 "$SHARED_DATA_DIR"

ACCESS_FILE="$BASE_DIR/access.txt"
RUN_ACCESS_FILE="$BASE_DIR/runs/access_$(date +%Y%m%d_%H%M%S).txt"
SUMMARY_FILE="$BASE_DIR/summary.txt"
DOCKERFILE="$BASE_DIR/docker/Dockerfile"

#########################################################
# CONTAINER DISCOVERY / SPEC RESOLUTION
#########################################################

list_existing_user_numbers() {
    docker ps -a --format '{{.Names}}' 2>/dev/null \
        | grep -E "^${CONTAINER_PREFIX}_[0-9]+$" \
        | sed -E "s/^${CONTAINER_PREFIX}_([0-9]+)$/\1/" \
        | sort -n || true
}

get_existing_max_user_number() {
    list_existing_user_numbers | tail -n 1
}

get_existing_count() {
    list_existing_user_numbers | grep -c . || true
}

container_exists() {
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$1"
}

# Expand a TARGET spec (all | N | A-B | 1,3,5) into a sorted, unique list of numbers.
parse_spec_to_numbers() {
    local spec="$1"
    local -a nums=()

    if [[ "$spec" == "all" ]]; then
        mapfile -t nums < <(list_existing_user_numbers)
    else
        local IFS=','
        read -ra parts <<< "$spec"
        local part
        for part in "${parts[@]}"; do
            if [[ "$part" =~ ^[0-9]+$ ]]; then
                nums+=("$part")
            elif [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                local a="${BASH_REMATCH[1]}" b="${BASH_REMATCH[2]}" i t
                if (( a > b )); then t="$a"; a="$b"; b="$t"; fi
                for ((i=a; i<=b; i++)); do nums+=("$i"); done
            else
                err "Invalid target part: '$part' (use all | N | A-B | 1,3,5)"
                exit 1
            fi
        done
    fi

    if (( ${#nums[@]} == 0 )); then
        return 0
    fi
    printf '%s\n' "${nums[@]}" | sort -n -u
}

# Populates the global SELECTED array from a spec, or exits if nothing matches.
SELECTED=()
resolve_spec() {
    mapfile -t SELECTED < <(parse_spec_to_numbers "$1")
    if (( ${#SELECTED[@]} == 0 )); then
        warn "No matching containers for target: $1"
        exit 0
    fi
}

#########################################################
# FIREWALL
#########################################################

open_firewall_port() {
    local port="$1"

    if command -v ufw >/dev/null 2>&1 && ufw status | grep -qi active; then
        ufw allow "${port}/tcp" >/dev/null
        log "UFW allowed TCP port $port"
        return
    fi

    if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        firewall-cmd --permanent --add-port="${port}/tcp" >/dev/null
        firewall-cmd --reload >/dev/null
        log "firewalld allowed TCP port $port"
        return
    fi

    if command -v iptables >/dev/null 2>&1; then
        if ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT >/dev/null 2>&1; then
            iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
            log "iptables allowed TCP port $port"
        fi
        return
    fi

    warn "No supported firewall manager found for TCP port $port"
}

close_firewall_port() {
    local port="$1"

    if command -v ufw >/dev/null 2>&1 && ufw status | grep -qi active; then
        ufw delete allow "${port}/tcp" >/dev/null 2>&1 || true
        log "UFW removed rule for TCP port $port"
        return
    fi

    if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        firewall-cmd --permanent --remove-port="${port}/tcp" >/dev/null 2>&1 || true
        firewall-cmd --reload >/dev/null 2>&1 || true
        log "firewalld removed rule for TCP port $port"
        return
    fi

    if command -v iptables >/dev/null 2>&1; then
        iptables -D INPUT -p tcp --dport "$port" -j ACCEPT >/dev/null 2>&1 || true
        return
    fi
}

#########################################################
# IMAGE
#########################################################

generate_dockerfile() {
    log "Writing Kali Dockerfile..."

    # NOTE: the base 'apt-get install' is pinned to Kali's Cloudflare CDN
    # (kali.download over HTTP) instead of the http.kali.org redirector.
    # The redirector was bouncing some packages to a community mirror whose
    # HTTPS certificate is invalid, which made apt abort with
    # "certificate verify failed". Retries + timeouts absorb transient errors.
    cat > "$DOCKERFILE" <<EOF
FROM kalilinux/kali-rolling

RUN set -eux; \\
    echo 'deb http://kali.download/kali kali-rolling main contrib non-free non-free-firmware' > /etc/apt/sources.list; \\
    echo 'Acquire::Retries "5";'          >  /etc/apt/apt.conf.d/99custom; \\
    echo 'Acquire::http::Timeout "60";'   >> /etc/apt/apt.conf.d/99custom; \\
    echo 'Acquire::https::Timeout "60";'  >> /etc/apt/apt.conf.d/99custom; \\
    apt-get update; \\
    DEBIAN_FRONTEND=noninteractive apt-get install -y \\
    openssh-server sudo ca-certificates curl nano vim net-tools iproute2 procps less bash-completion; \\
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
    echo "AllowUsers $SSH_USER" >> /etc/ssh/sshd_config

CMD ["/usr/sbin/sshd", "-D", "-e"]
EOF
}

build_image() {
    local nocache="${1:-}"
    generate_dockerfile
    if [[ -n "$nocache" ]]; then
        log "Building Docker image (no cache): $IMAGE_NAME"
        docker build --no-cache -t "$IMAGE_NAME" "$BASE_DIR/docker"
    else
        log "Building Docker image: $IMAGE_NAME"
        docker build -t "$IMAGE_NAME" "$BASE_DIR/docker"
    fi
}

ensure_image() {
    if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
        log "Image already present: $IMAGE_NAME (use --rebuild-image to refresh)"
    else
        build_image
    fi
}

#########################################################
# ACCESS FILES
#########################################################

write_header() {
    local file="$1"

    cat > "$file" <<EOF
KALI CONTAINER ACCESS FILE
Generated at: $(date)

Base directory:
$BASE_DIR

Container SSH user:
$SSH_USER

Privilege level:
Passwordless sudo inside each container.

Memory limit per container:
$MEM_LIMIT

Shared data folder (all containers):
$SHARED_DATA_DIR
Mounted inside each container at ~/data with sticky-bit permissions (1777).
All users can read and write; only the file owner can delete their own files.

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

#########################################################
# CONTAINER CREATION
#########################################################

create_user_container() {
    local num="$1"

    local name="${CONTAINER_PREFIX}_${num}"
    local ssh_port=$((SSH_PORT_START - num + 1))
    local service_port=$((SERVICE_PORT_START + num - 1))
    local key="$BASE_DIR/keys/${name}_ed25519"

    log "Processing $name"
    echo "    SSH port:     $ssh_port"
    echo "    Service port: $service_port"
    echo "    Memory limit: $MEM_LIMIT"
    echo "    Sudo:         passwordless"

    open_firewall_port "$ssh_port"
    open_firewall_port "$service_port"

    if container_exists "$name"; then
        warn "Container already exists, skipping without modification: $name"

        cat >> "$SUMMARY_FILE" <<EOF
$name
  Status:   already exists, not modified
  SSH:      ssh -i "$key" -p $ssh_port $SSH_USER@YOUR_SERVER_IP
  SFTP:     sftp -i "$key" -P $ssh_port $SSH_USER@YOUR_SERVER_IP
  Service:  YOUR_SERVER_IP:$service_port
  Key:      $key

EOF
        return
    fi

    if [[ ! -f "$key" ]]; then
        ssh-keygen -t ed25519 -f "$key" -N "" -C "$name" >/dev/null
        chmod 600 "$key"
        log "Generated private key: $key"
    else
        warn "Key already exists, reusing: $key"
    fi

    docker run -d \
        --name "$name" \
        --restart unless-stopped \
        --memory "$MEM_LIMIT" \
        --memory-swap "$MEM_LIMIT" \
        -p "${ssh_port}:22" \
        -p "${service_port}:${service_port}" \
        -v "${SHARED_DATA_DIR}:/home/$SSH_USER/data" \
        "$IMAGE_NAME" >/dev/null

    docker cp "${key}.pub" "$name:/home/$SSH_USER/.ssh/authorized_keys"
    docker exec "$name" chown -R "$SSH_USER:$SSH_USER" "/home/$SSH_USER/.ssh"
    docker exec "$name" chmod 700 "/home/$SSH_USER/.ssh"
    docker exec "$name" chmod 600 "/home/$SSH_USER/.ssh/authorized_keys"
    # Shared data directory: sticky bit lets all users read/write while
    # preventing deletion of each other's files (same semantics as /tmp).
    docker exec "$name" chmod 1777 "/home/$SSH_USER/data"

    local block
    block=$(cat <<EOF

============================================================
USER $num
============================================================

Container:
$name

SSH username:
$SSH_USER

SSH port:
$ssh_port

Service port:
$service_port

Private key:
$key

SSH command:
ssh -i "$key" -p $ssh_port $SSH_USER@YOUR_SERVER_IP

SFTP command:
sftp -i "$key" -P $ssh_port $SSH_USER@YOUR_SERVER_IP

Privilege inside container:
The user can run sudo without a password.

Example:
sudo apt update
sudo apt install -y nmap tmux git

Service exposure:
Inside the container, bind the service to:

0.0.0.0:$service_port

External access will be:

YOUR_SERVER_IP:$service_port

Example inside the container:
python3 -m http.server $service_port --bind 0.0.0.0

Useful admin commands:

docker exec -it $name bash
docker logs $name
docker restart $name
docker stop $name
docker rm -f $name

Shared data folder:
All containers share the same host directory mounted at:

  ~/data  (inside the container)
  /data  (on the host)

Files placed here are immediately visible to every other container.
The directory uses sticky-bit permissions (1777) so any user can
read and write, but only the owner can delete their own files.

Example:
  cp myfile.txt ~/data/        # share a file
  ls ~/data/                   # see what others shared

EOF
)

    echo "$block" >> "$ACCESS_FILE"
    echo "$block" >> "$RUN_ACCESS_FILE"

    cat >> "$SUMMARY_FILE" <<EOF
$name
  Status:   created
  SSH:      ssh -i "$key" -p $ssh_port $SSH_USER@YOUR_SERVER_IP
  SFTP:     sftp -i "$key" -P $ssh_port $SSH_USER@YOUR_SERVER_IP
  Service:  YOUR_SERVER_IP:$service_port
  Key:      $key
  Sudo:     enabled, passwordless
  Shared:   ~/data  (host: /data)

EOF
}

#########################################################
# LIFECYCLE OPERATIONS
#########################################################

list_containers() {
    local -a nums
    mapfile -t nums < <(list_existing_user_numbers)

    if (( ${#nums[@]} == 0 )); then
        warn "No managed containers found."
        return
    fi

    printf '%-10s %-9s %-9s %-12s %-8s\n' "CONTAINER" "SSHPORT" "SVCPORT" "STATE" "KEY"
    printf '%-10s %-9s %-9s %-12s %-8s\n' "---------" "-------" "-------" "-----" "---"
    local num name state ssh_port service_port key keystat
    for num in "${nums[@]}"; do
        name="${CONTAINER_PREFIX}_${num}"
        state=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo "unknown")
        ssh_port=$((SSH_PORT_START - num + 1))
        service_port=$((SERVICE_PORT_START + num - 1))
        key="$BASE_DIR/keys/${name}_ed25519"
        keystat="missing"
        [[ -f "$key" ]] && keystat="present"
        printf '%-10s %-9s %-9s %-12s %-8s\n' "$name" "$ssh_port" "$service_port" "$state" "$keystat"
    done
}

stop_containers() {
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            docker stop "$name" >/dev/null && log "Stopped: $name"
        else
            warn "No such container: $name"
        fi
    done
}

start_containers() {
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            docker start "$name" >/dev/null && log "Started: $name"
        else
            warn "No such container: $name"
        fi
    done
}

restart_containers() {
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            docker restart "$name" >/dev/null && log "Restarted: $name"
        else
            warn "No such container: $name"
        fi
    done
}

remove_containers() {
    local num name ssh_port service_port key
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            docker rm -f "$name" >/dev/null && log "Removed container: $name"

            ssh_port=$((SSH_PORT_START - num + 1))
            service_port=$((SERVICE_PORT_START + num - 1))
            close_firewall_port "$ssh_port"
            close_firewall_port "$service_port"

            key="$BASE_DIR/keys/${name}_ed25519"
            if (( PURGE_KEYS == 1 )); then
                rm -f "$key" "${key}.pub"
                warn "Purged SSH key pair for $name"
            else
                log "Kept SSH key for $name (re-run with --purge-keys to delete it)"
            fi
        else
            warn "No such container: $name"
        fi
    done
}

# "Format": recreate the container(s) from a clean image layer while REUSING
# the existing on-disk SSH key and the deterministic ports. The user's
# credentials and connection details stay identical.
format_containers() {
    local num name
    for num in "$@"; do
        name="${CONTAINER_PREFIX}_${num}"
        if container_exists "$name"; then
            log "Formatting $name (fresh container, same key and ports)"
            docker rm -f "$name" >/dev/null
        else
            warn "$name does not exist yet; creating it"
        fi
        create_user_container "$num"
    done
}

# "Format the image": rebuild the base image from scratch, then rebuild every
# existing container on top of it. Keys and ports are preserved.
format_image() {
    local -a nums
    mapfile -t nums < <(list_existing_user_numbers)

    build_image --no-cache

    if (( ${#nums[@]} == 0 )); then
        warn "No existing containers to recreate; image rebuilt only."
        return
    fi

    log "Recreating ${#nums[@]} container(s) on the fresh image, keeping keys and ports"
    local num
    for num in "${nums[@]}"; do
        docker rm -f "${CONTAINER_PREFIX}_${num}" >/dev/null 2>&1 || true
        create_user_container "$num"
    done
}

#########################################################
# PROVISIONING (default / add)
#########################################################

provision_range() {
    local start="$1" end="$2"

    if (( end > 1000 )); then
        err "Refusing to create user numbers higher than 1000."
        exit 1
    fi
    if (( SERVICE_PORT_START + end - 1 > 65535 )); then
        err "Service port range overflow."
        exit 1
    fi
    if (( SSH_PORT_START - end + 1 < 1024 )); then
        err "SSH port range would enter privileged ports."
        exit 1
    fi

    ensure_image
    setup_access_files

    local num
    for ((num=start; num<=end; num++)); do
        create_user_container "$num"
    done
}

#########################################################
# DISPATCH
#########################################################

case "$MODE" in
    default)
        if (( TOTAL_USERS < 1 )); then
            err "TOTAL_USERS must be at least 1."
            exit 1
        fi
        log "Default mode: ensuring users 1 to $TOTAL_USERS exist"
        provision_range 1 "$TOTAL_USERS"
        ;;

    add)
        EXISTING_MAX="$(get_existing_max_user_number || true)"
        EXISTING_COUNT="$(get_existing_count || true)"
        [[ -z "$EXISTING_MAX" ]] && EXISTING_MAX=0
        [[ -z "$EXISTING_COUNT" ]] && EXISTING_COUNT=0

        START_USER=$((EXISTING_MAX + 1))
        END_USER=$((EXISTING_MAX + ADD_USERS))

        log "Existing containers detected: $EXISTING_COUNT"
        log "Highest existing user number: $EXISTING_MAX"
        log "Adding users from $START_USER to $END_USER"
        provision_range "$START_USER" "$END_USER"
        ;;

    list)
        list_containers
        exit 0
        ;;

    start)
        resolve_spec "$SPEC"
        start_containers "${SELECTED[@]}"
        exit 0
        ;;

    stop)
        resolve_spec "$SPEC"
        stop_containers "${SELECTED[@]}"
        exit 0
        ;;

    restart)
        resolve_spec "$SPEC"
        restart_containers "${SELECTED[@]}"
        exit 0
        ;;

    remove)
        resolve_spec "$SPEC"
        remove_containers "${SELECTED[@]}"
        exit 0
        ;;

    format)
        ensure_image
        setup_access_files
        resolve_spec "$SPEC"
        format_containers "${SELECTED[@]}"
        ;;

    format-image)
        setup_access_files
        format_image
        ;;

    rebuild-image)
        build_image --no-cache
        log "Image rebuilt. Existing containers still run the old image until formatted."
        log "Run: sudo $0 --format-image   (or --format TARGET) to roll them onto the new image."
        exit 0
        ;;

    *)
        err "Unhandled mode: $MODE"
        exit 1
        ;;
esac

log "Provisioning complete."
echo
echo "Master access file:"
echo "$ACCESS_FILE"
echo
echo "This run access file:"
echo "$RUN_ACCESS_FILE"
echo
echo "Summary file:"
echo "$SUMMARY_FILE"
echo
cat "$SUMMARY_FILE"
