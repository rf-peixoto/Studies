#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# CONFIG
# ============================================================

TOOL_VERSION="2.0"

ZSTD_LEVEL=10
THREADS="$(nproc)"

# Small files are grouped until the raw shard reaches ~8 GB.
SHARD_TARGET_BYTES=$((8 * 1024 * 1024 * 1024))

# Files >= 8 GB are compressed alone.
BIG_FILE_MIN_BYTES=$SHARD_TARGET_BYTES

DELETE_ORIGINALS="no"
QUIET_MODE="no"
FRESH_MODE="no"   # --fresh: wipe output dir and start over

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
    CYAN="$(printf '\033[0;36m')"
    BOLD="$(printf '\033[1m')"
    DIM="$(printf '\033[2m')"
    NC="$(printf '\033[0m')"
    BGREEN="$(printf '\033[1;32m')"
    BMAGENTA="$(printf '\033[1;35m')"
    BCYAN="$(printf '\033[1;36m')"
else
    RED="" GREEN="" YELLOW="" CYAN=""
    BOLD="" DIM="" NC=""
    BGREEN="" BMAGENTA="" BCYAN=""
fi

# ============================================================
# SPINNER
# ============================================================

SPINNER_PID=""

_spinner_loop() {
    local msg="${1:-working...}"
    local -a frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    trap 'exit 0' TERM INT
    while true; do
        printf '\r%b%s%b  %s  ' "${BMAGENTA}" "${frames[$i]}" "${NC}" "$msg" >&2
        (( i = (i + 1) % 10 )) || true
        sleep 0.08
    done
}

spinner_start() {
    # No spinner in quiet mode or when stderr is not a tty.
    [[ "$QUIET_MODE" == "yes" || ! -t 2 ]] && return 0
    _spinner_loop "$*" &
    SPINNER_PID=$!
}

spinner_stop() {
    if [[ -n "${SPINNER_PID:-}" ]]; then
        kill "${SPINNER_PID}" 2>/dev/null || true
        wait "${SPINNER_PID}" 2>/dev/null || true   # suppresses "Killed" job notice
        SPINNER_PID=""
    fi
    printf '\r\033[2K' >&2   # erase the spinner line
}

_cleanup() { spinner_stop; }
trap '_cleanup' EXIT

# ============================================================
# UI
# ============================================================

banner() {
    [[ "$QUIET_MODE" == "yes" ]] && return 0
    printf '\n' >&2
    printf '%b%s%b\n' "${BCYAN}${BOLD}" \
        "  ╔══════════════════════════════════════════════════════════════════╗" "${NC}" >&2
    printf '%b  ║  %b░▒▓ BLACK HOLE ▓▒░%b  raw-text compression engine  %bv%-8s%b  ║%b\n' \
        "${BCYAN}${BOLD}" "${BMAGENTA}" "${BCYAN}${BOLD}" "${DIM}${CYAN}" \
        "$TOOL_VERSION" "${BCYAN}${BOLD}" "${NC}" >&2
    printf '%b  ║  %b%-64s%b║%b\n' \
        "${BCYAN}${BOLD}" "${DIM}${CYAN}" \
        "zstd · ripgrep · sharded · incremental · append-safe" \
        "${BCYAN}${BOLD}" "${NC}" >&2
    printf '%b%s%b\n' "${BCYAN}${BOLD}" \
        "  ╚══════════════════════════════════════════════════════════════════╝" "${NC}" >&2
    printf '\n' >&2
}

human_bytes() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || printf '%s bytes' "$1"
}

die() {
    spinner_stop
    printf '%b[✗ FATAL]%b %s\n' "${RED}${BOLD}" "${NC}" "$*" >&2
    exit 1
}

warn() {
    printf '%b[⚠  WARN]%b %s\n' "${YELLOW}${BOLD}" "${NC}" "$*" >&2
}

ok() {
    printf '%b[✓    OK]%b %s\n' "${BGREEN}${BOLD}" "${NC}" "$*" >&2
}

info() {
    printf '%b[·  INFO]%b %s\n' "${BCYAN}${BOLD}" "${NC}" "$*" >&2
}

work() {
    [[ "$QUIET_MODE" == "yes" ]] && return 0
    printf '%b[⚙  WORK]%b %s\n' "${BMAGENTA}${BOLD}" "${NC}" "$*" >&2
}

