#!/usr/bin/env bash
set -euo pipefail

# --- User settings (edit these) ---------------------------------------------

# Countries to exclude (ISO 3166-1 alpha-2, lower-case inside {} for Tor)
EXCLUDE_COUNTRIES=("{de}" "{fr}" "{us}")

# Known malicious relays (prefer fingerprints; IPs also supported)
# Fingerprint format: 40 hex chars, optionally spaced. Example:
# BAD_RELAYS_FINGERPRINTS=("0123456789ABCDEF0123456789ABCDEF01234567")
BAD_RELAYS_FINGERPRINTS=()

# IPs (only if you have high-confidence)
BAD_RELAYS_IPS=()

# Local SOCKS port for Tor client
SOCKS_PORT="9050"

# ---------------------------------------------------------------------------

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root (e.g., sudo $0)" >&2
    exit 1
  fi
}

install_tor_debian() {
  apt-get update
  apt-get install -y tor
}

normalize_fp() {
  # Remove spaces, uppercase
  tr -d ' ' | tr '[:lower:]' '[:upper:]'
}

write_config() {
  mkdir -p /etc/tor/torrc.d

  local cfg="/etc/tor/torrc.d/99-custom.conf"

  # Build ExcludeNodes list: countries + fingerprints + IPs
  local exclude_nodes=()
  exclude_nodes+=("${EXCLUDE_COUNTRIES[@]}")

  for fp in "${BAD_RELAYS_FINGERPRINTS[@]}"; do
    fp="$(echo -n "${fp}" | normalize_fp)"
    if [[ ! "${fp}" =~ ^[0-9A-F]{40}$ ]]; then
      echo "Invalid fingerprint: ${fp}" >&2
      exit 1
    fi
    exclude_nodes+=("\$${fp}")
  done

  for ip in "${BAD_RELAYS_IPS[@]}"; do
    # Minimal validation
    if [[ ! "${ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
      echo "Invalid IP: ${ip}" >&2
      exit 1
    fi
    exclude_nodes+=("${ip}")
  done

  {
    echo "# Managed by setup-tor-client.sh"
    echo ""
    echo "# Basic client settings"
    echo "SocksPort ${SOCKS_PORT}"
    echo "RunAsDaemon 1"
    echo ""
    echo "# Security / hygiene"
    echo "AvoidDiskWrites 1"
    echo "CookieAuthentication 1"
    echo ""
    echo "# Exclusions"
    if (( ${#exclude_nodes[@]} > 0 )); then
      # Join with commas
      local joined
      joined="$(IFS=,; echo "${exclude_nodes[*]}")"
      echo "ExcludeNodes ${joined}"
      echo "StrictNodes 1"
    fi
    echo ""
    echo "# Optional: reduce exposure to unstable circuits (conservative defaults)"
    echo "# MaxCircuitDirtiness 600"
    echo "# NewCircuitPeriod 30"
  } > "${cfg}"

  echo "Wrote: ${cfg}"
}

restart_tor() {
  systemctl enable tor
  systemctl restart tor
  systemctl --no-pager --full status tor || true
}

main() {
  require_root
  install_tor_debian
  write_config
  restart_tor
  echo ""
  echo "Tor client should now be listening on SOCKS ${SOCKS_PORT}."
  echo "Test (example): torsocks curl -I https://check.torproject.org/"
}

main "$@"
