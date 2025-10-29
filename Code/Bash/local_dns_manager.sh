#!/usr/bin/env bash
# setup-mitm-blocker.sh
# Purpose: Install mitmproxy-based small blocking proxy and compose blocklists
# Designed for Debian/Ubuntu (tested). Run as root (sudo).
# Usage: sudo ./setup-mitm-blocker.sh [--no-proxy-env] [--no-ca-install] [--port PORT]
set -euo pipefail

### Configuration - edit if needed
INSTALL_DIR="/opt/mitm-blocker"
BLOCKLIST_DIR="$INSTALL_DIR/blocklists"
SERVICE_NAME="mitm-blocker.service"
MITMPROXY_PORT=8080
MITMPROXY_USER="root"   # for personal lab; change to dedicated user for production
LOG_FILE="/var/log/mitm-blocker.log"
BLOCKLIST_SOURCES=(
  "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"   # StevenBlack unified
  "https://raw.githubusercontent.com/anudeepND/blacklist/master/adservers.txt" # anudeep adservers
  "https://raw.githubusercontent.com/ppfeufer/adguard-filter-list/master/blocklist?raw=true" # combined adguard list
  "https://raw.githubusercontent.com/ProgramComputer/Easylist_hosts/master/hosts" # EasyList hosts mirror
)
# Some convenience default path-patterns that often map to short-video endpoints.
# You can add more patterns to additional_patterns.txt after installation.
DEFAULT_PATH_PATTERNS=(
  "youtubei.googleapis.com.*reel" 
  "youtubei.googleapis.com.*short"
  ".*/reel_watch"
  ".*/shorts"
  ".*/api/v\\d+/reel"
  ".*snssdk.*"     # common TikTok host fragment
  ".*tiktokv.com.*"
  ".*instagram.com.*reels"
  ".*fbcdn.net.*reel"
)

# Command-line switches
NO_PROXY_ENV=0
NO_CA_INSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-proxy-env) NO_PROXY_ENV=1; shift ;;
    --no-ca-install) NO_CA_INSTALL=1; shift ;;
    --port) MITMPROXY_PORT="$2"; shift 2 ;;
    --help|-h) echo "Usage: sudo $0 [--no-proxy-env] [--no-ca-install] [--port PORT]"; exit 0 ;;
    *) echo "Unknown option $1"; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

mkdir -p "$INSTALL_DIR"
mkdir -p "$BLOCKLIST_DIR"
touch "$LOG_FILE"
chown "$MITMPROXY_USER":"$MITMPROXY_USER" "$LOG_FILE" || true

echo "[*] Installing runtime prerequisites..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip ca-certificates curl wget jq
else
  echo "Non-Debian system; ensure python3, pip and ca-certificates are installed manually."
fi

# Create a small venv for mitmproxy to avoid conflicting system packages
VENV_DIR="$INSTALL_DIR/venv"
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install mitmproxy==11.0.0 requests

# Helper: fetch lists and normalize to one-domain-per-line format
echo "[*] Fetching blocklists..."
COMBINED_HOSTS="$BLOCKLIST_DIR/combined-hosts.txt"
> "$COMBINED_HOSTS"

