#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# CONFIG
# ============================================================

TOOL_NAME="BLACK HOLE"

ZSTD_LEVEL=10
THREADS="$(nproc)"

# Small files are grouped until the raw shard reaches ~8GB.
SHARD_TARGET_BYTES=$((8 * 1024 * 1024 * 1024))

# Files >= 8GB are compressed alone.
BIG_FILE_MIN_BYTES=$SHARD_TARGET_BYTES

DELETE_ORIGINALS="no"
QUIET_MODE="no"

COMPRESSED_EXTENSIONS=(
    ".zip" ".gz" ".gzip" ".bz2" ".xz" ".zst" ".7z" ".rar"
    ".tar" ".tgz" ".tbz" ".tbz2" ".txz"
    ".tar.gz" ".tar.bz2" ".tar.xz" ".tar.zst"
)

# ============================================================
# COLORS
# ============================================================

if [[ -t 2 ]]; then
    RED="$(printf '\033[0;31m')"
    GREEN="$(printf '\033[0;32m')"
    YELLOW="$(printf '\033[1;33m')"
    BLUE="$(printf '\033[0;34m')"
    MAGENTA="$(printf '\033[0;35m')"
    CYAN="$(printf '\033[0;36m')"
    BOLD="$(printf '\033[1m')"
    DIM="$(printf '\033[2m')"
    NC="$(printf '\033[0m')"
else
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
    BOLD=""
    DIM=""
    NC=""
fi

# ============================================================
# UI
# ============================================================

banner() {
    printf '%b\n' "${CYAN}${BOLD}"
    printf '%s\n' "┌──────────────────────────────────────────────┐"
    printf '%s\n' "│                  ${TOOL_NAME}                  │"
    printf '%s\n' "│        compressed raw-text search helper      │"
    printf '%s\n' "└──────────────────────────────────────────────┘"
    printf '%b\n' "${NC}"
}

human_bytes() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || printf '%s bytes\n' "$1"
}

die() {
    printf '%b\n' "${RED}${BOLD}[ERROR]${NC} $*" >&2
    exit 1
}

warn() {
    printf '%b\n' "${YELLOW}${BOLD}[WARN]${NC} $*" >&2
}

ok() {
    printf '%b\n' "${GREEN}${BOLD}[OK]${NC} $*" >&2
}

info() {
    printf '%b\n' "${BLUE}${BOLD}[INFO]${NC} $*" >&2
}

