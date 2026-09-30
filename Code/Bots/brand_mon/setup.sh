#!/usr/bin/env bash
#
# setup.sh — installs or removes the web mention monitor in this folder.
#
#   ./setup.sh                 create venv, install deps, create folders and config, add the cron job
#   ./setup.sh --time 07:30    same, running every day at 07:30 (server time)
#   ./setup.sh --no-cron       everything except the cron job
#   ./setup.sh --delete        remove the cron job and everything setup/the monitor created
#   ./setup.sh --delete --yes  same, without asking for confirmation
#
# Keep setup.sh next to monitor.py and config.example.json.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
LOG_DIR="$DIR/logs"
CONFIG="$DIR/config.json"
MANIFEST="$DIR/.setup_manifest"
CRON_MARK="# web-mention-monitor:$DIR"

RUN_TIME="08:00"
DELETE=0
ASSUME_YES=0
WITH_CRON=1

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m ✗\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --delete)  DELETE=1 ;;
        --yes|-y)  ASSUME_YES=1 ;;
        --no-cron) WITH_CRON=0 ;;
        --time)    [[ $# -ge 2 ]] || die "--time needs a value like 08:00"; RUN_TIME="$2"; shift ;;
        -h|--help) usage ;;
        *)         die "Unknown option: $1 (see --help)" ;;
    esac
    shift
done

# Records a path (relative to $DIR) that setup created, so --delete removes only those.
remember() {
    grep -qxF "$1" "$MANIFEST" 2>/dev/null || echo "$1" >> "$MANIFEST"
}

current_crontab() { crontab -l 2>/dev/null || true; }

# Rewrites the crontab without our line, then adds $1 if given. Other jobs are kept.
# The current crontab is read fully before anything is written.
write_cron() {
    local others
    others="$(current_crontab | grep -vF "$CRON_MARK" || true)"
    {
        [[ -n "$others" ]] && printf '%s\n' "$others"
        [[ -n "${1:-}" ]] && printf '%s\n' "$1"
        true
    } | crontab -
}

remove_cron() {
    command -v crontab >/dev/null || return 0
    if current_crontab | grep -qF "$CRON_MARK"; then
        write_cron ""
        ok "Removed cron job"
    fi
}

