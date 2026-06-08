#!/bin/bash

set -e

echo "[+] Stopping Docker services..."
systemctl stop docker.service 2>/dev/null || true
systemctl stop docker.socket 2>/dev/null || true
systemctl stop containerd.service 2>/dev/null || true

echo "[+] Disabling Docker services..."
systemctl disable docker.service 2>/dev/null || true
systemctl disable docker.socket 2>/dev/null || true
systemctl disable containerd.service 2>/dev/null || true

echo "[+] Killing remaining Docker processes..."
pkill -9 dockerd 2>/dev/null || true
pkill -9 containerd 2>/dev/null || true
pkill -9 containerd-shim 2>/dev/null || true
pkill -9 runc 2>/dev/null || true

echo "[+] Removing Docker containers, images, volumes, networks and metadata..."
rm -rf /var/lib/docker
rm -rf /var/lib/containerd

echo "[+] Removing Docker runtime files..."
rm -rf /run/docker
rm -rf /run/containerd

echo "[+] Removing Docker logs..."
rm -rf /var/log/docker*

echo "[+] Docker cleanup complete."

echo
echo "Remaining Docker-related processes:"
ps aux | grep -E 'docker|containerd|runc' | grep -v grep || true
