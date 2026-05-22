#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# CONFIG
# ============================================================

ZSTD_LEVEL=10
THREADS="$(nproc)"

# Files smaller than this are grouped into shards.
SMALL_FILE_MAX_BYTES=$((128 * 1024 * 1024))

# Target uncompressed shard size.
SHARD_TARGET_BYTES=$((4 * 1024 * 1024 * 1024))

# Marker used between concatenated files.
FILE_MARKER_PREFIX="===== FILE:"

QUIET_MODE="no"

# ============================================================
# COLORS
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================================
# HELP
# ============================================================

help_menu() {
    cat <<EOF

Usage:
  $0 install
  $0 compress <input_path> <output_path> [--delete-originals]
  $0 search <pattern> <compressed_file_or_path> [--quiet]

Commands:

  install
      Install zstd, zstdcat, tar and ripgrep.

  compress
      Compress recursively.

      Small files:
        grouped into ~4GB .zst shards

      Big files:
        compressed individually

      Example:
        $0 compress /data/raw /data/compressed

      Optional:
        --delete-originals

  search
      Case-insensitive ripgrep against .zst data.

      Example:
        $0 search "gmail.com" /data/compressed

      Quiet mode:
        $0 search "gmail.com" /data/compressed --quiet

EOF
}

# ============================================================
# INSTALL
# ============================================================

install_tools() {
    echo -e "${YELLOW}[+] Installing dependencies...${NC}"

    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y zstd ripgrep tar coreutils findutils

    elif command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y zstd ripgrep tar coreutils findutils

    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm zstd ripgrep tar coreutils findutils

    else
        echo -e "${RED}[ERROR] Unsupported package manager.${NC}"
        exit 1
    fi

    for cmd in zstd zstdcat rg tar find realpath; do
        command -v "$cmd" >/dev/null 2>&1 || {
            echo -e "${RED}[ERROR] Missing command: $cmd${NC}"
            exit 1
        }
    done

    echo -e "${GREEN}[OK] Dependencies installed.${NC}"
}

# ============================================================
# HELPERS
# ============================================================

human_bytes() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 bytes"
}

finalize_shard() {
    local tmp_file="$1"
    local out_file="$2"

    if [[ ! -s "$tmp_file" ]]; then
        rm -f "$tmp_file"
        return 0
    fi

    echo -e "${YELLOW}[SHARD] Compressing $(basename "$out_file") size=$(human_bytes "$(stat -c%s "$tmp_file")")${NC}"

    zstd \
        -q \
        -T"$THREADS" \
        -"${ZSTD_LEVEL}" \
        -f \
        "$tmp_file" \
        -o "$out_file"

    rm -f "$tmp_file"

    echo -e "${GREEN}[OK]${NC} $out_file"
}

compress_big_file() {
    local input_root="$1"
    local output_root="$2"
    local file="$3"
    local delete_originals="$4"

    local rel="${file#$input_root/}"
    local out_file="$output_root/big/$rel.zst"
    local manifest="$output_root/manifests/big_files.manifest.tsv"

    mkdir -p "$(dirname "$out_file")"

    echo -e "${GREEN}[BIG]${NC} $rel"

    zstd \
        -q \
        -T"$THREADS" \
        -"${ZSTD_LEVEL}" \
        -f \
        "$file" \
        -o "$out_file"

    printf '%s\t%s\t%s\n' "$rel" "$(stat -c%s "$file")" "$out_file" >> "$manifest"

    if [[ "$delete_originals" == "yes" ]]; then
        rm -f -- "$file"
    fi
}

append_small_file_to_shard() {
    local input_root="$1"
    local file="$2"
    local tmp_file="$3"
    local manifest="$4"

    local rel="${file#$input_root/}"
    local size
    size="$(stat -c%s "$file")"

    {
        printf '\n%s %s SIZE: %s =====\n' "$FILE_MARKER_PREFIX" "$rel" "$size"
        cat -- "$file"
        printf '\n===== END FILE: %s =====\n' "$rel"
    } >> "$tmp_file"

    printf '%s\t%s\n' "$rel" "$size" >> "$manifest"
}

# ============================================================
# COMPRESS
# ============================================================

