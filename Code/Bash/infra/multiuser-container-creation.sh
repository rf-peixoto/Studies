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

log()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[-]\033[0m $*"; }

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo $0"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    err "Docker is not installed."
    exit 1
fi

if (( TOTAL_USERS < 1 )); then
    err "TOTAL_USERS must be at least 1."
    exit 1
fi

if (( TOTAL_USERS > 1000 )); then
    err "Refusing to create more than 1000 containers."
    exit 1
fi

if (( SERVICE_PORT_START + TOTAL_USERS - 1 > 65535 )); then
    err "Service port range overflow."
    exit 1
fi

if (( SSH_PORT_START - TOTAL_USERS + 1 < 1024 )); then
    err "SSH port range would enter privileged ports."
    exit 1
fi

SSH_PORTS=()
SERVICE_PORTS=()

for ((i=0; i<TOTAL_USERS; i++)); do
    SSH_PORTS+=($((SSH_PORT_START - i)))
    SERVICE_PORTS+=($((SERVICE_PORT_START + i)))
done

mkdir -p "$BASE_DIR/keys" "$BASE_DIR/docker"

ACCESS_FILE="$BASE_DIR/access.txt"
SUMMARY_FILE="$BASE_DIR/summary.txt"
DOCKERFILE="$BASE_DIR/docker/Dockerfile"

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

log "Opening firewall ports..."

for port in "${SSH_PORTS[@]}" "${SERVICE_PORTS[@]}"; do
    open_firewall_port "$port"
done

cat > "$ACCESS_FILE" <<EOF
KALI CONTAINER ACCESS FILE
Generated at: $(date)

Total users:
$TOTAL_USERS

Base directory:
$BASE_DIR

Container SSH user:
$SSH_USER

Privilege level:
Passwordless sudo inside each container.

Memory limit per container:
$MEM_LIMIT

EOF

cat > "$SUMMARY_FILE" <<EOF
CONTAINER SUMMARY
Generated at: $(date)

EOF

log "Creating containers..."

for ((i=0; i<TOTAL_USERS; i++)); do
    NUM=$((i + 1))
    NAME="${CONTAINER_PREFIX}_${NUM}"
    SSH_PORT="${SSH_PORTS[$i]}"
    SERVICE_PORT="${SERVICE_PORTS[$i]}"
    KEY="$BASE_DIR/keys/${NAME}_ed25519"

    log "Configuring $NAME"
    echo "    SSH port:     $SSH_PORT"
    echo "    Service port: $SERVICE_PORT"
    echo "    Memory limit: $MEM_LIMIT"
    echo "    Sudo:         passwordless"

    if [[ ! -f "$KEY" ]]; then
        ssh-keygen -t ed25519 -f "$KEY" -N "" -C "$NAME" >/dev/null
        chmod 600 "$KEY"
        log "Generated private key: $KEY"
    else
        warn "Key already exists, reusing: $KEY"
    fi

    if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
        warn "Removing old container: $NAME"
        docker rm -f "$NAME" >/dev/null
    fi

    docker run -d \
        --name "$NAME" \
        --restart unless-stopped \
        --memory "$MEM_LIMIT" \
        --memory-swap "$MEM_LIMIT" \
        -p "${SSH_PORT}:22" \
        -p "${SERVICE_PORT}:${SERVICE_PORT}" \
        "$IMAGE_NAME" >/dev/null

    docker cp "${KEY}.pub" "$NAME:/home/$SSH_USER/.ssh/authorized_keys"
    docker exec "$NAME" chown -R "$SSH_USER:$SSH_USER" "/home/$SSH_USER/.ssh"
    docker exec "$NAME" chmod 700 "/home/$SSH_USER/.ssh"
    docker exec "$NAME" chmod 600 "/home/$SSH_USER/.ssh/authorized_keys"

    cat >> "$ACCESS_FILE" <<EOF

============================================================
USER $NUM
============================================================

Container:
$NAME

SSH username:
$SSH_USER

SSH port:
$SSH_PORT

Service port:
$SERVICE_PORT

Private key:
$KEY

SSH command:
ssh -i "$KEY" -p $SSH_PORT $SSH_USER@YOUR_SERVER_IP

SFTP command:
sftp -i "$KEY" -P $SSH_PORT $SSH_USER@YOUR_SERVER_IP

Privilege inside container:
The user can run sudo without a password.

Example:
sudo apt update
sudo apt install -y nmap tmux git

Service exposure:
Inside the container, bind the service to:

0.0.0.0:$SERVICE_PORT

External access will be:

YOUR_SERVER_IP:$SERVICE_PORT

Example inside the container:
python3 -m http.server $SERVICE_PORT --bind 0.0.0.0

Useful admin commands:

docker exec -it $NAME bash
docker logs $NAME
docker restart $NAME
docker stop $NAME
docker rm -f $NAME

EOF

    cat >> "$SUMMARY_FILE" <<EOF
$NAME
  SSH:      ssh -i "$KEY" -p $SSH_PORT $SSH_USER@YOUR_SERVER_IP
  SFTP:     sftp -i "$KEY" -P $SSH_PORT $SSH_USER@YOUR_SERVER_IP
  Service:  YOUR_SERVER_IP:$SERVICE_PORT
  Key:      $KEY
  Sudo:     enabled, passwordless

EOF
done

log "Provisioning complete."
echo
echo "Access file:"
echo "$ACCESS_FILE"
echo
echo "Summary file:"
echo "$SUMMARY_FILE"
echo
cat "$SUMMARY_FILE"
