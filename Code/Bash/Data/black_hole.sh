#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME="BLACK HOLE"

ZSTD_LEVEL=10
THREADS="$(nproc)"

SMALL_FILE_MAX_BYTES=$((256 * 1024 * 1024))
SHARD_TARGET_BYTES=$((8 * 1024 * 1024 * 1024))

DELETE_ORIGINALS="no"
QUIET_MODE="no"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

COMPRESSED_EXTENSIONS=(
    ".zip" ".gz" ".gzip" ".bz2" ".xz" ".zst" ".7z" ".rar"
    ".tar" ".tgz" ".tbz" ".tbz2" ".txz" ".tar.gz" ".tar.bz2" ".tar.xz" ".tar.zst"
)

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "┌──────────────────────────────────────────────┐"
    echo "│                  ${TOOL_NAME}                  │"
    echo "│        compressed raw-text search helper      │"
    echo "└──────────────────────────────────────────────┘"
    echo -e "${NC}"
}

help_menu() {
    banner
    cat <<EOF
${BOLD}Usage:${NC}
  $0 install
  $0 compress <input_file_or_dir> <output_dir> [--delete-originals]
  $0 search <pattern> <compressed_file_or_dir> [--quiet]

${BOLD}Commands:${NC}

  ${GREEN}install${NC}
      Install required tools: zstd, zstdcat, ripgrep, coreutils, findutils.

  ${GREEN}compress${NC}
      Compress a single file or an entire directory.

      ${YELLOW}Default behavior:${NC}
        - compressed input files are ignored
        - originals are kept
        - small files are grouped into 8GB uncompressed shards
        - big files are compressed alone
        - all output .zst files go into the same shards/ folder
        - manifests are written for traceability

      ${YELLOW}Example:${NC}
        $0 compress /data/raw /data/compressed

      ${YELLOW}Dangerous option:${NC}
        --delete-originals
            Disabled by default.
            Even when passed, the script asks for confirmation.

  ${GREEN}search${NC}
      Case-insensitive ripgrep search over .zst output.

      ${YELLOW}Example:${NC}
        $0 search "gmail.com" /data/compressed

      ${YELLOW}Quiet mode:${NC}
        $0 search "gmail.com" /data/compressed --quiet

${BOLD}Current defaults:${NC}
  zstd level:             ${ZSTD_LEVEL}
  threads:                ${THREADS}
  small-file threshold:   $(human_bytes "$SMALL_FILE_MAX_BYTES")
  shard target size:      $(human_bytes "$SHARD_TARGET_BYTES")

EOF
}

human_bytes() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 bytes"
}

die() {
    echo -e "${RED}${BOLD}[ERROR]${NC} $*" >&2
    exit 1
}

warn() {
    echo -e "${YELLOW}${BOLD}[WARN]${NC} $*" >&2
}

ok() {
    echo -e "${GREEN}${BOLD}[OK]${NC} $*" >&2
}

info() {
    echo -e "${BLUE}${BOLD}[INFO]${NC} $*" >&2
}