compress_recursive() {
    local input="$1"
    local output="$2"
    local delete_originals="${3:-no}"

    input="$(realpath "$input")"
    output="$(realpath -m "$output")"

    if [[ ! -d "$input" ]]; then
        echo -e "${RED}[ERROR] Input path is not a directory.${NC}"
        exit 1
    fi

    mkdir -p "$output/shards"
    mkdir -p "$output/big"
    mkdir -p "$output/manifests"
    mkdir -p "$output/tmp"

    echo -e "${YELLOW}[+] Input: $input${NC}"
    echo -e "${YELLOW}[+] Output: $output${NC}"
    echo -e "${YELLOW}[+] Threads: $THREADS${NC}"
    echo -e "${YELLOW}[+] ZSTD level: $ZSTD_LEVEL${NC}"
    echo -e "${YELLOW}[+] Small file threshold: $(human_bytes "$SMALL_FILE_MAX_BYTES")${NC}"
    echo -e "${YELLOW}[+] Shard target size: $(human_bytes "$SHARD_TARGET_BYTES")${NC}"

    if [[ "$delete_originals" == "yes" ]]; then
        echo -e "${RED}[!] Originals will be deleted after compression.${NC}"
    fi

    local shard_id=1
    local shard_size=0
    local small_count=0
    local big_count=0

    local shard_tmp
    local shard_out
    local shard_manifest

    shard_tmp="$output/tmp/shard_$(printf '%06d' "$shard_id").raw"
    shard_out="$output/shards/shard_$(printf '%06d' "$shard_id").zst"
    shard_manifest="$output/manifests/shard_$(printf '%06d' "$shard_id").manifest.tsv"

    : > "$shard_tmp"
    : > "$shard_manifest"
    : > "$output/manifests/big_files.manifest.tsv"

    while IFS= read -r -d '' file; do

        size="$(stat -c%s "$file")"

        if (( size >= SMALL_FILE_MAX_BYTES )); then
            compress_big_file "$input" "$output" "$file" "$delete_originals"
            big_count=$((big_count + 1))
            continue
        fi

        if (( shard_size > 0 && shard_size + size >= SHARD_TARGET_BYTES )); then

            finalize_shard "$shard_tmp" "$shard_out"

            shard_id=$((shard_id + 1))
            shard_size=0

            shard_tmp="$output/tmp/shard_$(printf '%06d' "$shard_id").raw"
            shard_out="$output/shards/shard_$(printf '%06d' "$shard_id").zst"
            shard_manifest="$output/manifests/shard_$(printf '%06d' "$shard_id").manifest.tsv"

            : > "$shard_tmp"
            : > "$shard_manifest"
        fi

        rel="${file#$input/}"

        echo -e "${GREEN}[SMALL]${NC} shard=$(printf '%06d' "$shard_id") $rel"

        append_small_file_to_shard "$input" "$file" "$shard_tmp" "$shard_manifest"

        shard_size=$((shard_size + size))
        small_count=$((small_count + 1))

        if [[ "$delete_originals" == "yes" ]]; then
            rm -f -- "$file"
        fi

    done < <(find "$input" -type f -print0)

    finalize_shard "$shard_tmp" "$shard_out"

    rmdir "$output/tmp" 2>/dev/null || true

    cat > "$output/compression_summary.txt" <<EOF
input=$input
output=$output
small_file_max_bytes=$SMALL_FILE_MAX_BYTES
shard_target_bytes=$SHARD_TARGET_BYTES
zstd_level=$ZSTD_LEVEL
threads=$THREADS
small_files_grouped=$small_count
big_files_compressed=$big_count
delete_originals=$delete_originals
EOF

    echo -e "${GREEN}[OK] Compression finished.${NC}"
    echo -e "${GREEN}[OK] Small files grouped: $small_count${NC}"
    echo -e "${GREEN}[OK] Big files compressed: $big_count${NC}"
    echo -e "${GREEN}[OK] Summary: $output/compression_summary.txt${NC}"
}

# ============================================================
# SEARCH
# ============================================================

search_one_zst() {
    local pattern="$1"
    local file="$2"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        echo -e "${GREEN}[SEARCH]${NC} $file"
    fi

    zstdcat -- "$file" 2>/dev/null | \
        rg \
            -i \
            -n \
            --color=always \
            --max-columns=4096 \
            --max-columns-preview \
            -- "$pattern" || true
}

search_zstd() {
    local pattern="$1"
    local target="$2"

    if [[ ! -e "$target" ]]; then
        echo -e "${RED}[ERROR] Path does not exist.${NC}"
        exit 1
    fi

    if [[ "$QUIET_MODE" != "yes" ]]; then
        echo -e "${YELLOW}[+] Searching for:${NC} $pattern"
        echo -e "${YELLOW}[+] Target:${NC} $target"
    fi

    if [[ -f "$target" ]]; then

        if [[ "$target" != *.zst ]]; then
            echo -e "${RED}[ERROR] File is not .zst${NC}"
            exit 1
        fi

        search_one_zst "$pattern" "$target"
        exit 0
    fi

    find "$target" -type f -name '*.zst' -print0 | \
    while IFS= read -r -d '' file; do
        search_one_zst "$pattern" "$file"
    done
}

# ============================================================
# MAIN
# ============================================================

main() {

    if [[ $# -lt 1 ]]; then
        help_menu
        exit 1
    fi

    cmd="$1"

    case "$cmd" in

        install)
            install_tools
            ;;

        compress)

            if [[ $# -ne 3 && $# -ne 4 ]]; then
                help_menu
                exit 1
            fi

            delete_originals="no"

            if [[ $# -eq 4 ]]; then

                if [[ "$4" == "--delete-originals" ]]; then
                    delete_originals="yes"
                else
                    echo -e "${RED}[ERROR] Unknown option: $4${NC}"
                    exit 1
                fi
            fi

            compress_recursive "$2" "$3" "$delete_originals"
            ;;

        search)

            if [[ $# -lt 3 || $# -gt 4 ]]; then
                help_menu
                exit 1
            fi

            if [[ $# -eq 4 ]]; then

                if [[ "$4" == "--quiet" ]]; then
                    QUIET_MODE="yes"
                else
                    echo -e "${RED}[ERROR] Unknown option: $4${NC}"
                    exit 1
                fi
            fi

            search_zstd "$2" "$3"
            ;;

        *)
            help_menu
            exit 1
            ;;
    esac
}

main "$@"
