# proxy-one

An authenticated HTTP / HTTPS / SOCKS5 forward proxy for a VPS, written in Go
with **zero external dependencies** (standard library only). Ships with bash
scripts to install, run, and manage per-user access tokens.

## Features

- **Three protocols, one binary:** HTTP forward proxy, HTTPS via `CONNECT`, and
  SOCKS5 — driven from a single config, on separate ports.
- **Mandatory per-user token auth.** Every request must carry a valid token.
  - HTTP / HTTPS: `Proxy-Authorization: Basic base64(user:token)`
  - SOCKS5: RFC 1929 username/password (token goes in the password field)
- **Per-token controls:** time-to-live in days, connections-per-second rate,
  burst allowance, and a concurrent-connection cap — all set at token creation.
- **Tokens are never stored in plaintext.** Only `SHA-256(token)` is written to
  disk, and validation uses a constant-time comparison.
- **SSRF / abuse protection (on by default):** destinations resolving to
  loopback, private, link-local (incl. cloud metadata `169.254.169.254`), CGNAT
  and reserved ranges are refused. The validated IP is dialed directly, closing
  the DNS-rebinding hole.
- **Structured JSON-lines logging.** By default only *authenticated* requests
  are logged; pass `--log-all` to also record dropped/unauthenticated attempts.
  The token itself is never logged — only a short hash prefix.
- **Live token reload** on `SIGHUP`: adding or revoking a token takes effect in
  milliseconds without dropping other users' connections.
- **Hardened systemd unit** (sandboxed, auto-restart) and a **logrotate** policy
  that compresses logs older than a week with `xz -9e` and keeps ~3.7 months.

## A note on the auth model (important)

Different protocols expose auth at different granularities, and this is inherent
to the protocols, not a shortcut:

- **HTTP** — the token is checked on **every request** (even on a keep-alive
  connection), because the header is present each time.
- **HTTPS `CONNECT`** and **SOCKS5** — the token is checked once at
  **connection setup**. After that the connection is an opaque encrypted tunnel
  with no request boundaries to re-authenticate.

SOCKS4 and UDP are intentionally unsupported. A SOCKS5 client that requests UDP
`ASSOCIATE` or `BIND` is rejected; only outbound TCP `CONNECT` is served.

## Requirements

A Debian/Ubuntu (apt) or RHEL-family (dnf/yum) VPS with root. `install.sh`
installs everything else it needs (Go toolchain, `xz`, `logrotate`).

## Install

```bash
# Optionally choose ports up front (defaults: 8080 HTTP, 1080 SOCKS5):
sudo HTTP_PORT=8080 SOCKS_PORT=1080 ./install.sh
```

This builds the binary to `/opt/proxyd/proxyd`, creates a locked-down `proxyd`
system user, writes config to `/etc/proxyd/`, installs the systemd unit and
logrotate policy, and opens the ports in ufw/iptables.

> If iptables was used, persist the rules (e.g. `netfilter-persistent save`) so
> they survive a reboot. Also open the ports at your cloud provider's firewall.

## Manage tokens

```bash
# Create a token that lasts 30 days, capped at 10 conn/s (burst 20), 50 concurrent:
sudo ./token.sh add --user alice --days 30 --rate 10 --burst 20 --max-conns 50

# List tokens (shows hash prefix, expiry, limits, status — never the secret):
sudo ./token.sh list

# Revoke every token for a user (takes effect immediately, live):
sudo ./token.sh revoke --user alice
```

The plaintext token is printed **once**, at creation. Store it then.

## Start / stop

```bash
sudo ./start.sh --http 8080 --socks 1080      # (re)start via systemd
sudo ./start.sh --log-all                     # also log dropped requests
sudo ./start.sh --foreground                  # run in the terminal (no systemd)
sudo ./start.sh --status
sudo ./start.sh --stop
```

`start.sh` writes your chosen flags to `/etc/proxyd/proxyd.env` and restarts the
service. Anything not overridden comes from `/etc/proxyd/config.json`.

## Client usage

```bash
# HTTP + HTTPS through the HTTP proxy port:
curl -x http://alice:<TOKEN>@<SERVER_IP>:8080 https://example.com

# SOCKS5 (socks5h = resolve DNS at the proxy):
curl -x socks5h://alice:<TOKEN>@<SERVER_IP>:1080 https://example.com
```

## Logging

JSON-lines at `/var/log/proxyd/proxyd.log`, one event per line, e.g.:

```json
{"ts":"...","event":"tunnel","proto":"socks5","src_ip":"203.0.113.9","user":"alice","token_prefix":"68a0d0b99e66","method":"CONNECT","dest_host":"example.com","dest_port":443,"dest_ip":"93.184.216.34","auth":"accepted","bytes_up":517,"bytes_down":8462,"duration_ms":214}
```

- Default: only `auth:"accepted"` events are recorded.
- `--log-all`: additionally records `auth:"missing"` / `auth:"rejected"` and
  the reason (`unknown_token`, `expired`, `revoked`, `rate_limited`, …).
- Rotation: weekly, keeps 16 generations (~3.7 months); rotated files are
  compressed with `xz -9e`. Nothing is silently deleted before that window.

## Configuration reference (`/etc/proxyd/config.json`)

| Key | Meaning |
|-----|---------|
| `http_addr` / `socks_addr` | listen addresses; `""` disables that listener |
| `token_db` | path to the hashed-token store |
| `log_file` / `log_all` | log destination and whether to log drops |
| `ssrf_protect` | block private/reserved destinations (recommended: `true`) |
| `extra_blocked_cidrs` | additional CIDRs to deny |
| `dial_timeout_sec` / `idle_timeout_sec` / `handshake_timeout_sec` | timeouts |
| `preauth_ip_rate` / `preauth_ip_burst` | per-source-IP accept limit before auth |

## Security notes

- A token is a bearer credential. If one leaks, `revoke` it — revocation is
  live. Keep TTLs short for untrusted users.
- Keep `ssrf_protect: true` unless you fully trust every token holder; without
  it the proxy can be aimed at your own VPS and cloud metadata endpoint.
- Consider restricting the ports to known client IPs at the firewall for another
  layer beyond the token.