work() {
    printf '%b\n' "${MAGENTA}${BOLD}[WORK]${NC} $*" >&2
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
        - files smaller than 8GB are grouped into 8GB raw shards
        - files >= 8GB are compressed alone
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
  grouped shard size:     $(human_bytes "$SHARD_TARGET_BYTES")
  big-file threshold:     $(human_bytes "$BIG_FILE_MIN_BYTES")

EOF
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

safe_name() {
    printf '%s' "$1" | sed 's#/#__#g; s#[^A-Za-z0-9._-]#_#g'
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

# ============================================================
# INSTALL
# ============================================================

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

    for cmd in zstd zstdcat rg find realpath stat numfmt sed tr cat; do
        need_cmd "$cmd"
    done

    ok "Dependencies installed."
}

# ============================================================
# SAFETY
# ============================================================

confirm_delete_originals() {
    if [[ "$DELETE_ORIGINALS" != "yes" ]]; then
        return 0
    fi

    printf '\n' >&2
    printf '%b\n' "${RED}${BOLD}DANGER:${NC} You requested --delete-originals." >&2
    printf '%b\n' "${RED}${BOLD}Original files will be deleted after successful compression.${NC}" >&2
    printf '\n' >&2

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

# ============================================================
# COMPRESSION
# ============================================================

finalize_group_shard() {
    local tmp_file="$1"
    local out_file="$2"

    if [[ ! -s "$tmp_file" ]]; then
        rm -f -- "$tmp_file"
        return 0
    fi

    if [[ -e "$out_file" ]]; then
        die "Refusing to overwrite existing shard: $out_file"
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

    if [[ -e "$out_file" ]]; then
        die "Refusing to overwrite existing standalone shard: $out_file"
    fi

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
        return 1
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

# ------------------------------------------------------------
# FIXED: Group shard management
# ------------------------------------------------------------
#
# Important guarantees:
#   1. Every grouped shard gets a unique monotonically increasing name:
#        group_000001.zst
#        group_000002.zst
#        group_000003.zst
#        ...
#
#   2. The active raw shard is finalized before a new group starts.
#
#   3. Existing .zst shards are never overwritten.
#
#   4. The tmp raw file name always matches the final shard name, making
#      debugging simple:
#        tmp/group_000001.raw -> shards/group_000001.zst
#
#   5. The last partially-filled group is always compressed at the end.
#
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
    info "Grouped shard target: $(human_bytes "$SHARD_TARGET_BYTES")"
    info "Big-file threshold: $(human_bytes "$BIG_FILE_MIN_BYTES")"
    info "Delete originals: $DELETE_ORIGINALS"

    local standalone_id=1
    local shard_size=0
    local small_count=0
    local big_count=0
    local ignored_count=0
    local error_count=0
    local total_seen=0

    local group_id=1
    local current_group_name=""
    local current_group_tmp=""
    local current_group_out=""

    next_available_group_id() {
        local candidate

        while true; do
            candidate="$(printf '%06d' "$group_id")"

            current_group_name="group_${candidate}.zst"
            current_group_tmp="$output/tmp/group_${candidate}.raw"
            current_group_out="$output/shards/$current_group_name"

            if [[ ! -e "$current_group_tmp" && ! -e "$current_group_out" ]]; then
                return 0
            fi

            (( group_id += 1 ))
        done
    }

    start_group_shard() {
        next_available_group_id

        # Refuse accidental reuse even if the filesystem state changes between
        # next_available_group_id and this point.
        if [[ -e "$current_group_tmp" || -e "$current_group_out" ]]; then
            die "Internal shard naming collision: $current_group_name"
        fi

        : > "$current_group_tmp"
        shard_size=0

        work "Started grouped shard: $current_group_name"
    }

    finalize_group_shard() {
        if [[ -z "$current_group_tmp" || -z "$current_group_out" || -z "$current_group_name" ]]; then
            return 0
        fi

        if (( shard_size <= 0 )) || [[ ! -s "$current_group_tmp" ]]; then
            rm -f -- "$current_group_tmp"
            current_group_name=""
            current_group_tmp=""
            current_group_out=""
            shard_size=0
            return 0
        fi

        if [[ -e "$current_group_out" ]]; then
            die "Refusing to overwrite existing grouped shard: $current_group_out"
        fi

        work "Compressing grouped shard: $current_group_name raw_size=$(human_bytes "$(stat -c%s "$current_group_tmp")")"

        # Do not use -f here. Existing output must remain a hard failure.
        if zstd -q -T"$THREADS" -"${ZSTD_LEVEL}" "$current_group_tmp" -o "$current_group_out"; then
            rm -f -- "$current_group_tmp"
            ok "Created $current_group_out"
        else
            printf '%s\t%s\n' "$current_group_tmp" "group_compression_failed" >> "$output/manifests/errors.tsv"
            warn "Failed to compress grouped shard: $current_group_tmp"
            return 1
        fi

        (( group_id += 1 ))

        current_group_name=""
        current_group_tmp=""
        current_group_out=""
        shard_size=0
    }

    process_one_file() {
        local file="$1"
        local size rel

        (( total_seen += 1 ))

        [[ -f "$file" ]] || return 0

        if is_compressed_file "$file"; then
            if [[ -d "$input" ]]; then
                rel="${file#$input/}"
            else
                rel="$(basename "$file")"
            fi

            warn "Ignoring compressed input: $rel"
            printf '%s\n' "$rel" >> "$output/manifests/ignored_compressed_files.tsv"
            (( ignored_count += 1 ))
            return 0
        fi

        if ! size="$(stat -c%s "$file" 2>/dev/null)"; then
            warn "Could not stat file: $file"
            printf '%s\t%s\n' "$file" "stat_failed" >> "$output/manifests/errors.tsv"
            (( error_count += 1 ))
            return 0
        fi

        # Standalone big file.
        if (( size >= BIG_FILE_MIN_BYTES )); then
            if ! compress_standalone_file "$input" "$output" "$file" "$standalone_id"; then
                (( error_count += 1 ))
            fi

            (( standalone_id += 1 ))
            (( big_count += 1 ))
            return 0
        fi

        # Lazily create the first group only when the first small file appears.
        if [[ -z "$current_group_tmp" ]]; then
            start_group_shard
        fi

        # If adding this file would exceed the target, close the current group
        # and start a fresh one. This is the critical anti-overwrite path.
        if (( shard_size > 0 && shard_size + size > SHARD_TARGET_BYTES )); then
            if ! finalize_group_shard; then
                (( error_count += 1 ))
            fi
            start_group_shard
        fi

        if [[ -d "$input" ]]; then
            rel="${file#$input/}"
        else
            rel="$(basename "$file")"
        fi

        work "Grouping small file: shard=$current_group_name file=$rel size=$(human_bytes "$size")"

        if append_file_to_group_shard "$input" "$output" "$file" "$current_group_tmp" "$current_group_name"; then
            (( shard_size += size ))
            (( small_count += 1 ))
        else
            warn "Failed to append file to group shard: $file"
            printf '%s\t%s\n' "$file" "append_failed" >> "$output/manifests/errors.tsv"
            (( error_count += 1 ))
        fi
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

    # Finalize the last partially-filled grouped shard. This is what creates
    # group_000001.zst even when the total small-file data is below 8GB.
    if ! finalize_group_shard; then
        (( error_count += 1 ))
    fi

    rmdir "$output/tmp" 2>/dev/null || true

    cat > "$output/compression_summary.txt" <<EOF
tool=$TOOL_NAME
input=$input
output=$output
shards_dir=$output/shards
zstd_level=$ZSTD_LEVEL
threads=$THREADS
shard_target_bytes=$SHARD_TARGET_BYTES
shard_target_human=$(human_bytes "$SHARD_TARGET_BYTES")
big_file_min_bytes=$BIG_FILE_MIN_BYTES
big_file_min_human=$(human_bytes "$BIG_FILE_MIN_BYTES")
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

# ============================================================
# SEARCH
# ============================================================

search_one_zst() {
    local pattern="$1"
    local file="$2"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        printf '%b\n' "${CYAN}${BOLD}[SEARCH]${NC} $file" >&2
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

# ============================================================
# MAIN
# ============================================================

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
