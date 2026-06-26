#!/usr/bin/env bash
#
# secure_wipe.sh — sanitize removable/external drives with verification.
#
# Strategy (aligned with NIST SP 800-88 Rev.1):
#   1. Try a real hardware SANITIZE first (the only thing that can reach
#      hidden/over-provisioned flash cells): BLKSECDISCARD, NVMe sanitize,
#      or ATA Secure Erase. Best-effort — many USB bridges block these.
#   2. Fall back to a single full-device overwrite (random then zero).
#   3. VERIFY by reading the whole device back and confirming it is all zero.
#      Correctness comes from this read-back, NOT from dd's exit status.
#   4. Recreate a fresh partition + filesystem.
#
# IMPORTANT LIMITATION: on flash media (USB sticks, SSDs) a software
# overwrite cannot guarantee erasure of remapped / over-provisioned /
# retired cells. Chip-off forensics may still recover data from those.
# For truly sensitive data on flash, rely on a successful hardware
# sanitize, on crypto-erase (drive encrypted from first use), or on
# physical destruction. See the summary the script prints at the end.

set -euo pipefail

# ---- configuration (override via environment) -------------------------------
PASSES="${PASSES:-1}"            # NIST: 1 pass is enough for addressable area
FS_TYPE="${FS_TYPE:-exfat}"      # exfat or ext4
LABEL="${LABEL:-WIPED}"
BS="${BS:-16M}"
VERIFY="${VERIFY:-full}"         # full | sample | none
TRY_HW_ERASE="${TRY_HW_ERASE:-1}"     # try blkdiscard/nvme sanitize
TRY_ATA_ERASE="${TRY_ATA_ERASE:-0}"   # ATA Secure Erase via hdparm (can lock a
                                      # drive if it fails mid-way; opt-in only)

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'
info()  { echo "${GRN}[*]${RST} $*"; }
warn()  { echo "${YEL}[!]${RST} $*"; }
err()   { echo "${RED}[x]${RST} $*" >&2; }

# ---- preflight --------------------------------------------------------------
need_root() {
  [[ "$EUID" -eq 0 ]] || { err "Run as root: sudo $0"; exit 1; }
}

