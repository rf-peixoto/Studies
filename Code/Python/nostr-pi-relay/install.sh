#!/usr/bin/env bash
# Install the Nostr Pi microrelay. Safe to re-run: keeps your policy.json values
# (adding any new keys) and the relay database. See uninstall.sh to remove it all.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
[[ $(dpkg --print-architecture) == arm64 ]] || { echo 'Only Debian arm64 supported'; exit 1; }
. /etc/os-release
[[ $ID == debian && $VERSION_ID == 13 ]] || { echo 'Requires Debian 13'; exit 1; }
DOMAIN="${1:-}"
[[ $DOMAIN =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ && $DOMAIN == *.* ]] || { echo 'Usage: sudo bash install.sh relay.example.com'; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
# Upstream only publishes amd64 images, so by default the relay is built from the
# official source on this Pi, pinned to a release tag AND its exact commit.
RELAY_REPO="${NOSTR_RELAY_REPO:-https://github.com/scsibug/nostr-rs-relay.git}"
RELAY_REF="${NOSTR_RELAY_REF:-0.10.0}"
RELAY_COMMIT="${NOSTR_RELAY_COMMIT:-b5c1f642e4f4c3b9c54f5d18d66f4c53642076b4}"
# Alternatively use a prebuilt arm64 image you trust (skips the build), e.g.
# NOSTR_RELAY_IMAGE=registry.example/nostr-rs-relay@sha256:...
IMAGE="${NOSTR_RELAY_IMAGE:-}"
REBUILD="${NOSTR_RELAY_REBUILD:-0}"
MARKER='# managed by nostr-pi-relay'

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y podman uidmap slirp4netns passt python3 python3-venv caddy curl ca-certificates git

if ! id nostr >/dev/null 2>&1; then useradd -m -s /bin/bash nostr; fi
if ! id nostrgw >/dev/null 2>&1; then useradd -r -s /usr/sbin/nologin -d /var/lib/nostrgw -m nostrgw; fi
UID_N=$(id -u nostr)
as_nostr() { runuser -u nostr -- env XDG_RUNTIME_DIR="/run/user/$UID_N" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$UID_N/bus" "$@"; }

# Lingering starts the nostr user's systemd instance; wait until its bus exists.
loginctl enable-linger nostr
for _ in $(seq 1 30); do [[ -S /run/user/$UID_N/bus ]] && break; sleep 1; done
[[ -S /run/user/$UID_N/bus ]] || { echo "systemd user instance for nostr did not start"; exit 1; }

install -d -m 0750 -o nostr -g nostr /var/lib/nostr-relay
install -d -m 0750 -o nostrgw -g nostrgw /var/lib/nostrgw
install -d -m 0750 -o root -g nostrgw /etc/nostrgw
install -d -m 0755 /opt/nostrgw
install -m 0644 "$DIR/gateway.py" "$DIR/maintenance.py" "$DIR/backup.py" /opt/nostrgw/
python3 -m venv /opt/nostrgw/venv
/opt/nostrgw/venv/bin/pip install --disable-pip-version-check 'websockets==15.0.1'
# Fast native BIP-340 verification. Binary wheels only, so a Pi never compiles C;
# without it the gateway falls back to slow pure-Python verification.
/opt/nostrgw/venv/bin/pip install --disable-pip-version-check --only-binary=:all: 'coincurve==21.0.0' \
  || echo 'WARNING: coincurve unavailable, using slow pure-Python signature checks'

# Merge policy: bundled defaults, overridden by whatever is already configured.
python3 - "$DOMAIN" "$DIR/policy.json" <<'PY'
import json,sys
from pathlib import Path
p=Path('/etc/nostrgw/policy.json'); d=json.loads(Path(sys.argv[2]).read_text())
if p.exists(): d.update(json.loads(p.read_text()))
d['domain']=sys.argv[1]
assert d['target_bytes']<d['prune_bytes']<d['stop_bytes'], 'need target_bytes < prune_bytes < stop_bytes'
p.write_text(json.dumps(d,indent=2)+'\n')
PY
chown root:nostrgw /etc/nostrgw/policy.json; chmod 0640 /etc/nostrgw/policy.json
MAXMSG=$(python3 -c 'import json;print(json.load(open("/etc/nostrgw/policy.json"))["max_ws_message_bytes"])')
KINDS=$(python3 -c 'import json;print(", ".join(map(str,json.load(open("/etc/nostrgw/policy.json"))["allowed_kinds"])))')

cat >/var/lib/nostr-relay/config.toml <<EOF
[info]
relay_url = "wss://$DOMAIN/"
name = "Small Public Nostr Relay"
description = "Public microrelay. NIP-13 PoW required; notes limited to 128 characters."
[database]
engine = "sqlite"
data_directory = "/usr/src/app/db"
min_conn = 1
max_conn = 3
[network]
address = "0.0.0.0"
port = 8080
[options]
reject_future_seconds = 1800
[limits]
messages_per_sec = 2
subscriptions_per_min = 12
max_blocking_threads = 4
max_event_bytes = $MAXMSG
max_ws_message_bytes = $MAXMSG
max_ws_frame_bytes = $MAXMSG
broadcast_buffer = 128
event_persist_buffer = 128
event_kind_allowlist = [$KINDS]
limit_scrapers = true
[authorization]
nip42_auth = false
EOF
chown nostr:nostr /var/lib/nostr-relay/config.toml
chmod 0640 /var/lib/nostr-relay/config.toml

# Everything happens in the nostr user's own (rootless) image store, which is
# the one the container actually runs from.
cd /
# Remove any wrong-architecture upstream image left by an earlier install attempt.
OLD=docker.io/scsibug/nostr-rs-relay:latest
if as_nostr podman image exists "$OLD" && [[ $(as_nostr podman image inspect --format '{{.Architecture}}' "$OLD") != arm64 ]]; then
  as_nostr podman rmi -f "$OLD" >/dev/null && echo "Removed non-arm64 image $OLD"
fi

if [[ -n $IMAGE ]]; then
  as_nostr podman pull --arch arm64 "$IMAGE"
  ARCH=$(as_nostr podman image inspect --format '{{.Architecture}}' "$IMAGE")
  [[ $ARCH == arm64 ]] || { echo "Image architecture is $ARCH, not arm64; refusing"; exit 1; }
  REPO="${IMAGE%%@*}"; [[ ${REPO##*/} == *:* ]] && REPO="${REPO%:*}"
  PINNED="$REPO@$(as_nostr podman image inspect --format '{{.Digest}}' "$IMAGE")"
  PULL=missing
else
  PINNED="localhost/nostr-rs-relay:$RELAY_REF"
  PULL=never
  if [[ $REBUILD == 1 ]] || ! as_nostr podman image exists "$PINNED"; then
    # Rust needs roughly 1.5 GB RAM per parallel job and several GB of scratch space.
    FREE_KB=$(df --output=avail -k /home/nostr | tail -1)
    (( FREE_KB > 6*1024*1024 )) || { echo "Building the relay needs ~6 GB free in /home/nostr (have $((FREE_KB/1024)) MB)"; exit 1; }
    MEM_KB=$(awk '/^(MemTotal|SwapTotal):/{s+=$2} END{print s}' /proc/meminfo)
    if   (( MEM_KB < 3*1024*1024 )); then JOBS=1
    elif (( MEM_KB < 6*1024*1024 )); then JOBS=2
    else JOBS=$(nproc); fi
    SRC=/home/nostr/build/nostr-rs-relay
    rm -rf "$SRC"; as_nostr mkdir -p /home/nostr/build
    as_nostr git clone --quiet --depth 1 --branch "$RELAY_REF" "$RELAY_REPO" "$SRC"
    HEAD_COMMIT=$(as_nostr git -C "$SRC" rev-parse HEAD)
    [[ $HEAD_COMMIT == "$RELAY_COMMIT" ]] || { echo "Tag $RELAY_REF is $HEAD_COMMIT, expected $RELAY_COMMIT; refusing"; exit 1; }
    # Limit cargo's parallelism in the builder stage so small Pis don't run out of memory.
    head -1 "$SRC/Dockerfile" | grep -qi '^FROM .* as builder' || { echo 'Unexpected upstream Dockerfile layout; refusing'; exit 1; }
    as_nostr sed -i "1a ENV CARGO_BUILD_JOBS=$JOBS" "$SRC/Dockerfile"
    echo "Building nostr-rs-relay $RELAY_REF ($HEAD_COMMIT) with $JOBS job(s)."
    echo "This takes roughly 20-40 min on a Pi 5 and over an hour on a Pi 4."
    as_nostr podman build --pull=missing -t "$PINNED" "$SRC"
    # Reclaim several GB: build stages, the Rust toolchain image and the source.
    as_nostr podman image prune -f >/dev/null
    as_nostr podman rmi docker.io/library/rust:1-bookworm >/dev/null 2>&1 || true
    rm -rf /home/nostr/build
  else
    echo "Using existing $PINNED (set NOSTR_RELAY_REBUILD=1 to rebuild)"
  fi
  ARCH=$(as_nostr podman image inspect --format '{{.Architecture}}' "$PINNED")
  [[ $ARCH == arm64 ]] || { echo "Built image architecture is $ARCH, not arm64; refusing"; exit 1; }
fi
echo "Relay image: $PINNED"

QUAD=/home/nostr/.config/containers/systemd
install -d -m 0755 -o nostr -g nostr "$QUAD"
cat >"$QUAD/nostr-relay.container" <<EOF
[Unit]
Description=Nostr Rust relay (backend, loopback only)
[Container]
Image=$PINNED
Pull=$PULL
ContainerName=nostr-relay
PublishPort=127.0.0.1:17080:8080
Volume=/var/lib/nostr-relay:/usr/src/app/db:rw
Volume=/var/lib/nostr-relay/config.toml:/usr/src/app/config.toml:ro
User=100:100
Environment=RUST_LOG=warn
NoNewPrivileges=true
[Service]
Restart=always
RestartSec=10
[Install]
WantedBy=default.target
EOF
chown -R nostr:nostr /home/nostr/.config
# Make the data directory owned by UID 100 inside the rootless container's user namespace.
as_nostr podman unshare chown -R 100:100 /var/lib/nostr-relay
chmod 0755 /var/lib/nostr-relay

cat >/etc/systemd/system/nostrgw.service <<'EOF'
[Unit]
Description=Nostr privacy admission gateway
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=nostrgw
Group=nostrgw
WorkingDirectory=/var/lib/nostrgw
ExecStart=/opt/nostrgw/venv/bin/python /opt/nostrgw/gateway.py
Restart=always
RestartSec=3
MemoryMax=256M
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/nostrgw
ReadOnlyPaths=/var/lib/nostr-relay
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/nostr-prune.service <<'EOF'
[Unit]
Description=Offline Nostr database storage maintenance
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/nostrgw/maintenance.py
TimeoutStartSec=3600
EOF
cat >/etc/systemd/system/nostr-prune.timer <<'EOF'
[Unit]
Description=Check Nostr DB size each 30 minutes
[Timer]
OnBootSec=10min
OnUnitInactiveSec=30min
RandomizedDelaySec=3min
Persistent=false
[Install]
WantedBy=timers.target
EOF
cat >/etc/systemd/system/nostr-backup.service <<'EOF'
[Unit]
Description=Online backup of the Nostr relay database
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/usr/bin/python3 /opt/nostrgw/backup.py
EOF
cat >/etc/systemd/system/nostr-backup.timer <<'EOF'
[Unit]
Description=Daily Nostr relay backup
[Timer]
OnCalendar=*-*-* 04:00:00
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
EOF

# Cap the journal: log churn is a big source of microSD wear.
install -d /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/90-nostr-pi-relay.conf <<EOF
$MARKER
[Journal]
SystemMaxUse=64M
RuntimeMaxUse=32M
EOF
systemctl restart systemd-journald

# NIP-11 document generated from the live policy so it can't drift.
NIP11=$(python3 - <<'PY'
import json
p=json.load(open('/etc/nostrgw/policy.json'))
print(json.dumps({"name":"Small Public Nostr Relay",
  "description":f"{p['max_note_characters']} character notes, mandatory PoW ({p['min_pow_bits']} bits)",
  "software":"https://github.com/scsibug/nostr-rs-relay","supported_nips":[1,11,13],
  "limitation":{"max_message_length":p['max_ws_message_bytes'],"max_subscriptions":p['subscriptions_per_connection'],
    "max_filters":p['max_filters_per_req'],"max_limit":p['max_limit'],"max_content_length":p['max_note_characters'],
    "max_event_tags":max([p['max_tags'],*p.get('max_tags_by_kind',{}).values()]),
    "min_pow_difficulty":p['min_pow_bits'],"restricted_writes":True,
    "created_at_lower_limit":p['max_event_age_seconds'],"created_at_upper_limit":1800}},separators=(',',':')))
PY
)
# Keep the original Caddyfile once, so uninstall.sh can put it back.
if [[ -e /etc/caddy/Caddyfile && ! -e /etc/caddy/Caddyfile.pre-nostr ]] && ! grep -qF "$MARKER" /etc/caddy/Caddyfile; then
  cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.pre-nostr
  echo "Saved previous Caddyfile to /etc/caddy/Caddyfile.pre-nostr"
fi
cat >/etc/caddy/Caddyfile <<EOF
$MARKER
$DOMAIN {
  encode zstd gzip
  @nip11 header Accept *application/nostr+json*
  handle @nip11 {
    header Content-Type application/nostr+json
    header Access-Control-Allow-Origin *
    respond \`$NIP11\` 200
  }
  handle {
    reverse_proxy 127.0.0.1:17081 {
      header_up X-Forwarded-For {remote_host}
    }
  }
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

systemctl daemon-reload
as_nostr systemctl --user daemon-reload
# Quadlet units are generated, so they can't be "enabled"; the [Install]
# section above already makes the relay start at boot.
as_nostr systemctl --user restart nostr-relay.service
systemctl enable nostrgw.service nostr-prune.timer nostr-backup.timer caddy
systemctl restart nostrgw.service caddy
systemctl start nostr-prune.timer nostr-backup.timer
printf '\nRelay: wss://%s\nLocal monitor: curl -s http://127.0.0.1:17082\nPolicy: /etc/nostrgw/policy.json\nBackups: /var/backups/nostr-relay (copy these off the Pi)\n' "$DOMAIN"
