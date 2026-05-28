#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# BLACK HOLE - incremental compressed raw-text search helper
# ============================================================
# Main guarantees:
#   - compression is append-only by default
#   - existing shards are never overwritten
#   - manifests are preserved and extended, not rewritten
#   - repeated runs can add more data to the same output directory
#   - searches over the output directory include old and new shards
# ============================================================

TOOL_NAME="BLACK HOLE"
ZSTD_LEVEL="${BLACK_HOLE_ZSTD_LEVEL:-10}"
THREADS="${BLACK_HOLE_THREADS:-$(nproc 2>/dev/null || printf '1')}"
SHARD_TARGET_BYTES="${BLACK_HOLE_SHARD_TARGET_BYTES:-$((8 * 1024 * 1024 * 1024))}"
BIG_FILE_MIN_BYTES="${BLACK_HOLE_BIG_FILE_MIN_BYTES:-$SHARD_TARGET_BYTES}"
DELETE_ORIGINALS="no"
QUIET_MODE="no"
SKIP_KNOWN="yes"
CASE_INSENSITIVE="yes"
RG_EXTRA_ARGS=()

COMPRESSED_EXTENSIONS=(
    ".tar.zst" ".tar.xz" ".tar.bz2" ".tar.gz"
    ".zip" ".gz" ".gzip" ".bz2" ".xz" ".zst" ".7z" ".rar"
    ".tar" ".tgz" ".tbz" ".tbz2" ".txz"
)

if [[ -t 2 ]]; then
    RED="$(printf '\033[0;31m')"; GREEN="$(printf '\033[0;32m')"; YELLOW="$(printf '\033[1;33m')"
    BLUE="$(printf '\033[0;34m')"; MAGENTA="$(printf '\033[0;35m')"; CYAN="$(printf '\033[0;36m')"
    BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"; NC="$(printf '\033[0m')"
else
    RED=""; GREEN=""; YELLOW=""; BLUE=""; MAGENTA=""; CYAN=""; BOLD=""; DIM=""; NC=""
fi

banner() {
    [[ "$QUIET_MODE" == "yes" ]] && return 0
    printf '%b\n' "${CYAN}${BOLD}"
    printf '%s\n' '┌────────────────────────────────────────────────────────────┐'
    printf '%s\n' '│                       BLACK HOLE                           │'
    printf '%s\n' '│         append-only compressed raw-text search             │'
    printf '%s\n' '└────────────────────────────────────────────────────────────┘'
    printf '%b\n' "${NC}"
}

log() { local tag="$1" color="$2" msg="$3"; [[ "$QUIET_MODE" == "yes" ]] && return 0; printf '%b\n' "${color}${BOLD}[$tag]${NC} $msg" >&2; }
ok() { log "OK" "$GREEN" "$*"; }
warn() { log "WARN" "$YELLOW" "$*"; }
info() { log "INFO" "$BLUE" "$*"; }
work() { log "WORK" "$MAGENTA" "$*"; }
die() { printf '%b\n' "${RED}${BOLD}[ERROR]${NC} $*" >&2; exit 1; }

human_bytes() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || printf '%sB' "$1"; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }

require_runtime_tools() {
    for cmd in zstd zstdcat rg find realpath stat numfmt sed tr cat awk sort date mkdir basename mktemp grep; do
        need_cmd "$cmd"
    done
}

safe_name() { printf '%s' "$1" | sed 's#/#__#g; s#[^A-Za-z0-9._-]#_#g'; }
file_mtime() { stat -c '%Y' -- "$1"; }
file_size() { stat -c '%s' -- "$1"; }

is_compressed_file() {
    local path_lc ext
    path_lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    for ext in "${COMPRESSED_EXTENSIONS[@]}"; do
        [[ "$path_lc" == *"$ext" ]] && return 0
    done
    return 1
}

