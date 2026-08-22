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

# shellcheck disable=SC2034  # kept for external/reference use
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

# Search tuning (all optional; sensible defaults keep old behavior).
LITERAL="no"          # -F / --fixed-string
WORD="no"             # -w / --word
COUNT="no"            # -c / --count
FILES_ONLY="no"       # -l / --files-with-matches
CONTEXT=""            # -C N / --context N (fast engine only)
COLOR_MODE="auto"     # --color auto|always|never
LOCATE="no"           # --locate: map hits back to original files
SEARCH_JOBS="$THREADS"  # -j / --jobs: parallel workers

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
    {
        printf '%b\n' "${CYAN}${BOLD}"
        printf '%s\n' '┌────────────────────────────────────────────────────────────┐'
        printf '%s\n' '│                       BLACK HOLE                           │'
        printf '%s\n' '│         append-only compressed raw-text search             │'
        printf '%s\n' '└────────────────────────────────────────────────────────────┘'
        printf '%b\n' "${NC}"
    } >&2
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
    for cmd in zstd zstdcat rg find realpath stat numfmt sed tr cat awk sort date mkdir basename mktemp grep xargs; do
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
  $0 compress <input_file_or_dir> <output_dir> [--delete-originals] [--no-skip-known] [--quiet]
  $0 search  <pattern> <pool_or_shard> [search options]
  $0 verify  <pool_or_shard> [--quiet]
  $0 list    <pool> [name-substring] [--quiet]

${BOLD}Search options:${NC}
  -F, --fixed-string      Treat pattern as a literal string, not a regex
  -w, --word              Match whole words only
  -S, --case-sensitive    Case-sensitive (default is case-insensitive)
  -c, --count             Print a count of matches per shard
  -l, --files-with-matches  Print only shard names that contain a match
  -C, --context N         Show N lines of context (fast mode)
      --locate            Attribute each hit to its ORIGINAL file + line number
      --color MODE        auto (default), always, or never
  -j, --jobs N            Parallel workers (default: $THREADS)
  -q, --quiet             Suppress banner/logs (plain, script-friendly output)
      -- <rg args...>     Pass any extra flags straight to ripgrep

${BOLD}The binary-safe guarantee:${NC}
  Search always runs ripgrep with -a/--text, so shards that contain NUL bytes
  (an originally-binary file grouped with text) are searched fully instead of
  collapsing to "binary file matches" and dropping real hits.

${BOLD}Incremental behavior (unchanged):${NC}
  - Existing manifests are not rewritten; existing shards are never overwritten.
  - New runs create new shard IDs after the highest existing ID.
  - Searching a pool covers all old and new .zst shards.
  - Files already seen (same absolute path, size and mtime) are skipped.

${BOLD}Examples:${NC}
  $0 compress /data/raw_batch_01 /data/blackhole
  $0 compress /data/raw_batch_02 /data/blackhole
  $0 search 'gmail.com' /data/blackhole
  $0 search 'literal[.]domain' /data/blackhole --fixed-string
  $0 search 'password' /data/blackhole --locate          # which file was it in?
  $0 verify /data/blackhole
  $0 list   /data/blackhole config                        # files whose path contains "config"

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
    # shellcheck disable=SC2064  # expand $known_index now: the local is gone by EXIT time
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


# ------------------------------------------------------------
# Search
# ------------------------------------------------------------
# The core correctness fix lives here: every ripgrep invocation passes
# -a/--text so shards that happen to contain NUL bytes (an originally-binary
# file grouped in with text) are searched fully instead of collapsing to
# "binary file matches" and silently dropping real hits.

# Resolve --color=auto against whether stdout is a TTY.
resolve_color() {
    case "$COLOR_MODE" in
        always) printf 'always' ;;
        never)  printf 'never' ;;
        *)      if [[ -t 1 ]]; then printf 'always'; else printf 'never'; fi ;;
    esac
}