for url in "${BLOCKLIST_SOURCES[@]}"; do
  echo "  - $url"
  # attempt simple fetch; some sources have query ?raw=true that curl handles
  tmpf="$(mktemp)"
  if ! curl -fsSL "$url" -o "$tmpf"; then
    echo "    (warning) failed to fetch $url; skipping"
    rm -f "$tmpf"
    continue
  fi
  # Normalize: extract hostnames from hosts-style or one-per-line lists
  # Remove comments, blank lines, IPv4 mappings at start, and keep host names
  awk '
    BEGIN{FS=OFS=" "}
    {
      # trim windows CR
      gsub("\r","")
      if ($0 ~ /^#/ || $0 ~ /^[[:space:]]*$/) next
      # hosts file lines like "0.0.0.0 domain" or "127.0.0.1 domain"
      if ($1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) { print $2; next }
      # some lists are one domain per line already
      print $1
    }' "$tmpf" >> "$COMBINED_HOSTS"
  rm -f "$tmpf"
done

# Deduplicate, sanitize (allow letters, numbers, dot, dash, underscore)
echo "[*] Sanitizing combined blocklist..."
awk '{print tolower($0)}' "$COMBINED_HOSTS" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | grep -E '^[a-z0-9._-]+$' | sort -u > "$BLOCKLIST_DIR/hosts-clean.txt"

# Create defaults for path patterns
PATTERNS_FILE="$BLOCKLIST_DIR/path-patterns.txt"
> "$PATTERNS_FILE"
for p in "${DEFAULT_PATH_PATTERNS[@]}"; do
  echo "$p" >> "$PATTERNS_FILE"
done

# Create whitelist file (empty)
WHITELIST="$BLOCKLIST_DIR/whitelist.txt"
: > "$WHITELIST"

# Create mitmproxy inline addon: blocker.py
MITM_ADDON="$INSTALL_DIR/blocker.py"
cat > "$MITM_ADDON" <<'PY'
# blocker.py - mitmproxy addon to block hosts and path patterns
from mitmproxy import http, ctx
import re, time, os

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
BLOCK_HOSTS = set()
PATH_PATTERNS = []
WHITELIST = set()
LOGFILE = "/var/log/mitm-blocker.log"

def load_lists():
    hosts_file = os.path.join(BASE_DIR, "blocklists", "hosts-clean.txt")
    patterns_file = os.path.join(BASE_DIR, "blocklists", "path-patterns.txt")
    whitelist_file = os.path.join(BASE_DIR, "blocklists", "whitelist.txt")
    try:
        with open(hosts_file, "r") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                BLOCK_HOSTS.add(line.lower())
    except Exception as e:
        ctx.log.warn(f"Could not load hosts: {e}")

    try:
        with open(patterns_file, "r") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                try:
                    PATH_PATTERNS.append(re.compile(line))
                except re.error:
                    # try convert simple glob to regex
                    p=line.replace("*", ".*")
                    PATH_PATTERNS.append(re.compile(p))
    except Exception as e:
        ctx.log.warn(f"Could not load patterns: {e}")

    try:
        with open(whitelist_file, "r") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                WHITELIST.add(line.lower())
    except Exception as e:
        ctx.log.warn(f"Could not load whitelist: {e}")

def log_block(client_ip, host, url, reason):
    try:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(LOGFILE, "a") as f:
            f.write(f"{timestamp} {client_ip} BLOCK {host} {url} {reason}\n")
    except Exception:
        pass

def request(flow: http.HTTPFlow):
    # host in flow.request.host, url in flow.request.pretty_url
    host = (flow.request.host or "").lower()
    url = flow.request.pretty_url
    peer = flow.client_conn.peername[0] if flow.client_conn and flow.client_conn.peername else "unknown"

    # whitelist precedence
    if host in WHITELIST:
        return

    # exact host block
    if host in BLOCK_HOSTS:
        flow.response = http.HTTPResponse.make(403, b"Blocked by mitm-blocker (host)", {"Content-Type":"text/plain"})
        log_block(peer, host, url, "host")
        return

    # pattern match hosts substring (helpful for cdn shards)
    for h in BLOCK_HOSTS:
        if h and h in host:
            flow.response = http.HTTPResponse.make(403, b"Blocked by mitm-blocker (host-substring)", {"Content-Type":"text/plain"})
            log_block(peer, host, url, "host-substring:"+h)
            return

    # path/url patterns
    for pat in PATH_PATTERNS:
        try:
            if pat.search(url):
                flow.response = http.HTTPResponse.make(403, b"Blocked by mitm-blocker (url-pattern)", {"Content-Type":"text/plain"})
                log_block(peer, host, url, "pattern:"+pat.pattern)
                return
        except Exception:
            continue

addons = []
def start():
    load_lists()
    ctx.log.info(f"mitm-blocker: loaded {len(BLOCK_HOSTS)} hosts, {len(PATH_PATTERNS)} patterns, {len(WHITELIST)} whitelist")
PY

# ensure correct path to addon
# write a tiny launcher wrapper for mitmproxy to use the addon
LAUNCHER="$INSTALL_DIR/run-mitm-blocker.sh"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# wrapper to run mitmproxy with the blocker addon
BASE="$INSTALL_DIR"
VENV="$BASE/venv"
# shellcheck disable=SC1091
source "\$VENV/bin/activate"
exec mitmproxy -p ${MITMPROXY_PORT} -s "${INSTALL_DIR}/blocker.py" --set flow_detail=0 --set termlog_verbosity=info
EOF
chmod +x "$LAUNCHER"

# create a systemd service
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Local mitmproxy blocker service
After=network.target

[Service]
Type=simple
User=root
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=$LAUNCHER
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

echo "[*] Reloading systemd and enabling service..."
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

# Install mitmproxy CA into system trust store (Debian/Ubuntu method)
if [[ $NO_CA_INSTALL -eq 0 ]]; then
  echo "[*] Generating / exporting mitmproxy root certificate..."
  # run mitmproxy once to ensure certs exist
  "$LAUNCHER" &
  MP_PID=$!
  sleep 2
  # mitmproxy stores certs under ~/.mitmproxy for the user running it (root here)
  mkdir -p /root/.mitmproxy
  # give it a moment
  sleep 1
  # stop process
  kill "$MP_PID" || true
  sleep 1
  # copy cert
  if [[ -f /root/.mitmproxy/mitmproxy-ca.pem ]]; then
    cp -f /root/.mitmproxy/mitmproxy-ca.pem /usr/local/share/ca-certificates/mitmproxy-ca.crt
    update-ca-certificates || true
    echo "[*] Installed mitmproxy CA to system trust store (/usr/local/share/ca-certificates/) - you must install this CA on other client devices you want intercepted."
  else
    echo "Warning: mitmproxy CA not found under /root/.mitmproxy. You may need to run mitmproxy once as the intended user and export the certificate manually."
  fi
else
  echo "[*] Skipping CA install as requested (--no-ca-install)"
fi

# Optionally set system-wide proxy env in /etc/environment
if [[ $NO_PROXY_ENV -eq 0 ]]; then
  echo "[*] Writing proxy environment to /etc/environment (HTTP_PROXY/HTTPS_PROXY). Backup first."
  cp -a /etc/environment /etc/environment.mitm-blocker.bak || true
  # Remove existing entries for http(s)_proxy
  grep -v -i '^http_proxy\|^https_proxy\|^HTTP_PROXY\|^HTTPS_PROXY' /etc/environment > /etc/environment.tmp || true
  echo "HTTP_PROXY=\"http://127.0.0.1:${MITMPROXY_PORT}/\"" >> /etc/environment.tmp
  echo "HTTPS_PROXY=\"http://127.0.0.1:${MITMPROXY_PORT}/\"" >> /etc/environment.tmp
  mv /etc/environment.tmp /etc/environment
  echo "[*] Wrote /etc/environment — you may need to log out/in for GUI apps to pick this up, or configure NetworkManager to use the proxy."
else
  echo "[*] Skipping proxy environment step (--no-proxy-env)."
fi

# Create a helper update script for refreshing blocklists later
UPDATE_SCRIPT="$INSTALL_DIR/mitm-blocker-update.sh"
cat > "$UPDATE_SCRIPT" <<'UPD'
#!/usr/bin/env bash
set -euo pipefail
BASE="$(dirname "$(readlink -f "$0")")"
BLOCKDIR="$BASE/blocklists"
COMBINED="$BLOCKDIR/combined-hosts.txt"
> "$COMBINED"
SOURCES=(
  "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
  "https://raw.githubusercontent.com/anudeepND/blacklist/master/adservers.txt"
  "https://raw.githubusercontent.com/ppfeufer/adguard-filter-list/master/blocklist?raw=true"
  "https://raw.githubusercontent.com/ProgramComputer/Easylist_hosts/master/hosts"
)
for url in "${SOURCES[@]}"; do
  tmpf="$(mktemp)"
  if curl -fsSL "$url" -o "$tmpf"; then
    awk '
      BEGIN{FS=OFS=" "}
      {
        gsub("\r","")
        if ($0 ~ /^#/ || $0 ~ /^[[:space:]]*$/) next
        if ($1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) { print $2; next }
        print $1
      }' "$tmpf" >> "$COMBINED"
  fi
  rm -f "$tmpf"
done
awk '{print tolower($0)}' "$COMBINED" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | grep -E '^[a-z0-9._-]+$' | sort -u > "$BLOCKDIR/hosts-clean.txt"
systemctl restart mitm-blocker.service || true
echo "Updated blocklists and restarted service."
UPD
chmod +x "$UPDATE_SCRIPT"

echo "[*] Initial blocklist size: $(wc -l < "$BLOCKLIST_DIR/hosts-clean.txt" || echo 0) entries"
echo "[*] Path patterns: $(wc -l < "$PATTERNS_FILE") entries"

echo "[*] Setup finished. Service status:"
systemctl status "$SERVICE_NAME" --no-pager || true

cat <<EOF

Next steps (manual or automated):
- Install the generated mitmproxy CA on each client you wish to have HTTPS intercepted.
  * On Linux desktops (Debian/Ubuntu): the script attempted to install '/usr/local/share/ca-certificates/mitmproxy-ca.crt'.
  * For mobile devices or browsers, export the cert from /root/.mitmproxy or use the mitmproxy UI (http://mitm.it when proxy is active).

- If you prefer not to set /etc/environment, run with --no-proxy-env and configure per-device proxy settings manually or via NetworkManager:
  Example nmcli (one connection): 
    nmcli connection modify <conn> proxy.method manual \
      proxy.http "http://127.0.0.1:${MITMPROXY_PORT}" proxy.https "http://127.0.0.1:${MITMPROXY_PORT}"
    nmcli connection up <conn>

- Update blocklists manually with:
    sudo $UPDATE_SCRIPT

- Add hosts to whitelist: edit $BLOCKLIST_DIR/whitelist.txt (one host per line), then:
    sudo systemctl restart $SERVICE_NAME

- Add per-path rules: edit $BLOCKLIST_DIR/path-patterns.txt (each line is a regex, or use * as glob) and restart the service.

Security & privacy notes:
- The proxy intercepts TLS; treat the machine and the CA as sensitive.
- Keep backups: /etc/environment.mitm-blocker.bak and systemd service are saved; the update script preserves list sources.

EOF