help_menu() {
    banner
    cat <<EOF
${BOLD}Usage:${NC}
  $0 install
  $0 compress <input_file_or_dir> <output_dir> [--delete-originals] [--no-skip-known] [--quiet|--quit]
  $0 search <pattern> <compressed_file_or_dir> [--quiet|--quit] [--fixed-string] [--case-sensitive]

${BOLD}Incremental behavior:${NC}
  - Existing manifests are not rewritten.
  - Existing shards are not overwritten.
  - New runs create new shard IDs after the highest existing ID.
  - Searching an output directory searches all old and new .zst shards.
  - By default, files already seen with the same absolute path, size and mtime are skipped.

${BOLD}Examples:${NC}
  $0 compress /data/raw_batch_01 /data/blackhole
  $0 compress /data/raw_batch_02 /data/blackhole
  $0 search 'gmail.com' /data/blackhole
  $0 search 'literal[.]domain' /data/blackhole --fixed-string

${BOLD}Environment overrides:${NC}
  BLACK_HOLE_ZSTD_LEVEL=10
  BLACK_HOLE_THREADS=4
  BLACK_HOLE_SHARD_TARGET_BYTES=$((1024 * 1024 * 1024))

${BOLD}Current defaults:${NC}
  zstd level:          ${ZSTD_LEVEL}
  threads:             ${THREADS}
  grouped shard size:  $(human_bytes "$SHARD_TARGET_BYTES")
  big-file threshold:  $(human_bytes "$BIG_FILE_MIN_BYTES")
EOF
}

install_tools() {
    banner
    info "Installing dependencies..."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y zstd ripgrep coreutils findutils gawk
    elif command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y zstd ripgrep coreutils findutils gawk
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm zstd ripgrep coreutils findutils gawk
    else
        die "Unsupported package manager. Install zstd, ripgrep, coreutils, findutils and awk manually."
    fi
    require_runtime_tools
    ok "Dependencies installed."
}

ensure_file_with_header() {
    local file="$1" header="$2"
    if [[ ! -e "$file" || ! -s "$file" ]]; then
        printf '%s\n' "$header" > "$file"
    fi
}

prepare_output() {
    local output="$1"
    mkdir -p "$output/shards" "$output/manifests" "$output/tmp"
    ensure_file_with_header "$output/manifests/runs.tsv" $'run_id\tstarted_at_epoch\tinput\toutput\tzstd_level\tthreads\tshard_target_bytes\tbig_file_min_bytes\tdelete_originals\tskip_known'
    ensure_file_with_header "$output/manifests/grouped_shards.manifest.tsv" $'run_id\tshard_name\tshard_path\tsource_abs\tsource_rel\tsize\tmtime'
    ensure_file_with_header "$output/manifests/standalone_files.manifest.tsv" $'run_id\tshard_name\tshard_path\tsource_abs\tsource_rel\tsize\tmtime'
    ensure_file_with_header "$output/manifests/ignored_compressed_files.tsv" $'run_id\tsource_abs\tsource_rel\tsize\tmtime\treason'
    ensure_file_with_header "$output/manifests/skipped_known_files.tsv" $'run_id\tsource_abs\tsource_rel\tsize\tmtime\treason'
    ensure_file_with_header "$output/manifests/errors.tsv" $'run_id\tsource_abs\tsource_rel\tsize\tmtime\terror'
}

next_numeric_id() {
    local dir="$1" prefix="$2" max_id
    max_id="$(find "$dir" -maxdepth 1 -type f -name "${prefix}_[0-9][0-9][0-9][0-9][0-9][0-9]*.zst" -printf '%f\n' 2>/dev/null \
        | sed -n "s/^${prefix}_\([0-9][0-9][0-9][0-9][0-9][0-9]\).*$/\1/p" \
        | sort -n | tail -n 1)"
    if [[ -z "$max_id" ]]; then printf '1'; else printf '%d' "$((10#$max_id + 1))"; fi
}

build_known_index() {
    local output="$1" index_file="$2" manifest
    : > "$index_file"
    for manifest in "$output/manifests/grouped_shards.manifest.tsv" "$output/manifests/standalone_files.manifest.tsv"; do
        [[ -s "$manifest" ]] || continue
        awk -F'\t' 'NR > 1 && NF >= 7 { print $4 "\t" $6 "\t" $7 }' "$manifest" >> "$index_file"
    done
    sort -u -o "$index_file" "$index_file" 2>/dev/null || true
}

