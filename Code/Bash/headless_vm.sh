#!/usr/bin/env bash
set -Eeuo pipefail

# =========================
# Config
# =========================
VM_NAME="${VM_NAME:-debian-headless}"
VM_DIR="${VM_DIR:-$HOME/vm/$VM_NAME}"
ISO_URL="${ISO_URL:-https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.4.0-amd64-netinst.iso}"
ISO_PATH="${ISO_PATH:-$VM_DIR/debian-netinst.iso}"
DISK_PATH="${DISK_PATH:-$VM_DIR/${VM_NAME}.qcow2}"
DISK_SIZE="${DISK_SIZE:-20G}"
RAM_MB="${RAM_MB:-2048}"
VCPUS="${VCPUS:-2}"
OS_VARIANT="${OS_VARIANT:-debian13}"
NETWORK_NAME="${NETWORK_NAME:-default}"
AUTO_ATTACH_CONSOLE="${AUTO_ATTACH_CONSOLE:-yes}"   # yes|no
RECREATE="${RECREATE:-no}"                          # yes|no

# =========================
# Colors
# =========================
if [[ -t 1 ]]; then
  C_RESET="\033[0m"
  C_BOLD="\033[1m"
  C_DIM="\033[2m"
  C_RED="\033[31m"
  C_GREEN="\033[32m"
  C_YELLOW="\033[33m"
  C_BLUE="\033[34m"
  C_MAGENTA="\033[35m"
  C_CYAN="\033[36m"
else
  C_RESET=""
  C_BOLD=""
  C_DIM=""
  C_RED=""
  C_GREEN=""
  C_YELLOW=""
  C_BLUE=""
  C_MAGENTA=""
  C_CYAN=""
fi

# =========================
# Helpers
# =========================
info()    { printf "%b[INFO]%b %s\n"    "$C_CYAN"   "$C_RESET" "$*"; }
ok()      { printf "%b[ OK ]%b %s\n"    "$C_GREEN"  "$C_RESET" "$*"; }
warn()    { printf "%b[WARN]%b %s\n"    "$C_YELLOW" "$C_RESET" "$*"; }
error()   { printf "%b[ERR ]%b %s\n"    "$C_RED"    "$C_RESET" "$*" >&2; }
step()    { printf "\n%b==>%b %s\n"     "$C_BOLD"   "$C_RESET" "$*"; }
substep() { printf "%b  ->%b %s\n"      "$C_BLUE"   "$C_RESET" "$*"; }

die() {
  error "$*"
  exit 1
}

cleanup_on_error() {
  error "Script failed at line $1."
  warn "Review the messages above."
}
trap 'cleanup_on_error $LINENO' ERR

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing dependency: $1"
}

run_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

vm_exists() {
  run_sudo virsh dominfo "$VM_NAME" >/dev/null 2>&1
}

network_exists() {
  run_sudo virsh net-info "$NETWORK_NAME" >/dev/null 2>&1
}

network_active() {
  run_sudo virsh net-info "$NETWORK_NAME" 2>/dev/null | grep -q '^Active:.*yes'
}

vm_running() {
  run_sudo virsh domstate "$VM_NAME" 2>/dev/null | grep -qi running
}

print_summary() {
  printf "\n%b%s%b\n" "$C_BOLD" "Configuration summary" "$C_RESET"
  printf "  %-18s %s\n" "VM name:"       "$VM_NAME"
  printf "  %-18s %s\n" "VM dir:"        "$VM_DIR"
  printf "  %-18s %s\n" "ISO URL:"       "$ISO_URL"
  printf "  %-18s %s\n" "ISO path:"      "$ISO_PATH"
  printf "  %-18s %s\n" "Disk path:"     "$DISK_PATH"
  printf "  %-18s %s\n" "Disk size:"     "$DISK_SIZE"
  printf "  %-18s %s\n" "RAM:"           "${RAM_MB} MB"
  printf "  %-18s %s\n" "vCPUs:"         "$VCPUS"
  printf "  %-18s %s\n" "OS variant:"    "$OS_VARIANT"
  printf "  %-18s %s\n" "Libvirt net:"   "$NETWORK_NAME"
  printf "  %-18s %s\n" "Auto console:"  "$AUTO_ATTACH_CONSOLE"
  printf "  %-18s %s\n" "Recreate VM:"   "$RECREATE"
}

# =========================
# Pre-flight
# =========================
step "Checking dependencies"
for cmd in wget qemu-img virt-install virsh; do
  need_cmd "$cmd"
done
ok "All required commands are present"

step "Preparing workspace"
mkdir -p "$VM_DIR"
ok "Workspace ready at $VM_DIR"

print_summary

