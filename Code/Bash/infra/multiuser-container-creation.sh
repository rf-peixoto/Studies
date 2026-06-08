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

log()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[-]\033[0m $*"; }

usage() {
    cat <<EOF
Usage:

  sudo $0
      Create containers from 1 to TOTAL_USERS.
      Existing containers are not modified.

  sudo $0 --add-users N
      Add N new users after the highest existing user number.

Examples:

  sudo $0
  sudo $0 --add-users 2

EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --add-users)
            MODE="add"
            ADD_USERS="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo $0"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed."
    exit 1
fi

if [[ "$MODE" == "add" ]]; then
    if ! [[ "$ADD_USERS" =~ ^[0-9]+$ ]] || (( ADD_USERS < 1 )); then
        err "--add-users requires a positive number."
        exit 1
    fi
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

get_existing_max_user_number() {
    docker ps -a --format '{{.Names}}' \
        | grep -E "^${CONTAINER_PREFIX}_[0-9]+$" \
        | sed -E "s/^${CONTAINER_PREFIX}_([0-9]+)$/\1/" \
        | sort -n \
        | tail -n 1
}

get_existing_count() {
    docker ps -a --format '{{.Names}}' \
        | grep -E "^${CONTAINER_PREFIX}_[0-9]+$" \
        | wc -l
}

if [[ "$MODE" == "add" ]]; then
    EXISTING_MAX="$(get_existing_max_user_number || true)"
    EXISTING_COUNT="$(get_existing_count || true)"

    if [[ -z "$EXISTING_MAX" ]]; then
        EXISTING_MAX=0
    fi

    START_USER=$((EXISTING_MAX + 1))
    END_USER=$((EXISTING_MAX + ADD_USERS))

    log "Existing containers detected: $EXISTING_COUNT"
    log "Highest existing user number: $EXISTING_MAX"
    log "Adding users from $START_USER to $END_USER"
else
    if (( TOTAL_USERS < 1 )); then
        err "TOTAL_USERS must be at least 1."
        exit 1
    fi

    START_USER=1
    END_USER="$TOTAL_USERS"

    log "Default mode: ensuring users 1 to $TOTAL_USERS exist"
fi

if (( END_USER > 1000 )); then
    err "Refusing to create user numbers higher than 1000."
    exit 1
fi

if (( SERVICE_PORT_START + END_USER - 1 > 65535 )); then
    err "Service port range overflow."
    exit 1
fi

if (( SSH_PORT_START - END_USER + 1 < 1024 )); then
    err "SSH port range would enter privileged ports."
    exit 1
fi

log "Creating Kali Dockerfile..."

cat > "$DOCKERFILE" <<EOF
FROM kalilinux/kali-rolling

RUN apt-get update && \\
    DEBIAN_FRONTEND=noninteractive apt-get install -y \\
    openssh-server sudo ca-certificates curl nano vim net-tools iproute2 procps less bash-completion && \\
    apt-get clean && \\
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

log "Building Docker image: $IMAGE_NAME"
docker build -t "$IMAGE_NAME" "$BASE_DIR/docker"

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

    if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
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

for ((num=START_USER; num<=END_USER; num++)); do
    create_user_container "$num"
done

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