known_file() {
    local index_file="$1" abs="$2" size="$3" mtime="$4" key
    [[ -s "$index_file" ]] || return 1
    key="$(printf '%s\t%s\t%s' "$abs" "$size" "$mtime")"
    grep -Fqx -- "$key" "$index_file" 2>/dev/null
}

relative_path() {
    local root="$1" file="$2"
    if [[ -d "$root" ]]; then printf '%s' "${file#$root/}"; else basename -- "$file"; fi
}

confirm_delete_originals() {
    [[ "$DELETE_ORIGINALS" != "yes" ]] && return 0
    printf '\n%b\n' "${RED}${BOLD}DANGER:${NC} --delete-originals was requested." >&2
    printf '%b\n\n' "${RED}${BOLD}Files are deleted only after successful compression, but this is destructive.${NC}" >&2
    read -r -p "Type DELETE to confirm: " answer
    [[ "$answer" == "DELETE" ]] || die "Deletion not confirmed. Aborting."
}

append_file_to_group_raw() {
    local input_root="$1" output="$2" run_id="$3" file="$4" tmp_file="$5" shard_name="$6" shard_path="$7"
    local abs rel size mtime
    abs="$(realpath -- "$file")"; rel="$(relative_path "$input_root" "$abs")"; size="$(file_size "$abs")"; mtime="$(file_mtime "$abs")"
    {
        printf '\n===== BLACK_HOLE_FILE_BEGIN path=%s size=%s mtime=%s =====\n' "$rel" "$size" "$mtime"
        cat -- "$abs"
        printf '\n===== BLACK_HOLE_FILE_END path=%s =====\n' "$rel"
    } >> "$tmp_file"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$shard_name" "$shard_path" "$abs" "$rel" "$size" "$mtime" >> "$output/manifests/grouped_shards.manifest.tsv"
    [[ "$DELETE_ORIGINALS" == "yes" ]] && rm -f -- "$abs"
    return 0
}

compress_standalone_file() {
    local input_root="$1" output="$2" run_id="$3" file="$4" standalone_id="$5"
    local abs rel size mtime base shard_name out_file
    abs="$(realpath -- "$file")"; rel="$(relative_path "$input_root" "$abs")"; size="$(file_size "$abs")"; mtime="$(file_mtime "$abs")"
    base="$(safe_name "$rel")"
    shard_name="standalone_$(printf '%06d' "$standalone_id")_${base}.zst"
    out_file="$output/shards/$shard_name"
    [[ -e "$out_file" ]] && die "Refusing to overwrite existing standalone shard: $out_file"
    work "Standalone shard <- $rel ($(human_bytes "$size"))"
    if zstd -q -T"$THREADS" -"$ZSTD_LEVEL" -o "$out_file" -- "$abs"; then
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$shard_name" "$out_file" "$abs" "$rel" "$size" "$mtime" >> "$output/manifests/standalone_files.manifest.tsv"
        ok "Created $shard_name"
        [[ "$DELETE_ORIGINALS" == "yes" ]] && rm -f -- "$abs"
        return 0
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$abs" "$rel" "$size" "$mtime" "standalone_compression_failed" >> "$output/manifests/errors.tsv"
    warn "Compression failed: $rel"
    return 1
}