# Collect *.zst shards for a target into the named array (sorted, stable).
# Target may be a pool dir (uses its shards/ subdir), a bare dir of shards,
# or a single .zst file.
collect_shards() {
    local target="$1" __outname="$2" scan_root f
    local -a __found=()
    if [[ -f "$target" ]]; then
        [[ "$target" == *.zst ]] || die "Search file is not .zst: $target"
        __found+=("$target")
    else
        scan_root="$target"
        [[ -d "$target/shards" ]] && scan_root="$target/shards"
        while IFS= read -r -d '' f; do __found+=("$f"); done \
            < <(find "$scan_root" -type f -name '*.zst' -print0 2>/dev/null | sort -z)
    fi
    eval "$__outname=(\"\${__found[@]}\")"
}

# Turn a user pattern into a regex fragment honoring --fixed-string / --word.
# Only --locate needs this: it must OR the pattern together with the file
# markers in a single ripgrep pass, so it cannot delegate -F/-w to ripgrep the
# way the fast engine does.
build_regex() {
    local p="$1"
    if [[ "${LITERAL:-no}" == "yes" ]]; then
        # Wrap each character in a bracket class so nothing stays special.
        p="$(printf '%s' "$p" | sed 's/[^^]/[&]/g; s/\^/\\^/g')"
    fi
    if [[ "${WORD:-no}" == "yes" ]]; then
        p="\\b(?:$p)\\b"
    fi
    printf '%s' "$p"
}

# Exact begin-marker regex (must mirror the compressor's printf).
BH_BEGIN_RE='^===== BLACK_HOLE_FILE_BEGIN path=(.*) size=[0-9]+ mtime=[0-9]+ =====$'

# --------- fast engine: one rg -z -a pass, native parallel decompression -----
search_fast() {
    local pattern="$1" target="$2" color="$3"
    local -a args=(-z -a --no-messages --color="$color"
                   --max-columns=4096 --max-columns-preview --no-ignore)
    if [[ "$CASE_INSENSITIVE" == "yes" ]]; then args+=(-i); else args+=(-s); fi
    [[ "$LITERAL"    == "yes" ]] && args+=(-F)
    [[ "$WORD"       == "yes" ]] && args+=(-w)
    [[ "$COUNT"      == "yes" ]] && args+=(--count-matches)
    [[ "$FILES_ONLY" == "yes" ]] && args+=(-l)
    [[ -n "$CONTEXT"          ]] && args+=(-C "$CONTEXT")
    if [[ "$QUIET_MODE" == "yes" ]]; then args+=(--no-heading -n); else args+=(--heading -n); fi
    (( SEARCH_JOBS > 0 )) && args+=(--threads "$SEARCH_JOBS")

    if [[ -f "$target" ]]; then
        rg "${args[@]}" "${RG_EXTRA_ARGS[@]}" -e "$pattern" -- "$target"
    else
        local scan_root="$target"
        [[ -d "$target/shards" ]] && scan_root="$target/shards"
        # cd into the shard dir so printed paths are shard-relative, and glob
        # to *.zst so nothing else in the tree is scanned.
        ( cd "$scan_root" && rg "${args[@]}" -g '*.zst' "${RG_EXTRA_ARGS[@]}" -e "$pattern" -- . )
    fi
}

