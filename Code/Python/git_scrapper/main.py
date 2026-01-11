#!/bin/bash
# quick_git_scan.sh - Quick Git secret scanner

REPO_URL="$1"
OUTPUT_DIR="${2:-scan_results_$(date +%s)}"

echo "[*] Git Secret Scanner"
echo "[*] Repository: $REPO_URL"
echo "[*] Output: $OUTPUT_DIR"

# Create directories
mkdir -p "$OUTPUT_DIR/deleted" "$OUTPUT_DIR/dangling" "$OUTPUT_DIR/results"

# Clone repository
REPO_NAME=$(basename "$REPO_URL" .git)
echo "[*] Cloning repository..."
git clone --depth=50 "$REPO_URL" "$OUTPUT_DIR/repo" 2>/dev/null

cd "$OUTPUT_DIR/repo"

# 1. Extract deleted files
echo "[*] Extracting deleted files..."
git log --all --pretty=format:'%H' | while read commit; do
    parent=$(git log --pretty=format:"%P" -n 1 "$commit" | awk '{print $1}')
    if [ -n "$parent" ]; then
        git diff --name-status "$parent" "$commit" | grep '^D' | while read _ file; do
            if [ -n "$file" ]; then
                safe_name=$(echo "$file" | sed 's/\//_/g')
                git show "$parent:$file" > "../deleted/${commit}_${safe_name}" 2>/dev/null
            fi
        done
    fi
done

# 2. Extract dangling objects
echo "[*] Extracting dangling objects..."
mkdir -p ../dangling
git fsck --unreachable --dangling --no-reflogs --full 2>/dev/null | \
    grep 'unreachable blob' | \
    awk '{print $3}' | \
    while read hash; do
        git cat-file -p "$hash" > "../dangling/$hash.blob" 2>/dev/null
    done

# 3. Simple secret scanning
echo "[*] Scanning for secrets..."
cd ..
find . -type f -size -5M -exec grep -l -E "(AKIA[0-9A-Z]{16}|gh[oprs]_[0-9a-zA-Z]{36}|xox[baprs]-[0-9]{12}|sk_(live|test)_[0-9a-zA-Z]{24}|eyJ[A-Za-z0-9-_=]+\\.eyJ)" {} \; > results/files_with_secrets.txt

# 4. Create summary
echo "[*] Creating summary..."
echo "=== Git Secret Scan Report ===" > results/summary.txt
echo "Repository: $REPO_URL" >> results/summary.txt
echo "Date: $(date)" >> results/summary.txt
echo "" >> results/summary.txt
echo "Files potentially containing secrets:" >> results/summary.txt
cat results/files_with_secrets.txt >> results/summary.txt

echo ""
echo "[+] Scan complete!"
echo "[+] Results saved in: $OUTPUT_DIR"
echo "[+] Check: $OUTPUT_DIR/results/summary.txt"