compress_path() {
    local input="$1" output="$2"
    require_runtime_tools
    input="$(realpath -- "$input")"; output="$(realpath -m -- "$output")"
    [[ -e "$input" ]] || die "Input does not exist: $input"
    confirm_delete_originals
    prepare_output "$output"

    local run_id started_at known_index
    started_at="$(date +%s)"; run_id="run_${started_at}_$$"; known_index="$(mktemp)"
    trap "rm -f -- '$known_index'" EXIT
    if [[ "$SKIP_KNOWN" == "yes" ]]; then build_known_index "$output" "$known_index"; else : > "$known_index"; fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$started_at" "$input" "$output" "$ZSTD_LEVEL" "$THREADS" "$SHARD_TARGET_BYTES" "$BIG_FILE_MIN_BYTES" "$DELETE_ORIGINALS" "$SKIP_KNOWN" >> "$output/manifests/runs.tsv"

    banner
    info "Run ID: $run_id"
    info "Input: $input"
    info "Output: $output"
    info "Mode: append-only manifests, append-only shard IDs"
    info "Skip already-known files: $SKIP_KNOWN"
    info "Grouped shard target: $(human_bytes "$SHARD_TARGET_BYTES")"

    local group_id standalone_id shard_size current_group_name current_group_tmp current_group_out
    group_id="$(next_numeric_id "$output/shards" "group")"; standalone_id="$(next_numeric_id "$output/shards" "standalone")"
    shard_size=0; current_group_name=""; current_group_tmp=""; current_group_out=""
    local total_seen=0 small_count=0 big_count=0 ignored_count=0 skipped_count=0 error_count=0

    start_group_shard() {
        local candidate
        while true; do
            candidate="$(printf '%06d' "$group_id")"
            current_group_name="group_${candidate}.zst"
            current_group_tmp="$output/tmp/group_${candidate}.${run_id}.raw"
            current_group_out="$output/shards/$current_group_name"
            [[ ! -e "$current_group_out" && ! -e "$current_group_tmp" ]] && break
            group_id="$((group_id + 1))"
        done
        : > "$current_group_tmp"
        shard_size=0
        work "Started grouped shard: $current_group_name"
    }

    finalize_group_shard() {
        [[ -z "$current_group_tmp" ]] && return 0
        if (( shard_size <= 0 )) || [[ ! -s "$current_group_tmp" ]]; then
            rm -f -- "$current_group_tmp"
            current_group_name=""; current_group_tmp=""; current_group_out=""; shard_size=0
            return 0
        fi
        [[ -e "$current_group_out" ]] && die "Refusing to overwrite existing grouped shard: $current_group_out"
        work "Compressing grouped shard: $current_group_name raw=$(human_bytes "$(file_size "$current_group_tmp")")"
        if zstd -q -T"$THREADS" -"$ZSTD_LEVEL" -o "$current_group_out" -- "$current_group_tmp"; then
            rm -f -- "$current_group_tmp"
            ok "Created $current_group_name"
            group_id="$((group_id + 1))"
            current_group_name=""; current_group_tmp=""; current_group_out=""; shard_size=0
            return 0
        fi
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$current_group_tmp" "$current_group_name" "0" "0" "group_compression_failed" >> "$output/manifests/errors.tsv"
        warn "Failed to compress grouped shard: $current_group_tmp"
        return 1
    }

    process_one_file() {
        local file="$1" abs rel size mtime
        [[ -f "$file" ]] || return 0
        total_seen="$((total_seen + 1))"
        abs="$(realpath -- "$file")"; rel="$(relative_path "$input" "$abs")"
        if ! size="$(file_size "$abs" 2>/dev/null)" || ! mtime="$(file_mtime "$abs" 2>/dev/null)"; then
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$abs" "$rel" "0" "0" "stat_failed" >> "$output/manifests/errors.tsv"
            error_count="$((error_count + 1))"; warn "Could not stat file: $rel"; return 0
        fi
        if is_compressed_file "$abs"; then
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$abs" "$rel" "$size" "$mtime" "compressed_extension" >> "$output/manifests/ignored_compressed_files.tsv"
            ignored_count="$((ignored_count + 1))"; warn "Ignoring compressed input: $rel"; return 0
        fi
        if [[ "$SKIP_KNOWN" == "yes" ]] && known_file "$known_index" "$abs" "$size" "$mtime"; then
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$abs" "$rel" "$size" "$mtime" "already_in_manifest" >> "$output/manifests/skipped_known_files.tsv"
            skipped_count="$((skipped_count + 1))"; return 0
        fi
        if (( size >= BIG_FILE_MIN_BYTES )); then
            if compress_standalone_file "$input" "$output" "$run_id" "$abs" "$standalone_id"; then
                big_count="$((big_count + 1))"; printf '%s\t%s\t%s\n' "$abs" "$size" "$mtime" >> "$known_index"
            else
                error_count="$((error_count + 1))"
            fi
            standalone_id="$((standalone_id + 1))"; return 0
        fi
        [[ -z "$current_group_tmp" ]] && start_group_shard
        if (( shard_size > 0 && shard_size + size > SHARD_TARGET_BYTES )); then finalize_group_shard || error_count="$((error_count + 1))"; start_group_shard; fi
        work "Grouping <- $rel ($(human_bytes "$size")) into $current_group_name"
        if append_file_to_group_raw "$input" "$output" "$run_id" "$abs" "$current_group_tmp" "$current_group_name" "$current_group_out"; then
            shard_size="$((shard_size + size))"; small_count="$((small_count + 1))"; printf '%s\t%s\t%s\n' "$abs" "$size" "$mtime" >> "$known_index"
        else
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$run_id" "$abs" "$rel" "$size" "$mtime" "append_failed" >> "$output/manifests/errors.tsv"
            error_count="$((error_count + 1))"; warn "Failed to append file: $rel"
        fi
    }

    if [[ -f "$input" ]]; then
        process_one_file "$input"
    elif [[ -d "$input" ]]; then
        while IFS= read -r -d '' file; do process_one_file "$file"; done < <(find "$input" -type f -print0)
    else
        die "Input is neither a file nor a directory: $input"
    fi

    finalize_group_shard || error_count="$((error_count + 1))"
    rmdir "$output/tmp" 2>/dev/null || true

    cat > "$output/last_run_summary.txt" <<SUMMARY
run_id=$run_id
input=$input
output=$output
shards_dir=$output/shards
zstd_level=$ZSTD_LEVEL
threads=$THREADS
shard_target_bytes=$SHARD_TARGET_BYTES
big_file_min_bytes=$BIG_FILE_MIN_BYTES
total_files_seen=$total_seen
small_files_grouped=$small_count
big_files_compressed_standalone=$big_count
compressed_files_ignored=$ignored_count
known_files_skipped=$skipped_count
errors=$error_count
delete_originals=$DELETE_ORIGINALS
skip_known=$SKIP_KNOWN
SUMMARY

    ok "Compression run finished."
    ok "New run summary: $output/last_run_summary.txt"
    ok "Manifests were appended under: $output/manifests"
    ok "Search target for all data: $output"
    (( skipped_count > 0 )) && info "Skipped already-known files: $skipped_count"
    (( ignored_count > 0 )) && warn "Ignored compressed files: $ignored_count"
    (( error_count > 0 )) && warn "Errors: $error_count; see $output/manifests/errors.tsv"
}