# =========================
# Libvirt network
# =========================
step "Checking libvirt network"
if ! network_exists; then
  die "Libvirt network '$NETWORK_NAME' does not exist. Create it first or change NETWORK_NAME."
fi

if ! network_active; then
  substep "Starting libvirt network '$NETWORK_NAME'"
  run_sudo virsh net-start "$NETWORK_NAME" >/dev/null
fi

substep "Marking '$NETWORK_NAME' for autostart"
run_sudo virsh net-autostart "$NETWORK_NAME" >/dev/null || true
ok "Libvirt network is ready"

# =========================
# ISO
# =========================
step "Ensuring Debian ISO is available"
if [[ -f "$ISO_PATH" ]]; then
  ok "ISO already exists: $ISO_PATH"
else
  substep "Downloading ISO"
  wget --show-progress -O "$ISO_PATH" "$ISO_URL"
  ok "Downloaded ISO to $ISO_PATH"
fi

# =========================
# Disk
# =========================
step "Preparing VM disk"
if [[ -f "$DISK_PATH" ]]; then
  warn "Disk already exists: $DISK_PATH"
else
  substep "Creating qcow2 disk"
  qemu-img create -f qcow2 "$DISK_PATH" "$DISK_SIZE" >/dev/null
  ok "Disk created: $DISK_PATH"
fi

# =========================
# Existing VM handling
# =========================
step "Checking existing VM definition"
if vm_exists; then
  warn "A VM named '$VM_NAME' already exists."

  if [[ "$RECREATE" == "yes" ]]; then
    substep "Destroying running VM if necessary"
    run_sudo virsh destroy "$VM_NAME" >/dev/null 2>&1 || true

    substep "Undefining existing VM"
    run_sudo virsh undefine "$VM_NAME" >/dev/null

    ok "Old VM definition removed"
  else
    warn "RECREATE=no, so the existing VM will be reused."
  fi
fi

# =========================
# Create VM
# =========================
if ! vm_exists; then
  step "Creating the VM in headless mode"

  # Debian installer over serial console.
  # The extra args are important here.
  # Some environments may reject --extra-args with --cdrom. If that happens,
  # use the QEMU fallback shown after this script.
  run_sudo virt-install \
    --name "$VM_NAME" \
    --memory "$RAM_MB" \
    --vcpus "$VCPUS" \
    --cpu host \
    --disk "path=$DISK_PATH,format=qcow2,bus=virtio" \
    --cdrom "$ISO_PATH" \
    --os-variant "$OS_VARIANT" \
    --network "network=$NETWORK_NAME,model=virtio" \
    --graphics none \
    --console pty,target_type=serial \
    --serial pty \
    --boot hd,cdrom,menu=on,useserial=on \
    --noautoconsole \
    --extra-args "console=ttyS0,115200n8 serial"

  ok "VM created successfully"
else
  step "VM definition already exists"
  ok "Skipping VM creation"
fi

# =========================
# Start VM if needed
# =========================
step "Ensuring VM is running"
if vm_running; then
  ok "VM is already running"
else
  substep "Starting VM"
  run_sudo virsh start "$VM_NAME" >/dev/null
  ok "VM started"
fi

# =========================
# Post actions
# =========================
step "Useful commands"
printf "%b%s%b\n" "$C_MAGENTA" "Attach to console:" "$C_RESET"
printf "  sudo virsh console %s\n\n" "$VM_NAME"

printf "%b%s%b\n" "$C_MAGENTA" "Escape from console without shutting down the VM:" "$C_RESET"
printf "  Ctrl + ]\n\n"

printf "%b%s%b\n" "$C_MAGENTA" "Get guest IP later:" "$C_RESET"
printf "  sudo virsh domifaddr %s\n\n" "$VM_NAME"

printf "%b%s%b\n" "$C_MAGENTA" "Shutdown the VM:" "$C_RESET"
printf "  sudo virsh shutdown %s\n\n" "$VM_NAME"

printf "%b%s%b\n" "$C_MAGENTA" "Force power off:" "$C_RESET"
printf "  sudo virsh destroy %s\n\n" "$VM_NAME"

printf "%b%s%b\n" "$C_MAGENTA" "Remove only VM definition:" "$C_RESET"
printf "  sudo virsh undefine %s\n\n" "$VM_NAME"

printf "%b%s%b\n" "$C_MAGENTA" "Remove disk file too:" "$C_RESET"
printf "  rm -f %q\n" "$DISK_PATH"

# =========================
# Auto attach
# =========================
if [[ "$AUTO_ATTACH_CONSOLE" == "yes" ]]; then
  step "Attaching to VM console"
  warn "To leave the console, press Ctrl + ]"
  exec sudo virsh console "$VM_NAME"
else
  ok "Done. Auto attach disabled."
fi
