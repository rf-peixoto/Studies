#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# CONFIG
# ============================================================

ZSTD_LEVEL=10
THREADS="$(nproc)"

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
  $0 compress <input_path> <output_path>
  $0 search <pattern> <path>

Commands:

  install
      Install zstd, zstdcat and ripgrep.

  compress
      Recursively compress all files from input_path into output_path.

      Example:
        $0 compress /data/raw /data/compressed

  search
      Case-insensitive ripgrep search against:
        - .zst files
        - directories containing .zst files

      Example:
        $0 search "gmail.com" /data/compressed

EOF
}

# ============================================================
# INSTALL
# ============================================================

install_tools() {
    echo -e "${YELLOW}[+] Installing zstd and ripgrep...${NC}"

    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y zstd ripgrep

    elif command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y zstd ripgrep

    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm zstd ripgrep

    else
        echo -e "${RED}[ERROR] Unsupported package manager.${NC}"
        exit 1
    fi

    echo -e "${GREEN}[OK] Installation finished.${NC}"

    command -v zstd >/dev/null || {
        echo -e "${RED}[ERROR] zstd missing.${NC}"
        exit 1
    }

    command -v zstdcat >/dev/null || {
        echo -e "${RED}[ERROR] zstdcat missing.${NC}"
        exit 1
    }

    command -v rg >/dev/null || {
        echo -e "${RED}[ERROR] ripgrep missing.${NC}"
        exit 1
    }

    echo -e "${GREEN}[OK] All tools available.${NC}"
}

# ============================================================
# COMPRESS
# ============================================================

compress_recursive() {
    local input="$1"
    local output="$2"

    input="$(realpath "$input")"
    output="$(realpath -m "$output")"

    if [[ ! -d "$input" ]]; then
        echo -e "${RED}[ERROR] Input path is not a directory.${NC}"
        exit 1
    fi

    mkdir -p "$output"

    echo -e "${YELLOW}[+] Input : $input${NC}"
    echo -e "${YELLOW}[+] Output: $output${NC}"
    echo -e "${YELLOW}[+] Threads: $THREADS${NC}"
    echo -e "${YELLOW}[+] ZSTD level: $ZSTD_LEVEL${NC}"

    export input
    export output
    export ZSTD_LEVEL
    export THREADS

    find "$input" -type f -print0 | while IFS= read -r -d '' file; do

        rel="${file#$input/}"
        out_file="$output/$rel.zst"

        mkdir -p "$(dirname "$out_file")"

        echo -e "${GREEN}[COMPRESS]${NC} $rel"

        zstd \
            -q \
            -T"$THREADS" \
            -"${ZSTD_LEVEL}" \
            --rm \
            -f \
            "$file" \
            -o "$out_file"

    done

    echo -e "${GREEN}[OK] Compression finished.${NC}"
}

# ============================================================
# SEARCH
# ============================================================

search_zstd() {
    local pattern="$1"
    local target="$2"

    if [[ ! -e "$target" ]]; then
        echo -e "${RED}[ERROR] Path does not exist.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}[+] Searching for:${NC} $pattern"
    echo -e "${YELLOW}[+] Target:${NC} $target"

    if [[ -f "$target" ]]; then

        if [[ "$target" != *.zst ]]; then
            echo -e "${RED}[ERROR] File is not .zst${NC}"
            exit 1
        fi

        echo -e "${GREEN}[FILE]${NC} $target"

        zstdcat -- "$target" | \
            rg \
                -i \
                -n \
                --color=always \
                --max-columns=4096 \
                --max-columns-preview \
                -- "$pattern"

        exit 0
    fi

    find "$target" -type f -name '*.zst' -print0 | \
    while IFS= read -r -d '' file; do

        echo -e "${GREEN}[SEARCH]${NC} $file"

        zstdcat -- "$file" 2>/dev/null | \
            rg \
                -i \
                -n \
                --color=always \
                --max-columns=4096 \
                --max-columns-preview \
                --label "$file" \
                -- "$pattern" || true

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
            if [[ $# -ne 3 ]]; then
                help_menu
                exit 1
            fi

            compress_recursive "$2" "$3"
            ;;

        search)
            if [[ $# -ne 3 ]]; then
                help_menu
                exit 1
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