search_one_zst() {
    local pattern="$1" file="$2"
    local rg_color rg_line_number_arg rg_case_arg rg_heading_arg

    if [[ "$QUIET_MODE" == "yes" ]]; then
        rg_color="never"
        rg_line_number_arg="--no-line-number"
        rg_heading_arg="--no-heading"
    else
        rg_color="always"
        rg_line_number_arg="-n"
        rg_heading_arg="--heading"
        printf '%b\n' "${CYAN}${BOLD}[SCAN]${NC} $file" >&2
    fi

    [[ "$CASE_INSENSITIVE" == "yes" ]] && rg_case_arg="-i" || rg_case_arg="-s"

    zstdcat -T"$THREADS" -- "$file" 2>/dev/null | rg \
        "$rg_case_arg" \
        "$rg_line_number_arg" \
        "$rg_heading_arg" \
        --color="$rg_color" \
        --max-columns=4096 \
        --max-columns-preview \
        "${RG_EXTRA_ARGS[@]}" \
        -- "$pattern" || true
}

search_path() {
    local pattern="$1" target="$2" scan_root
    local search_started search_finished elapsed_seconds
    local shard_count=0 total_shard_bytes=0 file size

    require_runtime_tools
    [[ -e "$target" ]] || die "Search path does not exist: $target"

    banner
    info "Pattern: $pattern"
    info "Target: $target"

    search_started="$(date +%s)"

    if [[ -f "$target" ]]; then
        [[ "$target" == *.zst ]] || die "Search file is not .zst: $target"
        shard_count=1
        if [[ "$QUIET_MODE" != "yes" ]]; then
            total_shard_bytes="$(file_size "$target" 2>/dev/null || printf '0')"
        fi
        search_one_zst "$pattern" "$target"
    else
        scan_root="$target"
        [[ -d "$target/shards" ]] && scan_root="$target/shards"

        # Collect shard list up front so we can count and size without mixing
        # those stat calls into the hot search loop.
        local -a shards=()
        while IFS= read -r -d '' file; do
            shards+=("$file")
        done < <(find "$scan_root" -type f -name '*.zst' -print0 | sort -z)

        shard_count="${#shards[@]}"

        # Compute total bytes only when the summary will actually be printed;
        # in quiet mode we skip every stat call in the loop entirely.
        if [[ "$QUIET_MODE" != "yes" ]]; then
            for file in "${shards[@]}"; do
                size="$(file_size "$file" 2>/dev/null || printf '0')"
                total_shard_bytes="$((total_shard_bytes + size))"
            done
        fi

        # Parallel shard search via a token-based semaphore.
        # Each slot in the pipe acts as a token: a worker acquires one before
        # spawning and returns it (via EXIT trap) when done, bounding concurrency
        # to exactly $THREADS workers at any time.
        if (( THREADS > 1 && shard_count > 1 )); then
            local _sem_fifo _sem_fd
            _sem_fifo="$(mktemp -u)"
            mkfifo "$_sem_fifo"
            exec {_sem_fd}<>"$_sem_fifo"
            rm -f "$_sem_fifo"
            # Pre-fill the semaphore with THREADS tokens.
            for (( i = 0; i < THREADS; i++ )); do printf x >&$_sem_fd; done

            for file in "${shards[@]}"; do
                read -r -n1 -u"$_sem_fd"          # acquire token
                (
                    trap "printf x >&$_sem_fd" EXIT  # always release, even on error
                    search_one_zst "$pattern" "$file"
                ) &
            done
            wait
            exec {_sem_fd}>&-
        else
            for file in "${shards[@]}"; do
                search_one_zst "$pattern" "$file"
            done
        fi
    fi

    search_finished="$(date +%s)"
    elapsed_seconds="$((search_finished - search_started))"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        ok "Search finished."
        info "Search time: ${elapsed_seconds}s"
        info "Shards searched: $shard_count"
        info "Compressed data searched: $(human_bytes "$total_shard_bytes") ($total_shard_bytes bytes)"
    fi
}