# --------- locate engine: attribute each hit to its original file ------------
# Decompress one shard once; rg emits begin-markers and matches with GLOBAL
# line numbers; awk maps each match to its source file + file-local line.
locate_one_shard() {
    local pattern="$1" shard="$2"
    local shard_base rx case_flag
    shard_base="$(basename -- "$shard")"
    rx="$(build_regex "$pattern")"
    if [[ "$CASE_INSENSITIVE" == "yes" ]]; then case_flag='-i'; else case_flag='-s'; fi

    zstdcat -T"$THREADS" -- "$shard" 2>/dev/null \
      | rg -a --no-messages "$case_flag" -n --no-heading --color=never \
            -e "$BH_BEGIN_RE" -e "$rx" \
      | awk -v shard="$shard_base" -v flag="${BH_MATCH_FLAG:-}" \
            -v C="${CYAN:-}" -v B="${BOLD:-}" -v D="${DIM:-}" -v N="${NC:-}" '
        {
            gl = $0 + 0                       # leading integer = rg line number
            rest = $0; sub(/^[0-9]+:/, "", rest)
            if (rest ~ /^===== BLACK_HOLE_FILE_BEGIN path=/) {
                cur = rest
                sub(/^===== BLACK_HOLE_FILE_BEGIN path=/, "", cur)
                sub(/ size=[0-9]+ mtime=[0-9]+ =====$/, "", cur)
                base = gl; have = 1
                next
            }
            if (rest ~ /^===== BLACK_HOLE_FILE_END path=/) next
            if (have) { loc = gl - base; rel = cur }
            else      { loc = gl;         rel = "(whole file)" }
            hit = 1
            printf "%s%s%s %s|%s %s%s%s:%s%d%s: %s\n", \
                   C, shard, N, D, N, B, rel, N, B, loc, N, rest
        }
        END { if (hit && flag != "") { print "" >> flag; close(flag) } }
      '
}