check_cmds() {
  # Hard requirements — abort if missing.
  local required=(lsblk awk dd sync wipefs parted partprobe blockdev udevadm)
  local missing=()
  local c
  for c in "${required[@]}"; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  command -v "mkfs.$FS_TYPE" >/dev/null 2>&1 || missing+=("mkfs.$FS_TYPE")
  if ((${#missing[@]})); then
    err "Missing required commands: ${missing[*]}"
    err "Install them (e.g. util-linux, parted, exfatprogs/e2fsprogs) and retry."
    exit 1
  fi
  # Optional — note absence but continue.
  for c in blkdiscard nvme hdparm openssl; do
    command -v "$c" >/dev/null 2>&1 || warn "optional tool '$c' not found (some features disabled)"
  done
}

list_external_drives() {
  echo
  info "Detected removable / external-looking drives:"
  echo
  lsblk -dpno NAME,SIZE,MODEL,TRAN,RM,HOTPLUG,ROTA,TYPE |
    awk '$8=="disk" && ($4=="usb" || $5=="1" || $6=="1") {
      printf "  %-12s %-9s %-22s TRAN=%-4s RM=%s HOTPLUG=%s ROTA=%s\n",
             $1,$2,$3,$4,$5,$6,$7
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

is_rotational() {
  local base; base="$(basename "$1")"
  [[ "$(cat "/sys/block/$base/queue/rotational" 2>/dev/null || echo 1)" == "1" ]]
}

# ---- steps ------------------------------------------------------------------
unmount_drive() {
  local dev="$1"
  info "Unmounting any mounted partitions on $dev..."
  local part mnt
  while read -r part mnt; do
    [[ -n "${mnt:-}" ]] && { umount -f "$part" 2>/dev/null || warn "could not unmount $part"; }
  done < <(lsblk -lnpo NAME,MOUNTPOINT "$dev" | tail -n +2)
}

# Best-effort hardware sanitize. Returns 0 only if a sanitize method reported
# success; the caller still runs overwrite+verify regardless, as a safety net.
hardware_sanitize() {
  local dev="$1"
  local ok=1

  if [[ "$TRY_HW_ERASE" != "1" ]]; then
    warn "Hardware sanitize disabled (TRY_HW_ERASE=0)."
    return 1
  fi

  # 1) NVMe sanitize (external NVMe enclosures)
  if command -v nvme >/dev/null 2>&1 && [[ "$dev" == *nvme* ]]; then
    info "Attempting NVMe sanitize (block erase)..."
    if nvme sanitize "$dev" -a 2 2>/dev/null; then
      info "NVMe sanitize command accepted; waiting for completion..."
      # poll sanitize status if available
      for _ in $(seq 1 120); do
        nvme sanitize-log "$dev" 2>/dev/null | grep -qi "completed" && break
        sleep 5
      done
      ok=0
    else
      warn "NVMe sanitize not supported/refused."
    fi
  fi

  # 2) Secure discard (BLKSECDISCARD) — true erase on flash that supports it
  if command -v blkdiscard >/dev/null 2>&1; then
    info "Attempting secure discard (blkdiscard --secure)..."
    if blkdiscard -f --secure "$dev" 2>/dev/null; then
      info "Secure discard succeeded."
      ok=0
    else
      warn "Secure discard not supported; trying plain discard (TRIM)..."
      if blkdiscard -f "$dev" 2>/dev/null; then
        info "Plain discard succeeded (unmaps blocks; not a guaranteed erase)."
      else
        warn "Discard not supported by device."
      fi
    fi
  fi

  # 3) ATA Secure Erase via hdparm (opt-in; can lock the drive on failure)
  if [[ "$TRY_ATA_ERASE" == "1" ]] && command -v hdparm >/dev/null 2>&1; then
    ata_secure_erase "$dev" && ok=0
  fi

  return $ok
}

ata_secure_erase() {
  local dev="$1"
  local info_out
  info_out="$(hdparm -I "$dev" 2>/dev/null || true)"

  if ! grep -qi "Security:" <<<"$info_out"; then
    warn "ATA security info unavailable (USB bridge likely blocks it)."
    return 1
  fi
  if grep -qi "frozen" <<<"$info_out" && ! grep -qi "not.*frozen" <<<"$info_out"; then
    warn "Drive security is FROZEN; ATA Secure Erase not possible without a power-cycle."
    return 1
  fi

  local pw="wipe-$RANDOM"
  warn "Setting temporary ATA security password and issuing erase. Do NOT unplug."
  if ! hdparm --user-master u --security-set-pass "$pw" "$dev" >/dev/null 2>&1; then
    warn "Could not set ATA security password."
    return 1
  fi
  local cmd="--security-erase"
  grep -qi "enhanced erase" <<<"$info_out" && cmd="--security-erase-enhanced"
  if hdparm --user-master u "$cmd" "$pw" "$dev" >/dev/null 2>&1; then
    info "ATA Secure Erase ($cmd) completed."
    return 0
  fi
  err "ATA Secure Erase FAILED. The drive may still hold the password '$pw'."
  err "Recover with: hdparm --user-master u --security-disable '$pw' $dev"
  return 1
}

wipe_signatures() {
  local dev="$1"
  info "Removing filesystem/RAID/partition signatures..."
  wipefs -a "$dev" >/dev/null 2>&1 || warn "wipefs reported an issue (continuing)."
}

# Pick the fastest available cryptographically-strong random source.
random_stream() {
  if command -v openssl >/dev/null 2>&1; then
    # AES-CTR keystream from a fresh random key: fast, high quality.
    openssl enc -aes-256-ctr -pass "pass:$(openssl rand -hex 32)" -nosalt </dev/zero 2>/dev/null
  else
    cat /dev/urandom
  fi
}

# Whole-device overwrite. dd is EXPECTED to end with ENOSPC ("No space left");
# that is normal termination, not an error. Real correctness is checked later
# by verify_zero(), so we deliberately tolerate dd's nonzero exit here.
random_overwrite() {
  local dev="$1"
  info "Random overwrite of entire $dev ..."
  random_stream | dd of="$dev" bs="$BS" iflag=fullblock conv=fsync status=progress 2>&1 |
    grep -v "No space left" || true
  sync
}

zero_overwrite() {
  local dev="$1"
  info "Zero overwrite of entire $dev ..."
  dd if=/dev/zero of="$dev" bs="$BS" conv=fsync status=progress 2>&1 |
    grep -v "No space left" || true
  sync
}

# Authoritative check: read the device back and confirm it is all zero.
verify_zero() {
  local dev="$1"
  case "$VERIFY" in
    none)
      warn "Verification skipped (VERIFY=none)."
      return 0
      ;;
    sample)
      info "Sampling device to verify zeros (start / middle / end)..."
      local sz off nz
      sz="$(blockdev --getsize64 "$dev")"
      local total=0
      for off in 0 $((sz/2 - 8388608)) $((sz - 16777216)); do
        (( off < 0 )) && off=0
        nz="$(dd if="$dev" bs=1M skip=$((off/1048576)) count=16 status=none 2>/dev/null \
              | tr -d '\000' | wc -c)"
        total=$((total + nz))
      done
      if (( total == 0 )); then info "Sample verification passed."; return 0; fi
      err "Sample verification FAILED: found $total non-zero bytes."
      return 1
      ;;
    *)
      info "Full read-back verification (this reads the entire device)..."
      local nz
      nz="$(dd if="$dev" bs="$BS" status=none 2>/dev/null | tr -d '\000' | wc -c)"
      if (( nz == 0 )); then
        info "Verification PASSED: device reads back as all zeros."
        return 0
      fi
      err "Verification FAILED: $nz non-zero bytes remain on $dev."
      return 1
      ;;
  esac
}

recreate_partition() {
  local dev="$1"
  info "Recreating GPT partition table..."
  parted -s "$dev" mklabel gpt
  parted -s "$dev" mkpart primary 1MiB 100%
  partprobe "$dev" || true
  udevadm settle

  local part
  part="$(lsblk -lnpo NAME "$dev" | sed -n '2p')"
  if [[ -z "$part" || ! -b "$part" ]]; then
    err "Could not detect the new partition."
    exit 1
  fi

  info "Formatting $part as $FS_TYPE (label: $LABEL)..."
  case "$FS_TYPE" in
    exfat) mkfs.exfat -n "$LABEL" "$part" ;;
    ext4)  mkfs.ext4 -F -L "$LABEL" "$part" ;;
    *)     err "Unsupported FS_TYPE: $FS_TYPE"; exit 1 ;;
  esac
  sync
}

