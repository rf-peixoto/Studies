#!/usr/bin/env bash

# Show usage
usage() {
    echo "Usage: $0 [-v|--verbose] <file>"
    echo "  -v, --verbose   Show progress while testing credentials"
    exit 1
}

# Parse arguments
verbose=0
if [[ $# -eq 0 ]]; then
    usage
fi

if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    verbose=1
    shift
fi

if [[ $# -ne 1 ]]; then
    usage
fi

file="$1"
if [[ ! -f "$file" ]]; then
    echo "Error: File '$file' not found." >&2
    exit 1
fi

# Check if curl is installed
if ! command -v curl &> /dev/null; then
    echo "Error: curl is not installed. Please install it." >&2
    exit 1
fi

# Color definitions
GREEN='\033[0;32m'
NC='\033[0m' # No Color

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
    # Example: ftp://example.com/path -> example.com
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

    # Test connection to the FTP server using curl
    # Use the root directory '/' to avoid path‑related failures
    if curl -s -u "$user:$pass" "ftp://$host/" --list-only --connect-timeout 5 --max-time 10 >/dev/null 2>&1; then
        # Valid credentials: print original line with green VALID tag
        printf "${GREEN}VALID${NC} %s\n" "$line"
    else
        if [[ $verbose -eq 1 ]]; then
            echo "  -> Invalid" >&2
        fi
    fi
done < "$file"