hr() {
    [[ "$QUIET_MODE" == "yes" ]] && return 0
    printf '%b  %s%b\n' "${DIM}${CYAN}" \
        "──────────────────────────────────────────────────────────────" "${NC}" >&2
}

section() {
    [[ "$QUIET_MODE" == "yes" ]] && return 0
    printf '\n%b  ▸ %s%b\n\n' "${BOLD}${CYAN}" "$*" "${NC}" >&2
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

safe_name() {
    printf '%s' "$1" | sed 's#/#__#g; s#[^A-Za-z0-9._-]#_#g'
}

is_compressed_file() {
    local path_lc
    path_lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    local ext
    for ext in "${COMPRESSED_EXTENSIONS[@]}"; do
        [[ "$path_lc" == *"$ext" ]] && return 0
    done
    return 1
}

# ============================================================
# HELP
# ============================================================

help_menu() {
    banner
    cat <<EOF
${BOLD}Usage:${NC}
  $0 install
  $0 compress <input_file_or_dir> <output_dir> [--delete-originals] [--fresh]
  $0 search   <pattern> <output_dir_or_shard> [--quiet]

${BOLD}Commands:${NC}

  ${BGREEN}install${NC}
      Install required tools: zstd, ripgrep, coreutils, findutils.

  ${BGREEN}compress${NC}
      Compress a file or directory into a shard pool.

      ${YELLOW}Incremental by default:${NC}
        Running compress on the same <output_dir> multiple times is safe.
        New shards are appended; existing shards are never touched.
        Group and standalone shard IDs always resume from the last run.
        Manifests receive a timestamped session header on each run.

      ${YELLOW}Behaviour:${NC}
        · already-compressed inputs are skipped
        · small files (< 8 GB raw) are grouped into ~8 GB shards
        · big files (≥ 8 GB raw) get their own standalone shard
        · all .zst output lands in <output_dir>/shards/

      ${YELLOW}Options:${NC}
        --delete-originals   Delete source files after successful compression
                             (off by default; requires interactive confirmation)
        --fresh              Wipe <output_dir> before compressing
                             (requires interactive confirmation)

      ${YELLOW}Examples:${NC}
        $0 compress /data/batch1 /data/pool
        $0 compress /data/batch2 /data/pool          # safely appended
        $0 compress /data/batch1 /data/pool --fresh  # start over

  ${BGREEN}search${NC}
      Case-insensitive ripgrep search across all .zst shards.
      Automatically resolves <output_dir>/shards/ when it exists.

      ${YELLOW}Options:${NC}
        --quiet   Suppress progress headers; emit only match lines

      ${YELLOW}Examples:${NC}
        $0 search "gmail.com" /data/pool
        $0 search "gmail.com" /data/pool/shards/group_000001.zst
        $0 search "secret"    /data/pool --quiet

${BOLD}Current defaults:${NC}
  zstd level          ${ZSTD_LEVEL}
  threads             ${THREADS}
  grouped shard size  $(human_bytes "$SHARD_TARGET_BYTES")
  big-file threshold  $(human_bytes "$BIG_FILE_MIN_BYTES")

EOF
}

# ============================================================
# INSTALL
# ============================================================

install_tools() {
    banner
    section "Installing dependencies"

    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y zstd ripgrep coreutils findutils
    elif command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y zstd ripgrep coreutils findutils
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm zstd ripgrep coreutils findutils
    else
        die "No supported package manager found. Install manually: zstd ripgrep coreutils findutils"
    fi

    local cmd
    for cmd in zstd zstdcat rg find realpath stat numfmt sed tr cat; do
        need_cmd "$cmd"
    done

    ok "All dependencies installed and verified."
}

# ============================================================
# SAFETY PROMPTS
# ============================================================

confirm_delete_originals() {
    [[ "$DELETE_ORIGINALS" != "yes" ]] && return 0
    printf '\n' >&2
    printf '%b[!] DANGER:%b --delete-originals will permanently remove source files.\n' \
        "${RED}${BOLD}" "${NC}" >&2
    printf '\n' >&2
    local answer
    read -r -p "$(printf '%b' "${RED}${BOLD}")    Type DELETE to confirm: $(printf '%b' "${NC}")" \
        answer </dev/tty
    [[ "$answer" == "DELETE" ]] || die "Deletion not confirmed. Aborting."
}

confirm_fresh() {
    # $1 = output path shown in the warning
    printf '\n' >&2
    printf '%b[!] DANGER:%b --fresh will permanently delete: %s\n' \
        "${RED}${BOLD}" "${NC}" "$1" >&2
    printf '\n' >&2
    local answer
    read -r -p "$(printf '%b' "${RED}${BOLD}")    Type FRESH to confirm: $(printf '%b' "${NC}")" \
        answer </dev/tty
    [[ "$answer" == "FRESH" ]] || die "Fresh mode not confirmed. Aborting."
}

# ============================================================
# OUTPUT DIRECTORY SETUP
# ============================================================

# BUG FIX (original): prepare_output used `: >` which truncated every manifest
# on each invocation — destroying all records from prior runs and making
# incremental append impossible.
#
# FIX: manifests are never truncated. Each run opens with an append of a
# timestamped session-header line so runs are clearly delineated. Files are
# created if absent, untouched otherwise.

prepare_output() {
    local output="$1"

    # --fresh: wipe and start clean (confirmed by caller)
    if [[ "$FRESH_MODE" == "yes" ]]; then
        confirm_fresh "$output"
        rm -rf -- "$output"
        info "Output directory wiped for fresh run."
    fi

    mkdir -p "$output/shards" "$output/manifests" "$output/tmp"

    local session_ts
    session_ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local hdr="# ── SESSION ${session_ts} ──────────────────────────────────────────────"

    # Append a session header to each manifest (creates file if not present).
    local f
    for f in \
        "$output/manifests/grouped_shards.manifest.tsv" \
        "$output/manifests/standalone_files.manifest.tsv" \
        "$output/manifests/ignored_compressed_files.tsv" \
        "$output/manifests/errors.tsv"
    do
        printf '%s\n' "$hdr" >> "$f"
    done
}

# ============================================================
# COMPRESSION HELPERS
# ============================================================

compress_standalone_file() {
    local input_root="$1"
    local output="$2"
    local file="$3"
    local sid="$4"

    local rel size base out_file

    if [[ -d "$input_root" ]]; then
        rel="${file#${input_root}/}"
    else
        rel="$(basename "$file")"
    fi

    size="$(stat -c%s "$file")"
    base="$(safe_name "$rel")"
    out_file="$output/shards/standalone_$(printf '%06d' "$sid")_${base}.zst"

    # Hard guard — next_available_standalone_id should have prevented this.
    [[ -e "$out_file" ]] && die "Refusing to overwrite existing standalone shard: $out_file"

    work "Standalone: $rel  ($(human_bytes "$size"))"
    spinner_start "Compressing $(basename "$out_file") …"

    # BUG FIX (original): used -f (force overwrite) even though the guard above
    # already aborts on collision. The flags were contradictory; -f removed.
    if zstd -q -T"$THREADS" -"${ZSTD_LEVEL}" "$file" -o "$out_file"; then
        spinner_stop
        local zst_size
        zst_size="$(stat -c%s "$out_file")"
        printf '%s\t%s\t%s\n' "$rel" "$size" "$out_file" \
            >> "$output/manifests/standalone_files.manifest.tsv"
        ok "$(basename "$out_file")  raw=$(human_bytes "$size") → zst=$(human_bytes "$zst_size")"
        [[ "$DELETE_ORIGINALS" == "yes" ]] && rm -f -- "$file"
    else
        spinner_stop
        printf '%s\t%s\t%s\n' "$rel" "$size" "compression_failed" \
            >> "$output/manifests/errors.tsv"
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

    local rel size

    if [[ -d "$input_root" ]]; then
        rel="${file#${input_root}/}"
    else
        rel="$(basename "$file")"
    fi

    size="$(stat -c%s "$file")"

    {
        printf '\n===== FILE: %s SIZE: %s =====\n' "$rel" "$size"
        cat -- "$file"
        printf '\n===== END FILE: %s =====\n' "$rel"
    } >> "$tmp_file"

    printf '%s\t%s\t%s\n' "$shard_name" "$rel" "$size" \
        >> "$output/manifests/grouped_shards.manifest.tsv"

    [[ "$DELETE_ORIGINALS" == "yes" ]] && rm -f -- "$file"
    return 0
}

# ============================================================
# MAIN COMPRESS
# ============================================================

compress_path() {
    local input="$1"
    local output="$2"

    input="$(realpath "$input")"
    output="$(realpath -m "$output")"

    [[ -e "$input" ]] || die "Input does not exist: $input"

    confirm_delete_originals
    prepare_output "$output"

    banner
    section "Compression session"
    info "Input:             $input"
    info "Output:            $output"
    info "ZSTD level:        $ZSTD_LEVEL"
    info "Threads:           $THREADS"
    info "Shard target:      $(human_bytes "$SHARD_TARGET_BYTES")"
    info "Big-file min:      $(human_bytes "$BIG_FILE_MIN_BYTES")"
    info "Delete originals:  $DELETE_ORIGINALS"
    info "Mode:              $( [[ "$FRESH_MODE" == "yes" ]] && printf 'fresh (wiped)' || printf 'incremental (append)' )"
    hr

    # ── Counters ─────────────────────────────────────────────────────────────
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

    # ── next_available_group_id ───────────────────────────────────────────────
    # Advances group_id until both the .raw temp file and the .zst output are
    # absent, then sets current_group_{name,tmp,out}.
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
            (( group_id += 1 )) || true
        done
    }

    # ── next_available_standalone_id ─────────────────────────────────────────
    # BUG FIX (original): standalone_id was always reset to 1 at the start of
    # compress_path. On a second run over the same output dir the first IDs
    # were already taken, causing a hard die() on the existence check.
    #
    # FIX: mirror the group-ID pattern — scan shards/ for existing
    # standalone_NNNNNN_* files and advance until a free slot is found.
    next_available_standalone_id() {
        local candidate found
        while true; do
            candidate="$(printf '%06d' "$standalone_id")"
            found=0
            while IFS= read -r -d '' _; do
                found=1
                break
            done < <(find "$output/shards" -maxdepth 1 \
                         -name "standalone_${candidate}_*.zst" -print0 2>/dev/null)
            (( found == 0 )) && return 0
            (( standalone_id += 1 )) || true
        done
    }

    # Prime both counters from whatever shards already exist in the output dir.
    # BUG FIX (original): next_available_group_id was only called lazily when
    # the first group shard opened — not at startup. On a second run this meant
    # group_id started at 1 again and relied on the die() guard rather than
    # proactively finding the correct starting point.
    next_available_group_id
    next_available_standalone_id

    # ── Group shard lifecycle ─────────────────────────────────────────────────

    start_group_shard() {
        next_available_group_id
        [[ -e "$current_group_tmp" || -e "$current_group_out" ]] && \
            die "Internal shard naming collision: $current_group_name"
        : > "$current_group_tmp"
        shard_size=0
        work "Opened shard: $current_group_name"
    }

    finalize_group_shard() {
        [[ -n "${current_group_tmp:-}" && -n "${current_group_out:-}" ]] || return 0

        if (( shard_size <= 0 )) || [[ ! -s "$current_group_tmp" ]]; then
            rm -f -- "$current_group_tmp"
            current_group_name="" current_group_tmp="" current_group_out=""
            shard_size=0
            return 0
        fi

        [[ -e "$current_group_out" ]] && \
            die "Refusing to overwrite existing grouped shard: $current_group_out"

        local raw_sz
        raw_sz="$(stat -c%s "$current_group_tmp")"
        spinner_start "Compressing ${current_group_name}  (raw $(human_bytes "$raw_sz")) …"

        # Do NOT pass -f here — an existing output must remain a hard failure.
        if zstd -q -T"$THREADS" -"${ZSTD_LEVEL}" "$current_group_tmp" -o "$current_group_out"; then
            spinner_stop
            rm -f -- "$current_group_tmp"
            local zst_sz
            zst_sz="$(stat -c%s "$current_group_out")"
            ok "$(basename "$current_group_out")  raw=$(human_bytes "$raw_sz") → zst=$(human_bytes "$zst_sz")"
        else
            spinner_stop
            printf '%s\t%s\n' "$current_group_tmp" "group_compression_failed" \
                >> "$output/manifests/errors.tsv"
            warn "Failed to compress grouped shard: $current_group_tmp"
            current_group_name="" current_group_tmp="" current_group_out=""
            shard_size=0
            return 1
        fi

        (( group_id += 1 )) || true
        current_group_name="" current_group_tmp="" current_group_out=""
        shard_size=0
    }

    # ── Per-file handler ──────────────────────────────────────────────────────

    process_one_file() {
        local file="$1"
        local size rel

        (( total_seen += 1 )) || true
        [[ -f "$file" ]] || return 0

        # Skip already-compressed inputs
        if is_compressed_file "$file"; then
            if [[ -d "$input" ]]; then rel="${file#${input}/}"; else rel="$(basename "$file")"; fi
            warn "Skipping already-compressed: $rel"
            printf '%s\n' "$rel" >> "$output/manifests/ignored_compressed_files.tsv"
            (( ignored_count += 1 )) || true
            return 0
        fi

        # Stat
        if ! size="$(stat -c%s "$file" 2>/dev/null)"; then
            warn "Cannot stat: $file"
            printf '%s\t%s\n' "$file" "stat_failed" >> "$output/manifests/errors.tsv"
            (( error_count += 1 )) || true
            return 0
        fi

        # Big file → its own standalone shard
        if (( size >= BIG_FILE_MIN_BYTES )); then
            next_available_standalone_id
            if compress_standalone_file "$input" "$output" "$file" "$standalone_id"; then
                (( standalone_id += 1 )) || true
                next_available_standalone_id   # pre-prime for the next call
                (( big_count += 1 )) || true
            else
                (( error_count += 1 )) || true
            fi
            return 0
        fi

        # Small file → grouped shard
        [[ -n "$current_group_tmp" ]] || start_group_shard

        # If adding this file would exceed the target, seal the current shard
        # and open a fresh one. This is the critical shard-boundary path.
        if (( shard_size > 0 && shard_size + size > SHARD_TARGET_BYTES )); then
            if ! finalize_group_shard; then
                (( error_count += 1 )) || true
            fi
            start_group_shard
        fi

        if [[ -d "$input" ]]; then rel="${file#${input}/}"; else rel="$(basename "$file")"; fi

        work "Grouping: $rel  ($(human_bytes "$size")) → $current_group_name"

        if append_file_to_group_shard \
                "$input" "$output" "$file" "$current_group_tmp" "$current_group_name"; then
            (( shard_size += size )) || true
            (( small_count += 1 )) || true
        else
            warn "Failed to append: $file"
            printf '%s\t%s\n' "$file" "append_failed" >> "$output/manifests/errors.tsv"
            (( error_count += 1 )) || true
        fi
    }

    # ── Walk input ────────────────────────────────────────────────────────────
    if [[ -f "$input" ]]; then
        process_one_file "$input"
    elif [[ -d "$input" ]]; then
        # sort -z gives deterministic, reproducible ordering across runs
        while IFS= read -r -d '' file; do
            process_one_file "$file"
        done < <(find "$input" -type f -print0 | sort -z)
    else
        die "Input is neither a file nor a directory: $input"
    fi

    # Finalize the last partially-filled grouped shard.
    if ! finalize_group_shard; then
        (( error_count += 1 )) || true
    fi

    rmdir "$output/tmp" 2>/dev/null || true

    # ── Session summary (appended, never overwritten) ─────────────────────────
    # BUG FIX (original): used `cat > file` which wiped the summary each run.
    {
        printf '# session: %s\n'              "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'input=%s\n'                   "$input"
        printf 'zstd_level=%d\n'              "$ZSTD_LEVEL"
        printf 'threads=%d\n'                 "$THREADS"
        printf 'shard_target=%s\n'            "$(human_bytes "$SHARD_TARGET_BYTES")"
        printf 'big_file_min=%s\n'            "$(human_bytes "$BIG_FILE_MIN_BYTES")"
        printf 'total_files_seen=%d\n'        "$total_seen"
        printf 'small_files_grouped=%d\n'     "$small_count"
        printf 'big_files_standalone=%d\n'    "$big_count"
        printf 'compressed_inputs_skipped=%d\n' "$ignored_count"
        printf 'errors=%d\n'                  "$error_count"
        printf 'delete_originals=%s\n'        "$DELETE_ORIGINALS"
        printf '\n'
    } >> "$output/compression_summary.txt"

    section "Session complete"
    ok "Files seen:         $total_seen"
    ok "Small → grouped:    $small_count"
    ok "Big → standalone:   $big_count"
    ok "Compressed skipped: $ignored_count"
    ok "Errors:             $error_count"
    hr
    ok "Shards:    $output/shards"
    ok "Manifests: $output/manifests"
    ok "Summary:   $output/compression_summary.txt"
    (( error_count > 0 )) && warn "Error log: $output/manifests/errors.tsv" || true
}