search_locate() {
    local pattern="$1" target="$2"
    local -a shards; collect_shards "$target" shards
    (( ${#shards[@]} )) || { warn "No .zst shards found under: $target"; return 1; }

    # A flag file lets parallel workers report "at least one match" so we can
    # return a grep-like exit status without buffering their output.
    local flag; flag="$(mktemp)"; export BH_MATCH_FLAG="$flag"
    export CYAN BOLD DIM NC CASE_INSENSITIVE THREADS LITERAL WORD BH_BEGIN_RE
    export -f locate_one_shard build_regex die

    printf '%s\0' "${shards[@]}" \
      | xargs -0 -P "$SEARCH_JOBS" -I{} bash -c 'locate_one_shard "$0" "$1"' "$pattern" {}

    local rc=1; [[ -s "$flag" ]] && rc=0
    rm -f -- "$flag"; unset BH_MATCH_FLAG
    return "$rc"
}

search_path() {
    local pattern="$1" target="$2" color rc=0
    local search_started search_finished elapsed_seconds
    local shard_count=0 total_shard_bytes=0 file size

    require_runtime_tools
    [[ -e "$target" ]] || die "Search path does not exist: $target"
    if [[ -f "$target" && "$target" != *.zst ]]; then
        die "Search file is not .zst: $target (point me at a shard or a shards/ directory)"
    fi

    color="$(resolve_color)"
    banner
    info "Pattern: $pattern"
    info "Target: $target"
    [[ "$LOCATE" == "yes" ]] && info "Mode: locate (attributing hits to source files)"

    search_started="$(date +%s)"

    # Collect shards up front for the summary (also validates the target).
    local -a shards=(); collect_shards "$target" shards
    shard_count="${#shards[@]}"
    if [[ "$QUIET_MODE" != "yes" ]]; then
        for file in "${shards[@]}"; do
            size="$(file_size "$file" 2>/dev/null || printf '0')"
            total_shard_bytes="$((total_shard_bytes + size))"
        done
    fi

    if [[ "$LOCATE" == "yes" ]]; then
        search_locate "$pattern" "$target" || rc=$?
    else
        search_fast "$pattern" "$target" "$color" || rc=$?
    fi

    search_finished="$(date +%s)"
    elapsed_seconds="$((search_finished - search_started))"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        ok "Search finished."
        info "Search time: ${elapsed_seconds}s"
        info "Shards searched: $shard_count"
        info "Compressed data searched: $(human_bytes "$total_shard_bytes") ($total_shard_bytes bytes)"
    fi

    # grep-like status: 0 = matched, 1 = no match, >1 = ripgrep error.
    return "$rc"
}

# ------------------------------------------------------------
# Verify: integrity-check every shard with `zstd -t`.
# ------------------------------------------------------------
verify_shards() {
    local target="$1"
    require_runtime_tools
    [[ -e "$target" ]] || die "Path does not exist: $target"
    local -a shards; collect_shards "$target" shards
    (( ${#shards[@]} )) || die "No .zst shards found under: $target"

    banner
    info "Verifying ${#shards[@]} shard(s) under: $target"
    local healthy=0 corrupt=0 shard
    for shard in "${shards[@]}"; do
        if zstd -t -q -- "$shard" 2>/dev/null; then
            healthy="$((healthy + 1))"
        else
            corrupt="$((corrupt + 1))"
            printf '%b\n' "${RED}${BOLD}[CORRUPT]${NC} $shard" >&2
        fi
    done
    ok "Healthy shards: $healthy"
    if (( corrupt > 0 )); then
        warn "Corrupt shards: $corrupt"
        return 1
    fi
    ok "All shards passed integrity check."
    return 0
}

# ------------------------------------------------------------
# List: show every original file and which shard holds it, from manifests.
# ------------------------------------------------------------
list_files() {
    local target="$1" filter="${2:-}"
    [[ -e "$target" ]] || die "Path does not exist: $target"
    local mdir="$target/manifests"
    [[ -d "$mdir" ]] || die "No manifests/ directory under: $target (is this a BLACK HOLE pool?)"

    banner
    [[ "$QUIET_MODE" == "yes" ]] || printf '%s\t%s\t%s\t%s\n' "run_id" "shard" "size" "source_rel"
    local m
    for m in "$mdir/grouped_shards.manifest.tsv" "$mdir/standalone_files.manifest.tsv"; do
        [[ -s "$m" ]] || continue
        # cols: run_id shard_name shard_path source_abs source_rel size mtime
        awk -F'\t' -v flt="$filter" '
            NR > 1 && NF >= 7 {
                if (flt == "" || index($5, flt) > 0)
                    printf "%s\t%s\t%s\t%s\n", $1, $2, $6, $5
            }' "$m"
    done
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
                    --quiet|--quit|-q) QUIET_MODE="yes" ;;
                    --fixed-string|-F)  LITERAL="yes" ;;
                    --case-sensitive|-S) CASE_INSENSITIVE="no" ;;
                    --word|-w)          WORD="yes" ;;
                    --count|-c)         COUNT="yes" ;;
                    --files-with-matches|-l) FILES_ONLY="yes" ;;
                    --locate)           LOCATE="yes" ;;
                    --context|-C)       [[ $# -ge 2 ]] || die "$1 requires a value"; CONTEXT="$2"; shift ;;
                    --color)            [[ $# -ge 2 ]] || die "$1 requires a value"; COLOR_MODE="$2"; shift ;;
                    --jobs|-j)          [[ $# -ge 2 ]] || die "$1 requires a value"; SEARCH_JOBS="$2"; shift ;;
                    --)                 shift; RG_EXTRA_ARGS+=("$@"); break ;;
                    *) die "Unknown search option: $1" ;;
                esac
                shift
            done
            search_path "$pattern" "$target" ;;
        verify)
            [[ $# -ge 1 ]] || { help_menu; exit 1; }
            local vtarget=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --quiet|--quit|-q) QUIET_MODE="yes" ;;
                    *) [[ -z "$vtarget" ]] && vtarget="$1" || die "Unexpected argument: $1" ;;
                esac
                shift
            done
            [[ -n "$vtarget" ]] || { help_menu; exit 1; }
            verify_shards "$vtarget" ;;
        list)
            [[ $# -ge 1 ]] || { help_menu; exit 1; }
            local ltarget="" lfilter=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --quiet|--quit|-q) QUIET_MODE="yes" ;;
                    *) if [[ -z "$ltarget" ]]; then ltarget="$1"
                       elif [[ -z "$lfilter" ]]; then lfilter="$1"
                       else die "Unexpected argument: $1"; fi ;;
                esac
                shift
            done
            [[ -n "$ltarget" ]] || { help_menu; exit 1; }
            list_files "$ltarget" "$lfilter" ;;
        -h|--help|help) help_menu ;;
        *) help_menu; exit 1 ;;
    esac
}

main "$@"
