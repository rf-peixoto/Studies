#!/usr/bin/env bash
set -euo pipefail

echo "[!] This will delete ALL Docker containers, images, volumes, networks and cache."
read -rp "Type DELETE-DOCKER to continue: " confirm

if [[ "$confirm" != "DELETE-DOCKER" ]]; then
  echo "Aborted."
  exit 1
fi

echo "[*] Stopping running containers..."
docker ps -q | xargs -r docker stop

echo "[*] Removing all containers..."
docker ps -aq | xargs -r docker rm -f

echo "[*] Removing all images..."
docker images -aq | xargs -r docker rmi -f

echo "[*] Removing all volumes..."
docker volume ls -q | xargs -r docker volume rm -f

echo "[*] Removing custom networks..."
docker network ls --format '{{.Name}}' \
  | grep -vE '^(bridge|host|none)$' \
  | xargs -r docker network rm

echo "[*] Pruning Docker system..."
docker system prune -a --volumes -f

echo "[*] Pruning BuildKit/build cache..."
docker builder prune -a -f || true

echo "[*] Stopping Docker services..."
sudo systemctl stop docker.socket docker.service containerd.service 2>/dev/null || true

echo "[*] Removing Docker sockets..."
sudo rm -f /var/run/docker.sock /run/docker.sock
sudo rm -f /var/run/docker.pid /run/docker.pid

echo "[*] Optional deep cleanup of Docker data directories..."
read -rp "Delete Docker data dirs too? /var/lib/docker and /var/lib/containerd [y/N]: " deep

if [[ "$deep" =~ ^[Yy]$ ]]; then
  sudo rm -rf /var/lib/docker /var/lib/containerd
fi

echo "[+] Docker cleanup complete."