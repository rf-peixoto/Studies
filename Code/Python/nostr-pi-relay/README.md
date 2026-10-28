# Private-by-default Raspberry Pi Nostr microrelay

Deployment bundle targeting **Debian 13 arm64**, rootless Podman, upstream `scsibug/nostr-rs-relay`, Caddy TLS, and an additional small Python WebSocket policy gateway.

## Install

1. Point an A/AAAA DNS record at your publicly reachable address. Forward TCP ports **80 and 443** to the Pi. If behind CGNAT, you need another ingress solution; this installer does not configure tunnels.
2. Storage: default thresholds suit a **32 GB microSD** (pruning at 4 GiB, writes blocked at 6 GiB). VACUUM needs about **twice** the live database size free. With short notes and strict rate limits, expect the database to stay in the MB range for a long time. Use a high-endurance A1/A2 card and a solid power supply.
3. Add your own hex pubkey(s) to `trusted_pubkeys` in `policy.json` **before** installing (or later, see below). Most clients only mine PoW for kind-1 notes, so without this you can't publish your own profile (0), follow list (3) or relay list (10002) here.
4. On a fresh host (this **replaces** `/etc/caddy/Caddyfile`; the previous one is saved once to `/etc/caddy/Caddyfile.pre-nostr`):

```bash
sudo bash install.sh relay.yourdomain.example
```

Re-running is safe: existing `policy.json` values are kept and any new keys are added.

**The relay image is built on the Pi.** Upstream only publishes amd64 images on Docker Hub, so the installer clones the official repo at tag `0.10.0`, checks that it is exactly commit `b5c1f642…`, and builds it with Podman using upstream's own Dockerfile. Expect roughly 20–40 minutes on a Pi 5 and over an hour on a Pi 4. You need about 6 GB free during the build. Cargo parallelism is reduced automatically on Pis with less than 6 GB of RAM plus swap. Run the install inside `tmux` or `screen`, because an SSH drop would kill the build. Afterwards the Rust toolchain image and the sources are deleted. Re-running the installer reuses the built image. Other options:

- `NOSTR_RELAY_REBUILD=1` forces a rebuild.
- `NOSTR_RELAY_REF=<tag>` together with `NOSTR_RELAY_COMMIT=<sha>` builds another release.
- `NOSTR_RELAY_IMAGE=<image@sha256:...>` uses a prebuilt arm64 image you trust instead. The installer pulls it, refuses it if it isn't arm64, and pins its digest.

5. Check services:

```bash
sudo systemctl status nostrgw caddy nostr-prune.timer nostr-backup.timer
sudo -iu nostr systemctl --user status nostr-relay
curl -s http://127.0.0.1:17082          # "fast_signatures": true means coincurve is in use
curl -s -H 'Accept: application/nostr+json' https://relay.yourdomain.example
```

## Uninstall (development)

```bash
sudo bash uninstall.sh                  # asks you to type "delete"
sudo bash uninstall.sh --yes            # no prompt
sudo bash uninstall.sh --keep-backups   # keep /var/backups/nostr-relay
sudo bash uninstall.sh --purge-packages # also apt purge podman, caddy, slirp4netns, passt
```

This removes all services and timers, the relay container, **every image and volume in the `nostr` user's Podman storage**, the `nostr` and `nostrgw` users, `/var/lib/nostr-relay`, `/var/lib/nostrgw`, `/etc/nostrgw`, `/opt/nostrgw`, backups, and the journald cap. If `Caddyfile.pre-nostr` exists it is restored; otherwise Caddy is emptied and stopped. Caddy's TLS certificates in `/var/lib/caddy` are kept unless you pass `--purge-packages`, which avoids hitting Let's Encrypt rate limits while you reinstall repeatedly.

## Architecture and enforceable policy

- Public TLS WebSockets -> Caddy -> gateway (`127.0.0.1:17081`) -> relay container (`127.0.0.1:17080`). Backend has **no public-facing port**.
- Client "address" means the IPv4 address, or the **IPv6 /64** (`ipv6_prefix`), since one subscriber usually controls a whole /64.
- Per client address: 3 concurrent connections, 10 subscription creations per minute, 10 incoming events per minute. Per connection: 10 active subscription IDs, up to 3 filters per REQ, 50 historical events per filter (`max_limit`). Live events keep streaming without a cap.
- **Every filter must name `authors`, `ids`, `#e` or `#p`**, with full 64-char hex values (no prefix matching). `since`/`until`/`kinds` can narrow a query but are not enough on their own, so "everything since X" scraping is refused.
- Accepted kinds 0, 1, 3, 10002. Kind 1 content is at most 128 Python codepoints. Tags: 20 per event, 1500 for kind 3 (follow lists) via `max_tags_by_kind`. Messages up to 128 KiB (`max_ws_message_bytes`, also applied to the backend).
- NIP-13 PoW (16 bits, with a committed `nonce` target) is checked **before** the signature, so junk costs one SHA-256 rather than an elliptic-curve check. Signatures use `coincurve` (native libsecp256k1) when installed, with a pure-Python fallback; both run off the event loop in a 2-thread pool. The backend revalidates.
- Rejections use NIP-01 prefixes (`pow:`, `blocked:`, `rate-limited:`, `invalid:`, `error:`) so clients can show a useful reason. Malformed REQs get a `CLOSED`/`NOTICE` instead of silence.
- The gateway forwards its own re-serialization of the validated event, never the original bytes.
- Per-pubkey publishing rate 5/minute; temporary ban 2h on violation; permanent ban on the third in a rolling 24h. Strikes only happen after the signature is verified, so nobody can get someone else's key banned. `blocked_pubkeys` always rejected; `trusted_pubkeys` exempt from PoW and ban escalation, but not quotas.
- In-memory counters and sliding windows, pruned every 2 minutes so memory doesn't grow with each new IP/pubkey; no per-request IP logs. Durable ban state stores pubkey and timestamps. Gateway memory is capped at 256 MB (`MemoryMax`).
- NIP-11 document is generated from `policy.json` at install time. Re-run `install.sh` after changing limits so it stays accurate.
- Local-only metrics: `curl http://127.0.0.1:17082` (bytes passed, forwarded/rejected events, active connections, DB size). Reset on restart.

