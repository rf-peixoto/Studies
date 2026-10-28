#!/usr/bin/env bash
# Remove EVERYTHING install.sh created: services, timers, the relay container,
# its image and the nostr user's whole Podman storage, both service users,
# the relay database, ban state, policy, backups, and the Caddy site.
# Intended for the development phase. There is no undo.
#
#   sudo bash uninstall.sh                  # asks for confirmation
#   sudo bash uninstall.sh --yes            # no prompt
#   sudo bash uninstall.sh --keep-backups   # leave /var/backups/nostr-relay
#   sudo bash uninstall.sh --purge-packages # also apt purge podman & caddy
set -uo pipefail   # deliberately no -e: keep going and clean as much as possible
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }

YES=0; KEEP_BACKUPS=0; PURGE=0
for a in "$@"; do
  case $a in
    -y|--yes) YES=1 ;;
    --keep-backups) KEEP_BACKUPS=1 ;;
    --purge-packages) PURGE=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

MARKER='# managed by nostr-pi-relay'
BACKUPS=$(python3 -c 'import json;print(json.load(open("/etc/nostrgw/policy.json")).get("backup_dir","/var/backups/nostr-relay"))' 2>/dev/null || echo /var/backups/nostr-relay)

if [[ $YES -ne 1 ]]; then
  echo 'This permanently deletes the Nostr relay, all its events, ban state, policy,'
  [[ $KEEP_BACKUPS -eq 1 ]] || echo "backups in $BACKUPS,"
  echo 'the relay container and image, and the "nostr" and "nostrgw" users.'
  read -r -p 'Type "delete" to continue: ' ans
  [[ $ans == delete ]] || { echo 'Aborted.'; exit 1; }
fi

step() { printf '\n==> %s\n' "$*"; }

step 'Stopping gateway, timers and Caddy site'
for u in nostr-prune.timer nostr-backup.timer nostr-prune.service nostr-backup.service nostrgw.service; do
  systemctl disable --now "$u" 2>/dev/null
done
rm -f /etc/systemd/system/{nostrgw.service,nostr-prune.service,nostr-prune.timer,nostr-backup.service,nostr-backup.timer}
systemctl daemon-reload

if id nostr >/dev/null 2>&1; then
  UID_N=$(id -u nostr)
  as_nostr() { (cd / && runuser -u nostr -- env XDG_RUNTIME_DIR="/run/user/$UID_N" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$UID_N/bus" "$@"); }
  # Make sure the user's systemd/podman environment exists so we can clean it properly.
  loginctl enable-linger nostr 2>/dev/null
  for _ in $(seq 1 15); do [[ -S /run/user/$UID_N/bus ]] && break; sleep 1; done

  step 'Stopping relay container and wiping the nostr user'"'"'s Podman storage (containers, images, volumes)'
  as_nostr systemctl --user stop nostr-relay.service 2>/dev/null
  rm -f /home/nostr/.config/containers/systemd/nostr-relay.container
  as_nostr systemctl --user daemon-reload 2>/dev/null
  as_nostr podman rm -af -t 5 2>/dev/null
  as_nostr podman rmi -af 2>/dev/null
  as_nostr podman system reset -f 2>/dev/null

  step 'Removing user nostr'
  loginctl disable-linger nostr 2>/dev/null
  loginctl terminate-user nostr 2>/dev/null
  for _ in $(seq 1 10); do pgrep -u nostr >/dev/null || break; sleep 1; done
  pkill -KILL -u nostr 2>/dev/null
  # Rootless Podman leaves files owned by sub-UIDs in the home; root can remove them.
  userdel -r nostr 2>/dev/null || userdel nostr 2>/dev/null
  rm -rf /home/nostr
  sed -i '/^nostr:/d' /etc/subuid /etc/subgid 2>/dev/null
fi

step 'Removing user nostrgw'
pkill -KILL -u nostrgw 2>/dev/null
id nostrgw >/dev/null 2>&1 && { userdel nostrgw 2>/dev/null; getent group nostrgw >/dev/null && groupdel nostrgw 2>/dev/null; }

step 'Deleting relay data, gateway state, policy and code'
rm -rf /var/lib/nostr-relay /var/lib/nostrgw /etc/nostrgw /opt/nostrgw
if [[ $KEEP_BACKUPS -eq 1 ]]; then echo "Keeping backups in $BACKUPS"; else rm -rf "$BACKUPS"; fi

step 'Removing journald size cap'
rm -f /etc/systemd/journald.conf.d/90-nostr-pi-relay.conf
systemctl restart systemd-journald 2>/dev/null

step 'Removing Caddy site'
if [[ -f /etc/caddy/Caddyfile ]] && grep -qF "$MARKER" /etc/caddy/Caddyfile; then
  if [[ -f /etc/caddy/Caddyfile.pre-nostr ]]; then
    mv -f /etc/caddy/Caddyfile.pre-nostr /etc/caddy/Caddyfile
    echo 'Restored your previous Caddyfile'
    systemctl restart caddy 2>/dev/null
  else
    printf '# Emptied by nostr-pi-relay uninstall.sh\n' >/etc/caddy/Caddyfile
    systemctl disable --now caddy 2>/dev/null
    echo 'No previous Caddyfile existed; emptied it and stopped Caddy'
  fi
else
  echo 'Caddyfile not managed by this project; left untouched'
fi

if [[ $PURGE -eq 1 ]]; then
  step 'Purging packages installed by install.sh'
  DEBIAN_FRONTEND=noninteractive apt-get purge -y podman caddy slirp4netns passt
  DEBIAN_FRONTEND=noninteractive apt-get autoremove -y
  rm -rf /var/lib/caddy /etc/caddy
fi

step 'Done. Leftovers check:'
left=0
for x in /var/lib/nostr-relay /var/lib/nostrgw /etc/nostrgw /opt/nostrgw /home/nostr; do
  [[ -e $x ]] && { echo "  still present: $x"; left=1; }
done
for u in nostr nostrgw; do id "$u" >/dev/null 2>&1 && { echo "  user still exists: $u"; left=1; }; done
[[ $left -eq 0 ]] && echo '  nothing left behind'
