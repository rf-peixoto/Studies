#!/usr/bin/env bash
#
# start.sh - configure launch flags and (re)start proxyd.
#
# Examples:
#   sudo ./start.sh                              # start with current config
#   sudo ./start.sh --http 8080 --socks 1080     # set listen ports
#   sudo ./start.sh --log-all                    # also log dropped requests
#   sudo ./start.sh --http 8080 --foreground     # run in this terminal (no systemd)
#   sudo ./start.sh --stop                        # stop the service
#   sudo ./start.sh --status                      # show status
#
set -euo pipefail

BIN=/opt/proxyd/proxyd
CONF_DIR=/etc/proxyd
ENV_FILE="$CONF_DIR/proxyd.env"
CONFIG="$CONF_DIR/config.json"

HTTP_ADDR=""
SOCKS_ADDR=""
LOG_FILE=""
LOG_ALL=0
FOREGROUND=0
ACTION="start"

die() { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --http)        HTTP_ADDR=":$2"; shift 2 ;;
    --http-addr)   HTTP_ADDR="$2";  shift 2 ;;
    --socks)       SOCKS_ADDR=":$2"; shift 2 ;;
    --socks-addr)  SOCKS_ADDR="$2"; shift 2 ;;
    --log)         LOG_FILE="$2";   shift 2 ;;
    --log-all)     LOG_ALL=1;       shift ;;
    --foreground|-f) FOREGROUND=1;  shift ;;
    --stop)        ACTION="stop";   shift ;;
    --restart)     ACTION="restart"; shift ;;
    --status)      ACTION="status"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown flag: $1" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "start.sh must be run as root (use sudo)."
[ -x "$BIN" ] || die "$BIN not found. Run ./install.sh first."

# Assemble launch args that override config.json.
ARGS=""
[ -n "$HTTP_ADDR" ]  && ARGS="$ARGS --http-addr $HTTP_ADDR"
[ -n "$SOCKS_ADDR" ] && ARGS="$ARGS --socks-addr $SOCKS_ADDR"
[ -n "$LOG_FILE" ]   && ARGS="$ARGS --log $LOG_FILE"
[ "$LOG_ALL" -eq 1 ] && ARGS="$ARGS --log-all"
ARGS="$(echo "$ARGS" | sed 's/^ *//')"

has_systemd() { command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; }

case "$ACTION" in
  status)
    if has_systemd; then systemctl status proxyd --no-pager || true; fi
    exit 0 ;;
  stop)
    if has_systemd; then systemctl stop proxyd; echo "stopped."; else pkill -f "$BIN serve" || true; fi
    exit 0 ;;
esac

if [ "$FOREGROUND" -eq 1 ]; then
  echo "Running proxyd in foreground (Ctrl-C to stop)..."
  # shellcheck disable=SC2086
  exec "$BIN" serve --config "$CONFIG" $ARGS
fi

# Persist the launch args for systemd and (re)start.
printf 'PROXYD_ARGS=%s\n' "$ARGS" > "$ENV_FILE"
chmod 0640 "$ENV_FILE"; chown proxyd:proxyd "$ENV_FILE" 2>/dev/null || true

if has_systemd; then
  systemctl restart proxyd
  sleep 0.4
  systemctl --no-pager --lines=0 status proxyd || true
  echo "proxyd started via systemd. Args: ${ARGS:-<from config.json>}"
else
  die "systemd not detected. Use --foreground, or start $BIN under your init system."
fi
