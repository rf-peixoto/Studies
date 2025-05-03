#!/bin/sh

# Detect current shell
shell_name="$(ps -p $$ -o comm=)"

echo "Detected shell: $shell_name"

case "$shell_name" in
    bash)
        echo "[*] Shell is Bash"
        # Check HISTCONTROL
        if [ -n "$HISTCONTROL" ]; then
            echo "[+] HISTCONTROL is set to: $HISTCONTROL"
            echo "$HISTCONTROL" | grep -q "ignorespace" && echo "[!] 'ignorespace' is enabled — commands starting with space will not be logged." || echo "[*] 'ignorespace' is not enabled."
        else
            echo "[-] HISTCONTROL is not set."
        fi
        ;;
    zsh)
        echo "[*] Shell is Zsh"
        # Check HIST_IGNORE_SPACE option
        if zsh -c 'setopt' | grep -q 'HIST_IGNORE_SPACE'; then
            echo "[!] HIST_IGNORE_SPACE is enabled — commands starting with space will not be logged."
        else
            echo "[*] HIST_IGNORE_SPACE is not enabled."
        fi
        ;;
    *)
        echo "[!] Unsupported or unknown shell: $shell_name"
        ;;
esac
