#!/usr/bin/env bash
#
# token.sh - manage proxy access tokens.
#
# Commands:
#   add     --user NAME --days N [--rate R] [--burst B] [--max-conns M]
#   revoke  --user NAME
#   list
#
# Examples:
#   sudo ./token.sh add --user alice --days 30 --rate 10 --burst 20 --max-conns 50
#   sudo ./token.sh revoke --user alice
#   sudo ./token.sh list
#
# Notes:
#   * The plaintext token is printed exactly once, at creation. Only its
#     SHA-256 hash is ever stored on disk. Save it somewhere safe.
#   * add/revoke hot-reload the running proxy (SIGHUP) so changes take effect
#     within milliseconds without dropping other users' live connections.
#
set -euo pipefail

BIN=/opt/proxyd/proxyd
CONF_DIR=/etc/proxyd
CONFIG="$CONF_DIR/config.json"
RUN_DIR=/run/proxyd
PIDFILE="$RUN_DIR/proxyd.pid"

die() { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "token.sh must be run as root (use sudo)."
[ -x "$BIN" ] || die "$BIN not found. Run ./install.sh first."
[ $# -ge 1 ] || { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

CMD="$1"; shift

reload_proxy() {
  # Prefer systemd's reload; fall back to signalling the pidfile directly.
  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] \
     && systemctl is-active --quiet proxyd 2>/dev/null; then
    systemctl reload proxyd 2>/dev/null && { echo "(proxy reloaded)"; return; }
  fi
  if [ -f "$PIDFILE" ]; then
    kill -HUP "$(cat "$PIDFILE")" 2>/dev/null && echo "(proxy reloaded)" || \
      echo "(proxy not running; changes apply on next start)"
  else
    echo "(proxy not running; changes apply on next start)"
  fi
}

case "$CMD" in
  add)
    # Pass all flags straight through to the binary's token subcommand.
    OUT="$("$BIN" token add --config "$CONFIG" "$@")" || die "token add failed"
    echo
    echo "Token created. Store it now - it will NOT be shown again:"
    echo
    echo "    $OUT"
    echo
    reload_proxy
    ;;
  revoke)
    "$BIN" token revoke --config "$CONFIG" "$@" || die "token revoke failed"
    reload_proxy
    ;;
  list)
    "$BIN" token list --config "$CONFIG" "$@"
    ;;
  -h|--help|help)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *)
    die "unknown command: $CMD (use add | revoke | list)"
    ;;
esac
