#!/usr/bin/env bash
set -euo pipefail

PASSES="${PASSES:-2}"          # each pass = random + zeros
FS_TYPE="${FS_TYPE:-exfat}"    # exfat or ext4
LABEL="${LABEL:-WIPED}"
BS="${BS:-16M}"

need_root() {
  [[ "$EUID" -eq 0 ]] || { echo "Run as root: sudo $0"; exit 1; }
}

need_cmds() {
  for c in lsblk awk grep sed dd sync wipefs parted mkfs.exfat mkfs.ext4 blockdev udevadm; do
    command -v "$c" >/dev/null 2>&1 || true
  done
}

list_external_drives() {
  echo
  echo "Detected removable / external-looking drives:"
  echo

  lsblk -dpno NAME,SIZE,MODEL,TRAN,RM,HOTPLUG,TYPE |
    awk '$7=="disk" && ($4=="usb" || $5=="1" || $6=="1") {
      printf "  %-12s %-10s %-25s TRAN=%s RM=%s HOTPLUG=%s\n", $1,$2,$3,$4,$5,$6
    }'

  echo
}

is_external_drive() {
  local dev="$1"

  [[ -b "$dev" ]] || return 1

  local type tran rm hotplug
  type="$(lsblk -dnpo TYPE "$dev")"
  tran="$(lsblk -dnpo TRAN "$dev" | tr -d ' ')"
  rm="$(lsblk -dnpo RM "$dev" | tr -d ' ')"
  hotplug="$(lsblk -dnpo HOTPLUG "$dev" | tr -d ' ')"

  [[ "$type" == "disk" ]] || return 1
  [[ "$tran" == "usb" || "$rm" == "1" || "$hotplug" == "1" ]]
}

unmount_drive() {
  local dev="$1"

  echo "[*] Unmounting mounted partitions on $dev..."
  while read -r part mountpoint; do
    [[ -n "${mountpoint:-}" ]] && umount -f "$part" || true
  done < <(lsblk -lnpo NAME,MOUNTPOINT "$dev" | tail -n +2)
}

wipe_signatures() {
  local dev="$1"

  echo "[*] Removing filesystem/RAID/partition signatures..."
  wipefs -a "$dev" || true

  echo "[*] Destroying first and last metadata areas..."
  dd if=/dev/zero of="$dev" bs=1M count=64 conv=fsync status=progress || true

  local size
  size="$(blockdev --getsz "$dev")"
  if (( size > 262144 )); then
    dd if=/dev/zero of="$dev" bs=512 seek=$((size - 131072)) count=131072 conv=fsync status=progress || true
  fi

  sync
}

discard_if_supported() {
  local dev="$1"

  echo "[*] Trying blkdiscard/TRIM if supported..."
  if blkdiscard -f "$dev" 2>/dev/null; then
    echo "[+] blkdiscard succeeded."
  else
    echo "[!] blkdiscard not supported or refused by device. Continuing."
  fi
}

random_overwrite() {
  local dev="$1"

  echo "[*] Random overwrite on $dev..."
  openssl enc -aes-256-ctr \
    -pass pass:"$(openssl rand -hex 32)" \
    -nosalt \
    </dev/zero |
    dd of="$dev" bs="$BS" status=progress conv=fsync || true

  sync
}

zero_overwrite() {
  local dev="$1"

  echo "[*] Zero overwrite on $dev..."
  dd if=/dev/zero of="$dev" bs="$BS" status=progress conv=fsync || true
  sync
}

recreate_partition() {
  local dev="$1"

  echo "[*] Recreating GPT partition table..."
  parted -s "$dev" mklabel gpt
  parted -s "$dev" mkpart primary 1MiB 100%
  partprobe "$dev" || true
  udevadm settle

  local part
  part="$(lsblk -lnpo NAME "$dev" | sed -n '2p')"

  if [[ -z "$part" || ! -b "$part" ]]; then
    echo "[!] Could not detect new partition."
    exit 1
  fi

  echo "[*] Formatting $part as $FS_TYPE..."

  case "$FS_TYPE" in
    exfat)
      mkfs.exfat -n "$LABEL" "$part"
      ;;
    ext4)
      mkfs.ext4 -F -L "$LABEL" "$part"
      ;;
    *)
      echo "[!] Unsupported FS_TYPE: $FS_TYPE"
      exit 1
      ;;
  esac

  sync
  echo "[+] Done. Device wiped and reformatted: $dev"
}

main() {
  need_root
  need_cmds

  list_external_drives

  read -rp "Target device, for example /dev/sdb: " DEV

  if ! is_external_drive "$DEV"; then
    echo "[!] Refusing: $DEV does not look like a removable/external disk."
    exit 1
  fi

  echo
  echo "DANGER: this will permanently destroy all data on:"
  lsblk "$DEV"
  echo

  read -rp "Type exactly: WIPE $DEV : " CONFIRM
  [[ "$CONFIRM" == "WIPE $DEV" ]] || { echo "Aborted."; exit 1; }

  unmount_drive "$DEV"
  wipe_signatures "$DEV"
  discard_if_supported "$DEV"

  for i in $(seq 1 "$PASSES"); do
    echo
    echo "========== PASS $i / $PASSES =========="
    random_overwrite "$DEV"
    zero_overwrite "$DEV"
    wipe_signatures "$DEV"
  done

  recreate_partition "$DEV"
}

main "$@"