main() {
    [[ $# -ge 1 ]] || { help_menu; exit 1; }
    local cmd="$1"; shift
    case "$cmd" in
        install)
            [[ $# -eq 0 ]] || die "install takes no arguments"; install_tools ;;
        compress)
            [[ $# -ge 2 ]] || { help_menu; exit 1; }
            local input="$1" output="$2"; shift 2
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --delete-originals) DELETE_ORIGINALS="yes" ;;
                    --no-skip-known) SKIP_KNOWN="no" ;;
                    --quiet|--quit) QUIET_MODE="yes" ;;
                    *) die "Unknown compress option: $1" ;;
                esac
                shift
            done
            compress_path "$input" "$output" ;;
        search)
            [[ $# -ge 2 ]] || { help_menu; exit 1; }
            local pattern="$1" target="$2"; shift 2
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --quiet|--quit) QUIET_MODE="yes" ;;
                    --fixed-string|-F) RG_EXTRA_ARGS+=("--fixed-strings") ;;
                    --case-sensitive|-S) CASE_INSENSITIVE="no" ;;
                    *) die "Unknown search option: $1" ;;
                esac
                shift
            done
            search_path "$pattern" "$target" ;;
        -h|--help|help) help_menu ;;
        *) help_menu; exit 1 ;;
    esac
}

main "$@"
