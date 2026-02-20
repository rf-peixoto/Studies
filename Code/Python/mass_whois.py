#!/usr/bin/env python3
"""
ip_owner_enricher.py

Enrich a list of IPs with Shodan host info + RDAP/WHOIS ownership hints.
Outputs CSV (and optionally JSON).

Requirements:
  pip install shodan ipwhois

Usage:
  export SHODAN_API_KEY="YOURKEY"
  python3 ip_owner_enricher.py -i ips.txt -o results.csv --json results.json

Notes:
- Shodan endpoint: /shodan/host/{ip} :contentReference[oaicite:2]{index=2}
- ipwhois recommends RDAP lookups (lookup_rdap) :contentReference[oaicite:3]{index=3}
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

# Third-party
try:
    import shodan  # type: ignore
except Exception:
    shodan = None

from ipwhois import IPWhois  # type: ignore
from ipwhois.exceptions import IPDefinedError, HTTPLookupError  # type: ignore


@dataclass
class ResultRow:
    ip: str

    # "Owner" (best-effort synthesis)
    owner_best: str

    # RDAP/WHOIS-ish fields
    rdap_network_name: str
    rdap_asn: str
    rdap_asn_description: str
    rdap_asn_cidr: str
    rdap_asn_registry: str
    rdap_country: str
    rdap_owner_hint: str  # extracted from RDAP objects (registrant-like), if any

    # Shodan fields
    shodan_org: str
    shodan_isp: str
    shodan_asn: str
    shodan_country: str
    shodan_city: str
    shodan_hostnames: str
    shodan_domains: str
    shodan_tags: str
    shodan_last_update: str

    # Error fields
    shodan_error: str
    rdap_error: str


def _clean(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, (list, tuple)):
        return ", ".join(str(x) for x in s if x is not None)
    return str(s).strip()


def _is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except Exception:
        return False


def read_ips(path: str) -> List[str]:
    ips: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # allow: "1.2.3.4,comment" or "1.2.3.4 comment"
            token = re.split(r"[\s,;]+", line, maxsplit=1)[0].strip()
            if _is_valid_ip(token):
                ips.append(token)
            else:
                print(f"[!] Skipping invalid IP: {token}", file=sys.stderr)
    # de-duplicate while preserving order
    seen = set()
    out = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def shodan_lookup(api: "shodan.Shodan", ip: str, min_interval_s: float = 1.0) -> Tuple[Dict[str, Any], str]:
    """
    Returns (data, error_string). Enforces a minimal delay between calls.
    """
    # crude global rate control (single-process)
    time.sleep(max(0.0, min_interval_s))
    try:
        data = api.host(ip)  # :contentReference[oaicite:4]{index=4}
        return data, ""
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def rdap_lookup(ip: str) -> Tuple[Dict[str, Any], str]:
    """
    Returns (rdap_result, error_string).
    """
    try:
        obj = IPWhois(ip)
        # Recommended method by ipwhois docs :contentReference[oaicite:5]{index=5}
        rdap = obj.lookup_rdap(depth=1)
        return rdap, ""
    except IPDefinedError as e:
        # RFC-defined ranges (private, loopback, etc.)
        return {}, f"IPDefinedError: {e}"
    except HTTPLookupError as e:
        return {}, f"HTTPLookupError: {e}"
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def extract_rdap_owner_hint(rdap: Dict[str, Any]) -> str:
    """
    Best-effort extraction of an "owner" from RDAP objects.
    ipwhois RDAP result commonly contains:
      - 'network': {'name', ...}
      - 'asn', 'asn_description', 'asn_cidr', 'asn_registry', 'asn_country_code'
      - 'objects': dict of entity-handle -> {'roles': [...], 'contact': {...}}
    We prefer objects with roles suggesting registrant/holder; then fall back.
    """
    objects = rdap.get("objects") or {}
    if not isinstance(objects, dict):
        return ""

    preferred_roles = ("registrant", "holder", "registrar", "administrative", "technical", "abuse")
    candidates: List[Tuple[int, str]] = []

    for _handle, obj in objects.items():
        if not isinstance(obj, dict):
            continue
        roles = obj.get("roles") or []
        if not isinstance(roles, list):
            roles = []

        # score: lower is better
        score = 999
        for i, r in enumerate(preferred_roles):
            if r in roles:
                score = min(score, i)

        contact = obj.get("contact") or {}
        if not isinstance(contact, dict):
            contact = {}

        # Try org/name fields in plausible order
        name = (
            contact.get("name")
            or contact.get("organization")
            or contact.get("org")
            or contact.get("company")
        )
        if isinstance(name, dict):
            # sometimes vCard-like nested structures
            name = name.get("value") or name.get("text")

        owner = _clean(name)
        if owner:
            candidates.append((score, owner))

    if candidates:
        candidates.sort(key=lambda x: (x[0], len(x[1])))
        return candidates[0][1]

    # fallback: network name, ASN description
    net = rdap.get("network") or {}
    net_name = _clean(net.get("name")) if isinstance(net, dict) else ""
    if net_name:
        return net_name

    asn_desc = _clean(rdap.get("asn_description"))
    return asn_desc


def synthesize_owner(rdap_owner_hint: str, shodan_org: str, rdap_net_name: str, asn_desc: str) -> str:
    """
    Conservative priority: RDAP registrant-like hint > Shodan org > RDAP network name > ASN description.
    """
    for v in (rdap_owner_hint, shodan_org, rdap_net_name, asn_desc):
        v = _clean(v)
        if v:
            return v
    return ""


def build_row(ip: str, shodan_data: Dict[str, Any], shodan_err: str, rdap: Dict[str, Any], rdap_err: str) -> ResultRow:
    # Shodan fields (common keys: org, isp, asn, country_name, city, hostnames, domains, tags, last_update) :contentReference[oaicite:6]{index=6}
    sh_org = _clean(shodan_data.get("org"))
    sh_isp = _clean(shodan_data.get("isp"))
    sh_asn = _clean(shodan_data.get("asn"))
    sh_country = _clean(shodan_data.get("country_name"))
    sh_city = _clean(shodan_data.get("city"))
    sh_hostnames = _clean(shodan_data.get("hostnames"))
    sh_domains = _clean(shodan_data.get("domains"))
    sh_tags = _clean(shodan_data.get("tags"))
    sh_last_update = _clean(shodan_data.get("last_update"))

    # RDAP fields (ipwhois provides these at top-level + network dict) :contentReference[oaicite:7]{index=7}
    rd_asn = _clean(rdap.get("asn"))
    rd_asn_desc = _clean(rdap.get("asn_description"))
    rd_asn_cidr = _clean(rdap.get("asn_cidr"))
    rd_asn_reg = _clean(rdap.get("asn_registry"))
    rd_country = _clean(rdap.get("asn_country_code"))

    net = rdap.get("network") if isinstance(rdap.get("network"), dict) else {}
    rd_net_name = _clean(net.get("name")) if isinstance(net, dict) else ""

    rd_owner_hint = extract_rdap_owner_hint(rdap)

    owner_best = synthesize_owner(rd_owner_hint, sh_org, rd_net_name, rd_asn_desc)

    return ResultRow(
        ip=ip,
        owner_best=owner_best,

        rdap_network_name=rd_net_name,
        rdap_asn=rd_asn,
        rdap_asn_description=rd_asn_desc,
        rdap_asn_cidr=rd_asn_cidr,
        rdap_asn_registry=rd_asn_reg,
        rdap_country=rd_country,
        rdap_owner_hint=rd_owner_hint,

        shodan_org=sh_org,
        shodan_isp=sh_isp,
        shodan_asn=sh_asn,
        shodan_country=sh_country,
        shodan_city=sh_city,
        shodan_hostnames=sh_hostnames,
        shodan_domains=sh_domains,
        shodan_tags=sh_tags,
        shodan_last_update=sh_last_update,

        shodan_error=_clean(shodan_err),
        rdap_error=_clean(rdap_err),
    )


def write_csv(path: str, rows: List[ResultRow]) -> None:
    fieldnames = list(asdict(rows[0]).keys()) if rows else [f.name for f in ResultRow.__dataclass_fields__.values()]  # type: ignore
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_json(path: str, rows: List[ResultRow]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in rows], f, ensure_ascii=False, indent=2)


def main() -> int:
    p = argparse.ArgumentParser(description="Enrich IPs with Shodan + RDAP/WHOIS owner hints.")
    p.add_argument("-i", "--input", required=True, help="Input file containing IPs (one per line).")
    p.add_argument("-o", "--output", required=True, help="Output CSV path.")
    p.add_argument("--json", default="", help="Optional output JSON path.")
    p.add_argument("--no-shodan", action="store_true", help="Skip Shodan lookups (RDAP only).")
    p.add_argument("--shodan-key", default="", help="Shodan API key (or set SHODAN_API_KEY env var).")
    p.add_argument("--shodan-min-interval", type=float, default=1.0, help="Minimum seconds between Shodan calls.")
    args = p.parse_args()

    ips = read_ips(args.input)
    if not ips:
        print("[!] No valid IPs found in input.", file=sys.stderr)
        return 2

    api_key = args.shodan_key or os.environ.get("SHODAN_API_KEY", "")
    use_shodan = (not args.no_shodan)

    api = None
    if use_shodan:
        if shodan is None:
            print("[!] Python 'shodan' library not installed. Run: pip install shodan", file=sys.stderr)
            return 2
        if not api_key:
            print("[!] Missing Shodan API key. Set SHODAN_API_KEY or pass --shodan-key.", file=sys.stderr)
            return 2
        api = shodan.Shodan(api_key)

    rows: List[ResultRow] = []
    total = len(ips)

    for idx, ip in enumerate(ips, start=1):
        print(f"[{idx}/{total}] {ip}", file=sys.stderr)

        # RDAP
        rdap, rdap_err = rdap_lookup(ip)

        # Shodan
        sh_data: Dict[str, Any] = {}
        sh_err = ""
        if use_shodan and api is not None:
            sh_data, sh_err = shodan_lookup(api, ip, min_interval_s=args.shodan_min_interval)

        row = build_row(ip, sh_data, sh_err, rdap, rdap_err)
        rows.append(row)

    write_csv(args.output, rows)
    if args.json:
        write_json(args.json, rows)

    print(f"[+] Wrote {len(rows)} rows to: {args.output}", file=sys.stderr)
    if args.json:
        print(f"[+] Wrote JSON to: {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