# ============================================================
# SEARCH
# ============================================================

# Global match accumulator — must live outside search_one_zst so the
# while-loop caller can read it after the loop body runs.
_TOTAL_MATCHES=0

search_one_zst() {
    local pattern="$1"
    local file="$2"

    [[ "$QUIET_MODE" != "yes" ]] && \
        printf '%b  ▶ %s%b\n' "${DIM}${CYAN}" "$(basename "$file")" "${NC}" >&2

    # Write matches to a temp file so we can both stream them AND count lines
    # without a subshell breaking the _TOTAL_MATCHES accumulator.
    local tmp_out
    tmp_out="$(mktemp)"

    zstdcat -- "$file" 2>/dev/null \
        | rg -i -n --color=always --max-columns=4096 --max-columns-preview \
              -- "$pattern" > "$tmp_out" 2>/dev/null \
        || true   # rg exits 1 on no match; not an error

    local n
    n="$(wc -l < "$tmp_out")"
    cat -- "$tmp_out"
    rm -f -- "$tmp_out"

    if [[ "$QUIET_MODE" != "yes" && "$n" -gt 0 ]]; then
        printf '%b  ✓ %d match(es)%b\n' "${BGREEN}${BOLD}" "$n" "${NC}" >&2
    fi

    (( _TOTAL_MATCHES += n )) || true
}