## Storage protection

- Writes blocked by the gateway once DB+WAL+SHM reach `stop_bytes` (6 GiB). This is **not a disk quota**; use filesystem alerts too.
- Maintenance timer checks every ~30 minutes. At `prune_bytes` (4 GiB) it stops the relay, deletes kind-1 notes older than 30 days and hidden events, then oldest kind-1 notes until live pages are below `target_bytes` (3 GiB). Kinds 0, 3, 10002 are untouched. VACUUM runs only with ~2× live size free, with SQLite temp files placed on the data filesystem. Files touched as root are handed back to the container user.
- **Retention is capacity-triggered**, not a 30-day deletion SLA.

## Backups

`nostr-backup.timer` runs daily around 04:00: an online SQLite backup of the relay DB plus ban state and policy, into `/var/backups/nostr-relay/<timestamp>/`, keeping the last `backup_keep` (3). **These are on the same card.** Copy them off the Pi to survive card failure, for example from another machine:

```bash
rsync -a --rsync-path='sudo rsync' pi@relay:/var/backups/nostr-relay/ ./nostr-relay-backups/
```

Restore: run `install.sh`, then `sudo -iu nostr systemctl --user stop nostr-relay`, copy `nostr.db` into `/var/lib/nostr-relay/`, `sudo -u nostr podman unshare chown 100:100 /var/lib/nostr-relay/nostr.db`, copy `abuse.sqlite3` to `/var/lib/nostrgw/` (owner `nostrgw`), and start the relay again.

## MicroSD wear

The installer caps the journal at 64 MB. Also recommended (not done automatically, since it edits `/etc/fstab`): add `noatime` to the root filesystem's mount options. When traffic grows, moving `/var/lib/nostr-relay` to a USB SSD is the best upgrade.

## Important limitations / operational caveats

1. Custom, untested-in-production gateway: validate with real Nostr clients before publishing the domain, especially PoW support and the precise-filter requirement.
2. The 50 limit applies to each filter; repeated precise queries can still retrieve more.
3. Proxy networks, large IPv6 allocations and new keypairs defeat some IP/pubkey limits. Caddy overwrites `X-Forwarded-For` with the remote address; don't put another proxy in front without adjusting that.
4. The backend's own clients/subscriptions are not counted; monitoring reports gateway counts.
5. Events older than 30 days cannot be published, even with PoW. This intentionally blocks historical refill.
6. The relay is pinned to a release tag and commit (built locally, `Pull=never`). To upgrade, re-run `install.sh` with `NOSTR_RELAY_REF`/`NOSTR_RELAY_COMMIT` set to the new release and `NOSTR_RELAY_REBUILD=1`. Check the upstream changelog for database migrations first, and take a backup.
7. Reinstalling overwrites relay config and the Caddyfile. **Other Caddy sites on this host will be lost**.
8. PoW failures and malformed messages are rejected without pubkey strikes.
9. Container UID mapping may differ across Podman versions; if the container cannot read/write the SQLite directory, inspect its mount mappings.

## Administrative operations

Edit `/etc/nostrgw/policy.json` and restart the gateway (re-run `install.sh` instead if you changed limits advertised in NIP-11 or message sizes):

```bash
sudoedit /etc/nostrgw/policy.json
sudo systemctl restart nostrgw
```

Manual ban, 64-character lowercase hex public key:

```bash
sudo python3 - <<'PY'
import sqlite3
pk=input('hex pubkey: ').strip()
assert len(pk)==64 and all(x in '0123456789abcdef' for x in pk)
c=sqlite3.connect('/var/lib/nostrgw/abuse.sqlite3')
c.execute('INSERT OR REPLACE INTO bans(pubkey,until,manual) VALUES (?,-1,1)',(pk,))
c.commit()
PY
```

For manual unban, remove the entry from both `bans` and `strikes` so it does not immediately escalate again.

## References

- https://github.com/scsibug/nostr-rs-relay
- https://github.com/scsibug/nostr-rs-relay/blob/master/config.toml
- https://docs.rs/crate/nostr-rs-relay/latest/source/docs/database-maintenance.md
- https://github.com/nostr-protocol/nips/blob/master/01.md
- https://github.com/nostr-protocol/nips/blob/master/11.md
- https://github.com/nostr-protocol/nips/blob/master/13.md