work() {
    echo -e "${MAGENTA}${BOLD}[WORK]${NC} $*" >&2
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

is_compressed_file() {
    local path_lc
    path_lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"

    for ext in "${COMPRESSED_EXTENSIONS[@]}"; do
        if [[ "$path_lc" == *"$ext" ]]; then
            return 0
        fi
    done

    return 1
}

safe_name() {
    printf '%s' "$1" | sed 's#/#__#g; s#[^A-Za-z0-9._-]#_#g'
}

install_tools() {
    banner
    info "Installing dependencies..."

    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y zstd ripgrep coreutils findutils

    elif command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y zstd ripgrep coreutils findutils

    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm zstd ripgrep coreutils findutils

    else
        die "Unsupported package manager."
    fi

    for cmd in zstd zstdcat rg find realpath stat numfmt; do
        need_cmd "$cmd"
    done

    ok "Dependencies installed."
}

confirm_delete_originals() {
    if [[ "$DELETE_ORIGINALS" != "yes" ]]; then
        return 0
    fi

    echo
    echo -e "${RED}${BOLD}DANGER:${NC} You requested --delete-originals."
    echo -e "${RED}${BOLD}This will delete each original file after it is successfully compressed.${NC}"
    echo
    read -r -p "Type DELETE to confirm: " answer

    if [[ "$answer" != "DELETE" ]]; then
        die "Deletion not confirmed. Aborting."
    fi
}

prepare_output() {
    local output="$1"

    mkdir -p "$output/shards"
    mkdir -p "$output/manifests"
    mkdir -p "$output/tmp"

    : > "$output/manifests/grouped_shards.manifest.tsv"
    : > "$output/manifests/standalone_files.manifest.tsv"
    : > "$output/manifests/ignored_compressed_files.tsv"
    : > "$output/manifests/errors.tsv"
}

finalize_group_shard() {
    local tmp_file="$1"
    local out_file="$2"

    if [[ ! -s "$tmp_file" ]]; then
        rm -f -- "$tmp_file"
        return 0
    fi

    work "Compressing grouped shard: $(basename "$out_file") raw_size=$(human_bytes "$(stat -c%s "$tmp_file")")"

    if zstd -q -T"$THREADS" -"${ZSTD_LEVEL}" -f "$tmp_file" -o "$out_file"; then
        rm -f -- "$tmp_file"
        ok "Created $out_file"
    else
        warn "Failed to compress grouped shard: $tmp_file"
        return 1
    fi
}

compress_standalone_file() {
    local input_root="$1"
    local output="$2"
    local file="$3"
    local standalone_id="$4"

    local rel
    local size
    local base
    local out_file

    if [[ -d "$input_root" ]]; then
        rel="${file#$input_root/}"
    else
        rel="$(basename "$file")"
    fi

    size="$(stat -c%s "$file")"
    base="$(safe_name "$rel")"
    out_file="$output/shards/standalone_$(printf '%06d' "$standalone_id")_${base}.zst"

    work "Standalone big file: $rel size=$(human_bytes "$size")"

    if zstd -q -T"$THREADS" -"${ZSTD_LEVEL}" -f "$file" -o "$out_file"; then
        printf '%s\t%s\t%s\n' "$rel" "$size" "$out_file" >> "$output/manifests/standalone_files.manifest.tsv"
        ok "Created $out_file"

        if [[ "$DELETE_ORIGINALS" == "yes" ]]; then
            rm -f -- "$file"
        fi
    else
        printf '%s\t%s\t%s\n' "$rel" "$size" "compression_failed" >> "$output/manifests/errors.tsv"
        warn "Compression failed: $file"
    fi
}

append_file_to_group_shard() {
    local input_root="$1"
    local output="$2"
    local file="$3"
    local tmp_file="$4"
    local shard_name="$5"

    local rel
    local size

    if [[ -d "$input_root" ]]; then
        rel="${file#$input_root/}"
    else
        rel="$(basename "$file")"
    fi

    size="$(stat -c%s "$file")"

    {
        printf '\n===== FILE: %s SIZE: %s =====\n' "$rel" "$size"
        cat -- "$file"
        printf '\n===== END FILE: %s =====\n' "$rel"
    } >> "$tmp_file"

    printf '%s\t%s\t%s\n' "$shard_name" "$rel" "$size" >> "$output/manifests/grouped_shards.manifest.tsv"

    if [[ "$DELETE_ORIGINALS" == "yes" ]]; then
        rm -f -- "$file"
    fi
}

compress_path() {
    local input="$1"
    local output="$2"

    input="$(realpath "$input")"
    output="$(realpath -m "$output")"

    [[ -e "$input" ]] || die "Input does not exist: $input"

    confirm_delete_originals
    prepare_output "$output"

    banner
    info "Input: $input"
    info "Output: $output"
    info "All compressed files will be written to: $output/shards"
    info "ZSTD level: $ZSTD_LEVEL"
    info "Threads: $THREADS"
    info "Small-file threshold: $(human_bytes "$SMALL_FILE_MAX_BYTES")"
    info "Grouped shard target: $(human_bytes "$SHARD_TARGET_BYTES")"
    info "Delete originals: $DELETE_ORIGINALS"

    local shard_id=1
    local standalone_id=1
    local shard_size=0
    local small_count=0
    local big_count=0
    local ignored_count=0
    local error_count=0
    local total_seen=0

    local shard_name
    local shard_tmp
    local shard_out

    shard_name="group_$(printf '%06d' "$shard_id").zst"
    shard_tmp="$output/tmp/group_$(printf '%06d' "$shard_id").raw"
    shard_out="$output/shards/$shard_name"
    : > "$shard_tmp"

    process_one_file() {
        local file="$1"
        local size
        local rel

        total_seen=$((total_seen + 1))

        if [[ ! -f "$file" ]]; then
            return 0
        fi

        if is_compressed_file "$file"; then
            if [[ -d "$input" ]]; then
                rel="${file#$input/}"
            else
                rel="$(basename "$file")"
            fi

            warn "Ignoring compressed input: $rel"
            printf '%s\n' "$rel" >> "$output/manifests/ignored_compressed_files.tsv"
            ignored_count=$((ignored_count + 1))
            return 0
        fi

        if ! size="$(stat -c%s "$file" 2>/dev/null)"; then
            warn "Could not stat file: $file"
            printf '%s\t%s\n' "$file" "stat_failed" >> "$output/manifests/errors.tsv"
            error_count=$((error_count + 1))
            return 0
        fi

        if (( size >= SMALL_FILE_MAX_BYTES )); then
            compress_standalone_file "$input" "$output" "$file" "$standalone_id"
            standalone_id=$((standalone_id + 1))
            big_count=$((big_count + 1))
            return 0
        fi

        if (( shard_size > 0 && shard_size + size >= SHARD_TARGET_BYTES )); then
            finalize_group_shard "$shard_tmp" "$shard_out" || error_count=$((error_count + 1))

            shard_id=$((shard_id + 1))
            shard_size=0
            shard_name="group_$(printf '%06d' "$shard_id").zst"
            shard_tmp="$output/tmp/group_$(printf '%06d' "$shard_id").raw"
            shard_out="$output/shards/$shard_name"
            : > "$shard_tmp"
        fi

        if [[ -d "$input" ]]; then
            rel="${file#$input/}"
        else
            rel="$(basename "$file")"
        fi

        work "Grouping small file: shard=$shard_name file=$rel size=$(human_bytes "$size")"

        append_file_to_group_shard "$input" "$output" "$file" "$shard_tmp" "$shard_name"
        shard_size=$((shard_size + size))
        small_count=$((small_count + 1))
    }

    if [[ -f "$input" ]]; then
        process_one_file "$input"
    elif [[ -d "$input" ]]; then
        while IFS= read -r -d '' file; do
            process_one_file "$file"
        done < <(find "$input" -type f -print0)
    else
        die "Input is neither a file nor a directory: $input"
    fi

    finalize_group_shard "$shard_tmp" "$shard_out" || error_count=$((error_count + 1))
    rmdir "$output/tmp" 2>/dev/null || true

    cat > "$output/compression_summary.txt" <<EOF
tool=$TOOL_NAME
input=$input
output=$output
shards_dir=$output/shards
zstd_level=$ZSTD_LEVEL
threads=$THREADS
small_file_max_bytes=$SMALL_FILE_MAX_BYTES
small_file_max_human=$(human_bytes "$SMALL_FILE_MAX_BYTES")
shard_target_bytes=$SHARD_TARGET_BYTES
shard_target_human=$(human_bytes "$SHARD_TARGET_BYTES")
total_files_seen=$total_seen
small_files_grouped=$small_count
big_files_compressed_standalone=$big_count
compressed_files_ignored=$ignored_count
errors=$error_count
delete_originals=$DELETE_ORIGINALS
EOF

    ok "Compression finished."
    ok "Summary: $output/compression_summary.txt"
    ok "Shards: $output/shards"
    ok "Grouped manifest: $output/manifests/grouped_shards.manifest.tsv"
    ok "Standalone manifest: $output/manifests/standalone_files.manifest.tsv"

    if (( ignored_count > 0 )); then
        warn "Ignored compressed files: $ignored_count"
        warn "List: $output/manifests/ignored_compressed_files.tsv"
    fi

    if (( error_count > 0 )); then
        warn "Errors: $error_count"
        warn "List: $output/manifests/errors.tsv"
    fi
}

search_one_zst() {
    local pattern="$1"
    local file="$2"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        echo -e "${CYAN}${BOLD}[SEARCH]${NC} $file" >&2
    fi

    zstdcat -- "$file" 2>/dev/null | rg \
        -i \
        -n \
        --color=always \
        --max-columns=4096 \
        --max-columns-preview \
        -- "$pattern" || true
}

search_path() {
    local pattern="$1"
    local target="$2"

    [[ -e "$target" ]] || die "Search path does not exist: $target"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        banner
        info "Pattern: $pattern"
        info "Target: $target"
    fi

    if [[ -f "$target" ]]; then
        [[ "$target" == *.zst ]] || die "Search file is not .zst: $target"
        search_one_zst "$pattern" "$target"
        return 0
    fi

    find "$target" -type f -name '*.zst' -print0 | while IFS= read -r -d '' file; do
        search_one_zst "$pattern" "$file"
    done
}

main() {
    [[ $# -ge 1 ]] || {
        help_menu
        exit 1
    }

    case "$1" in
        install)
            install_tools
            ;;

        compress)
            [[ $# -eq 3 || $# -eq 4 ]] || {
                help_menu
                exit 1
            }

            if [[ $# -eq 4 ]]; then
                [[ "$4" == "--delete-originals" ]] || die "Unknown option: $4"
                DELETE_ORIGINALS="yes"
            fi

            compress_path "$2" "$3"
            ;;

        search)
            [[ $# -eq 3 || $# -eq 4 ]] || {
                help_menu
                exit 1
            }

            if [[ $# -eq 4 ]]; then
                [[ "$4" == "--quiet" ]] || die "Unknown option: $4"
                QUIET_MODE="yes"
            fi

            search_path "$2" "$3"
            ;;

        -h|--help|help)
            help_menu
            ;;

        *)
            help_menu
            exit 1
            ;;
    esac
}

main "$@"