# --------------------------------------------------------------------------- #
# --delete
# --------------------------------------------------------------------------- #
if [[ $DELETE -eq 1 ]]; then
    # What setup created, plus what the monitor itself creates at runtime.
    targets=()
    if [[ -f "$MANIFEST" ]]; then
        while IFS= read -r p; do [[ -n "$p" ]] && targets+=("$p"); done < "$MANIFEST"
    fi
    targets+=("monitor.db" "logs" "debug" ".monitor.lock" "__pycache__")

    existing=()
    for p in "${targets[@]}"; do
        [[ -e "$DIR/$p" ]] && [[ ! " ${existing[*]-} " == *" $p "* ]] && existing+=("$p")
    done

    has_cron=0
    command -v crontab >/dev/null && current_crontab | grep -qF "$CRON_MARK" && has_cron=1

    if [[ ${#existing[@]} -eq 0 && $has_cron -eq 0 && ! -f "$MANIFEST" ]]; then
        ok "Nothing to remove."
        exit 0
    fi

    info "This will remove:"
    [[ $has_cron -eq 1 ]] && echo "    cron job: $(current_crontab | grep -F "$CRON_MARK" | sed "s|  *$CRON_MARK||")"
    for p in "${existing[@]-}"; do [[ -n "$p" ]] && echo "    $DIR/$p"; done
    [[ " ${existing[*]-} " == *" config.json "* ]] && warn "config.json holds your bot token; it will be deleted too."
    echo "    (monitor.py, config.example.json and setup.sh are kept)"

    if [[ $ASSUME_YES -ne 1 ]]; then
        read -r -p "Continue? [y/N] " answer
        [[ "$answer" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }
    fi

    remove_cron
    for p in "${existing[@]-}"; do
        [[ -n "$p" ]] || continue
        rm -rf -- "${DIR:?}/$p"
        ok "Deleted $p"
    done
    rm -f -- "$MANIFEST"
    ok "Uninstalled."
    exit 0
fi

# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #
[[ -f "$DIR/monitor.py" ]] || die "monitor.py not found in $DIR"
[[ "$RUN_TIME" =~ ^([01]?[0-9]|2[0-3]):([0-5][0-9])$ ]] || die "Invalid --time '$RUN_TIME' (use HH:MM)"
HOUR=$((10#${BASH_REMATCH[1]}))
MINUTE=$((10#${BASH_REMATCH[2]}))

command -v python3 >/dev/null || die "python3 is not installed"
PY_OK=$(python3 -c 'import sys; print(int(sys.version_info >= (3, 8)))')
[[ "$PY_OK" == "1" ]] || die "Python 3.8+ is required (found $(python3 --version))"
if [[ $WITH_CRON -eq 1 ]]; then
    command -v crontab >/dev/null || die "crontab not found (install cron, or rerun with --no-cron)"
fi

# 1. Virtual environment
if [[ -x "$VENV/bin/python" ]]; then
    ok "Virtual environment already exists"
else
    info "Creating virtual environment"
    if ! python3 -m venv "$VENV" 2>/tmp/venv_err.$$; then
        cat /tmp/venv_err.$$ >&2; rm -f /tmp/venv_err.$$
        rm -rf "$VENV"
        die "Could not create the venv. On Debian/Ubuntu: sudo apt install python3-venv"
    fi
    rm -f /tmp/venv_err.$$
    remember ".venv"
    ok "Created .venv"
fi

# 2. Dependencies
info "Installing dependencies"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "requests>=2.28"
ok "Installed requests $("$VENV/bin/python" -c 'import requests; print(requests.__version__)')"

# 3. Folders
if [[ ! -d "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR"
    remember "logs"
    ok "Created logs/"
fi

# 4. Config
NEW_CONFIG=0
if [[ -f "$CONFIG" ]]; then
    ok "Keeping existing config.json"
else
    [[ -f "$DIR/config.example.json" ]] || die "config.example.json not found in $DIR"
    cp "$DIR/config.example.json" "$CONFIG"
    remember "config.json"
    NEW_CONFIG=1
    ok "Created config.json from config.example.json"
fi
chmod 600 "$CONFIG"  # it holds the bot token

# 5. Runner used by cron: no overlapping runs, monthly logs kept for 90 days
RUNNER="$DIR/run.sh"
cat > "$RUNNER" <<'EOF'
#!/usr/bin/env bash
# Created by setup.sh — runs the monitor once. Called by cron.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1
mkdir -p logs
LOG="logs/monitor-$(date +%Y-%m).log"
if command -v flock >/dev/null; then
    exec 9>"$DIR/.monitor.lock"
    flock -n 9 || { echo "$(date '+%F %T') previous run still active, skipping" >> "$LOG"; exit 0; }
fi
"$DIR/.venv/bin/python" monitor.py --config config.json "$@" >> "$LOG" 2>&1
status=$?
find logs -name 'monitor-*.log' -mtime +90 -delete
exit $status
EOF
chmod +x "$RUNNER"
remember "run.sh"
ok "Created run.sh"

# 6. Cron job
if [[ $WITH_CRON -eq 1 ]]; then
    LINE="$MINUTE $HOUR * * * '$RUNNER'  $CRON_MARK"
    write_cron "$LINE"
    ok "Cron job set for $(printf '%02d:%02d' "$HOUR" "$MINUTE") every day (server time is now $(date '+%H:%M %Z'))"
fi

# --------------------------------------------------------------------------- #
echo
info "Done. Next steps:"
PY=".venv/bin/python monitor.py --config config.json"
if [[ $NEW_CONFIG -eq 1 ]]; then
    echo "  1. Put your bot token and chat ID in config.json"
else
    echo "  1. (config.json already existed — check it has the 'sources' block from config.example.json)"
fi
echo "  2. cd '$DIR'"
echo "  3. $PY --test-telegram"
echo "  4. $PY --dry-run          # see what it finds, sends nothing"
echo "  5. $PY --init             # mark current results as known, sends nothing"
[[ $WITH_CRON -eq 0 ]] && echo "  (cron skipped: rerun ./setup.sh without --no-cron to add it)"
echo "To uninstall: ./setup.sh --delete"