print_summary() {
  local dev="$1" hw="$2" media="$3"
  echo
  echo "==================== RESULT ===================="
  info "Device wiped and reformatted: $dev"
  echo
  if [[ "$media" == "flash" ]]; then
    if [[ "$hw" == "0" ]]; then
      echo "${GRN}Flash device, hardware sanitize succeeded${RST} — this is the"
      echo "strongest software-achievable result. Remapped/over-provisioned"
      echo "cells were handled by the controller's own erase."
    else
      echo "${YEL}Flash device, NO hardware sanitize was available.${RST}"
      echo "The addressable area was overwritten and verified as zero, but"
      echo "wear-leveling means data may persist in remapped / over-provisioned"
      echo "/ retired cells that software cannot reach. Chip-off forensics could"
      echo "recover it. For highly sensitive data, physically destroy the device."
    fi
  else
    echo "${GRN}Magnetic drive:${RST} the addressable surface was overwritten and"
    echo "verified. This meets NIST SP 800-88 'Clear'. Note: any HPA/DCO hidden"
    echo "areas (if present) are outside dd's reach — check 'hdparm -N' / '--dco-identify'."
  fi
  echo "================================================"
}

# ---- main -------------------------------------------------------------------
main() {
  need_root
  check_cmds
  list_external_drives

  read -rp "Target device, for example /dev/sdb: " DEV
  if ! is_external_drive "$DEV"; then
    err "Refusing: $DEV does not look like a removable/external disk."
    exit 1
  fi

  local media="flash"
  is_rotational "$DEV" && media="magnetic"

  echo
  echo "${RED}DANGER:${RST} this will permanently destroy ALL data on:"
  lsblk "$DEV"
  echo "  Detected media type : $media"
  echo "  Passes              : $PASSES"
  echo "  Verification        : $VERIFY"
  echo "  Hardware sanitize   : $([[ $TRY_HW_ERASE == 1 ]] && echo on || echo off)"
  echo "  ATA secure erase    : $([[ $TRY_ATA_ERASE == 1 ]] && echo on || echo off)"
  echo

  read -rp "Type exactly: WIPE $DEV : " CONFIRM
  [[ "$CONFIRM" == "WIPE $DEV" ]] || { err "Aborted."; exit 1; }

  unmount_drive "$DEV"

  local hw=1
  if hardware_sanitize "$DEV"; then hw=0; fi

  wipe_signatures "$DEV"

  local i
  for i in $(seq 1 "$PASSES"); do
    echo
    info "========== PASS $i / $PASSES =========="
    random_overwrite "$DEV"
    zero_overwrite "$DEV"
  done

  if ! verify_zero "$DEV"; then
    err "ABORTING before reformat: the overwrite could not be verified."
    err "Do NOT trust this device as wiped. It may be failing or write-protected."
    exit 1
  fi

  wipe_signatures "$DEV"
  recreate_partition "$DEV"
  print_summary "$DEV" "$hw" "$media"
}

main "$@"
