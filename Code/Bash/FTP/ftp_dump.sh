#!/usr/bin/env bash

# Show usage
usage() {
    cat <<EOF
Usage: $0 [options] <file>

Options:
  -v, --verbose   Show progress while testing credentials and downloading
  -s, --size      Calculate and display total data volume for valid FTPs (requires lftp)
  --download      Mirror all content of valid FTPs to ./ftp_downloads/<domain>/ (requires lftp)

The input file should contain lines in the format:
  ftp://URL username password

Examples:
  $0 -v ftp_list.txt
  $0 -s ftp_list.txt
  $0 --download ftp_list.txt
  $0 -v --download ftp_list.txt
EOF
    exit 1
}

# Parse arguments
verbose=0
show_size=0
do_download=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) verbose=1; shift ;;
        -s|--size)    show_size=1; shift ;;
        --download)   do_download=1; shift ;;
        -h|--help)    usage ;;
        --)           shift; break ;;
        -*)           echo "Unknown option: $1" >&2; usage ;;
        *)            break ;;
    esac
done

if [[ $# -ne 1 ]]; then
    usage
fi

file="$1"
if [[ ! -f "$file" ]]; then
    echo "Error: File '$file' not found." >&2
    exit 1
fi

# Check required tools
if ! command -v curl &> /dev/null; then
    echo "Error: curl is not installed. Please install it." >&2
    exit 1
fi

if [[ $show_size -eq 1 || $do_download -eq 1 ]] && ! command -v lftp &> /dev/null; then
    echo "Error: lftp is not installed. Please install it (sudo apt install lftp)." >&2
    exit 1
fi

# Color definitions
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Base directory for downloads
DOWNLOAD_BASE="./ftp_downloads"
mkdir -p "$DOWNLOAD_BASE"

# Function to escape single quotes in a string for use in shell
quote_single() {
    echo "$1" | sed "s/'/'\\\\''/g"
}

# Read the file line by line
while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim leading/trailing whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    
    # Skip empty lines
    [[ -z "$line" ]] && continue

    # Extract fields (URL, username, password)
    url=$(echo "$line" | awk '{print $1}')
    user=$(echo "$line" | awk '{print $2}')
    pass=$(echo "$line" | awk '{print $3}')

    # Ensure all fields are present
    if [[ -z "$url" || -z "$user" || -z "$pass" ]]; then
        if [[ $verbose -eq 1 ]]; then
            echo "Skipping malformed line: $line" >&2
        fi
        continue
    fi

    # Extract host from URL (strip protocol and path)
    host=$(echo "$url" | sed -E 's|^ftp://([^/]*).*|\1|')
    if [[ -z "$host" ]]; then
        if [[ $verbose -eq 1 ]]; then
            echo "Skipping invalid URL: $url" >&2
        fi
        continue
    fi

    if [[ $verbose -eq 1 ]]; then
        echo "Testing: ftp://$host (user: $user)" >&2
    fi

    # Test connection using curl
    if curl -s -u "$user:$pass" "ftp://$host/" --list-only --connect-timeout 5 --max-time 10 >/dev/null 2>&1; then
        # Valid credentials
        if [[ $show_size -eq 1 ]]; then
            # Escape single quotes for lftp command
            user_escaped=$(quote_single "$user")
            pass_escaped=$(quote_single "$pass")
            size_bytes=$(lftp -c "open -u '$user_escaped','$pass_escaped' '$host'; du -sb" 2>/dev/null | awk '{print $1}')
            if [[ -n "$size_bytes" && "$size_bytes" =~ ^[0-9]+$ ]]; then
                if (( size_bytes >= 1073741824 )); then
                    size_human=$(echo "scale=2; $size_bytes / 1073741824" | bc)GB
                elif (( size_bytes >= 1048576 )); then
                    size_human=$(echo "scale=2; $size_bytes / 1048576" | bc)MB
                elif (( size_bytes >= 1024 )); then
                    size_human=$(echo "scale=2; $size_bytes / 1024" | bc)KB
                else
                    size_human="${size_bytes}B"
                fi
                printf "${GREEN}VALID${NC} %s (size: %s)\n" "$line" "$size_human"
            else
                printf "${GREEN}VALID${NC} %s (size: unavailable)\n" "$line"
            fi
        else
            printf "${GREEN}VALID${NC} %s\n" "$line"
        fi

        # Download if requested
        if [[ $do_download -eq 1 ]]; then
            # Create domain-specific directory (sanitize hostname)
            # Replace any '/' or ':' with '_' to be safe, but host should be clean
            safe_host=$(echo "$host" | sed 's/[:\/]/_/g')
            target_dir="$DOWNLOAD_BASE/$safe_host"
            mkdir -p "$target_dir"
            
            if [[ $verbose -eq 1 ]]; then
                echo "Downloading ftp://$host to $target_dir ..." >&2
                lftp_verbose="--verbose=3"
            else
                lftp_verbose="--verbose=0"
            fi
            
            # Escape credentials
            user_escaped=$(quote_single "$user")
            pass_escaped=$(quote_single "$pass")
            
            # Run mirror: continue (-c), parallel connections (--parallel=2), no overwrite newer files
            lftp -c "open -u '$user_escaped','$pass_escaped' '$host'; mirror -c --parallel=2 $lftp_verbose / '$target_dir'"
            
            if [[ $? -eq 0 ]]; then
                if [[ $verbose -eq 1 ]]; then
                    echo "Finished downloading $host" >&2
                fi
            else
                echo "Warning: Download failed for $host" >&2
            fi
        fi
    else
        if [[ $verbose -eq 1 ]]; then
            echo "  -> Invalid" >&2
        fi
    fi
done < "$file"