search_path() {
    local pattern="$1"
    local target="$2"

    [[ -e "$target" ]] || die "Search target does not exist: $target"

    if [[ "$QUIET_MODE" != "yes" ]]; then
        banner
        section "Search"
        info "Pattern : ${BOLD}${YELLOW}${pattern}${NC}"
        info "Target  : $target"
    fi

    local -a shard_files=()

    if [[ -f "$target" ]]; then
        [[ "$target" == *.zst ]] || die "Single-file target must be a .zst file: $target"
        shard_files=("$target")
    else
        # Automatically resolve <output_dir>/shards/ when it exists so the user
        # can point at the top-level output directory without any subpath.
        local search_root="$target"
        [[ -d "$target/shards" ]] && search_root="$target/shards"

        while IFS= read -r -d '' f; do
            shard_files+=("$f")
        done < <(find "$search_root" -type f -name '*.zst' -print0 | sort -z)
    fi

    if [[ ${#shard_files[@]} -eq 0 ]]; then
        warn "No .zst shards found under: $target"
        return 0
    fi

    if [[ "$QUIET_MODE" != "yes" ]]; then
        info "Shards  : ${#shard_files[@]}"
        hr
        printf '\n' >&2
    fi

    _TOTAL_MATCHES=0
    local total_shards="${#shard_files[@]}"
    local i=0

    for file in "${shard_files[@]}"; do
        (( i += 1 )) || true
        [[ "$QUIET_MODE" != "yes" ]] && \
            printf '%b  [%d/%d]%b\n' "${DIM}${CYAN}" "$i" "$total_shards" "${NC}" >&2
        search_one_zst "$pattern" "$file"
    done

    if [[ "$QUIET_MODE" != "yes" ]]; then
        printf '\n' >&2
        hr
        section "Search complete"
        info "Shards searched : $total_shards"
        if (( _TOTAL_MATCHES > 0 )); then
            info "Total matches   : ${BGREEN}${BOLD}${_TOTAL_MATCHES}${NC}"
        else
            info "Total matches   : ${YELLOW}0 — no results${NC}"
        fi
    fi
}

# ============================================================
# MAIN
# ============================================================

main() {
    [[ $# -ge 1 ]] || { help_menu; exit 1; }

    local cmd="$1"
    shift

    case "$cmd" in
        install)
            install_tools
            ;;

        compress)
            [[ $# -ge 2 ]] || { help_menu; exit 1; }
            local _in="$1" _out="$2"
            shift 2
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --delete-originals) DELETE_ORIGINALS="yes" ;;
                    --fresh)            FRESH_MODE="yes" ;;
                    *) die "Unknown option: $1" ;;
                esac
                shift
            done
            compress_path "$_in" "$_out"
            ;;

        search)
            [[ $# -ge 2 ]] || { help_menu; exit 1; }
            local _pat="$1" _tgt="$2"
            shift 2
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --quiet) QUIET_MODE="yes" ;;
                    *) die "Unknown option: $1" ;;
                esac
                shift
            done
            search_path "$_pat" "$_tgt"
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
