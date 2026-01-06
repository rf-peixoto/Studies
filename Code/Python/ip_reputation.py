#!/usr/bin/env python3

"""
broad_ip_reputation_sorted_geo.py

- Matches IPv4s against multiple threat-intel feeds (broad coverage).
- Enriches results with ISP + geolocation using IP-API Batch endpoint. :contentReference[oaicite:2]{index=2}
- Outputs CSV sorted: "listed" first, then "unknown"; within each group sort by IP.

Talos note:
- Include Cisco Talos/Snort list via --talos-file (local ingestion), because automated download is often gated.

Usage:
  python3 broad_ip_reputation_sorted_geo.py --input ips.txt --output results.csv
  python3 broad_ip_reputation_sorted_geo.py --input ips.txt --output results.csv --listed-only-out listed.csv
  python3 broad_ip_reputation_sorted_geo.py --input ips.txt --output results.csv --talos-file snort_ip_block_list.txt
  python3 broad_ip_reputation_sorted_geo.py --input ips.txt --output results.csv --no-default-feeds --feed "TAG=https://example/list.txt"
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.request import Request, urlopen

# Broad set (FireHOL mirrored netsets/ipsets). FireHOL provides curated aggregation levels. :contentReference[oaicite:3]{index=3}
DEFAULT_FEEDS = [
    ("FIREHOL_LEVEL1", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level1.netset"),
    ("FIREHOL_LEVEL2", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level2.netset"),
    ("FIREHOL_LEVEL3", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level3.netset"),
    ("FIREHOL_LEVEL4", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level4.netset"),
    ("FIREHOL_WEBSERVER", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_webserver.netset"),
    ("FIREHOL_WEBCLIENT", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_webclient.netset"),
    ("FIREHOL_PROXIES", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_proxies.netset"),
    ("FIREHOL_ANONYMOUS", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_anonymous.netset"),
    ("FEODO_BADIPS", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/feodo_badips.ipset"),
    ("BLOCKLIST_DE_BRUTEFORCE", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/blocklist_de_bruteforce.ipset"),
    ("BLOCKLIST_DE_SIP", "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/blocklist_de_sip.ipset"),
]


@dataclass
class RangeIndex:
    ranges: List[Tuple[int, int, str]]  # (start, end, tag)

    def contains(self, ip_int: int) -> List[str]:
        lo, hi = 0, len(self.ranges) - 1
        hits: List[str] = []

        while lo <= hi:
            mid = (lo + hi) // 2
            start, end, tag = self.ranges[mid]
            if ip_int < start:
                hi = mid - 1
            elif ip_int > end:
                lo = mid + 1
            else:
                i = mid
                while i >= 0 and self.ranges[i][0] <= ip_int <= self.ranges[i][1]:
                    hits.append(self.ranges[i][2])
                    i -= 1
                i = mid + 1
                while i < len(self.ranges) and self.ranges[i][0] <= ip_int <= self.ranges[i][1]:
                    hits.append(self.ranges[i][2])
                    i += 1
                break

        seen = set()
        out: List[str] = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                out.append(h)
        return out


def download_text(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": "broad_ip_reputation/2.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def cache_get(cache_dir: str, tag: str, url: str, refresh_hours: int) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    safe = tag.replace("/", "_")
    path = os.path.join(cache_dir, f"{safe}.txt")
    meta = os.path.join(cache_dir, f"{safe}.meta.json")

    now = time.time()
    if os.path.exists(path) and os.path.exists(meta):
        try:
            with open(meta, "r", encoding="utf-8") as f:
                m = json.load(f)
            age = now - float(m.get("ts", 0))
            if age < refresh_hours * 3600:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass

    text = download_text(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"ts": now, "url": url}, f)
    return text


def parse_ip_or_cidr(token: str) -> Optional[ipaddress.IPv4Network]:
    token = token.strip()
    if not token:
        return None
    try:
        if "/" in token:
            net = ipaddress.ip_network(token, strict=False)
        else:
            ip = ipaddress.ip_address(token)
            net = ipaddress.ip_network(f"{ip}/32", strict=False)
        return net if isinstance(net, ipaddress.IPv4Network) else None
    except Exception:
        return None


def parse_feed_text(text: str) -> List[ipaddress.IPv4Network]:
    nets: List[ipaddress.IPv4Network] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        for sep in ("#", ";"):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
        if not line:
            continue
        token = line.split()[0]
        net = parse_ip_or_cidr(token)
        if net:
            nets.append(net)
    return nets


def build_ranges(nets: Iterable[ipaddress.IPv4Network], tag: str) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    for net in nets:
        out.append((int(net.network_address), int(net.broadcast_address), tag))
    return out


def read_ips(path: str) -> List[str]:
    ips: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            s = s.split(",", 1)[0].strip()
            try:
                ip = ipaddress.ip_address(s)
                if isinstance(ip, ipaddress.IPv4Address):
                    ips.append(str(ip))
            except Exception:
                continue
    return ips


def ip_to_int(ip: str) -> int:
    return int(ipaddress.ip_address(ip))


# ---------- IP-API batch enrichment ----------
# Docs: /batch supports custom fields and returns per-item status/message/query etc. :contentReference[oaicite:4]{index=4}
def ipapi_batch_lookup(ips: List[str], batch_size: int = 100, sleep_s: float = 1.5) -> Dict[str, Dict[str, object]]:
    """
    Returns dict ip -> enrichment dict
    Uses http://ip-api.com/batch (HTTP is what their docs show; the free endpoint is commonly HTTP). :contentReference[oaicite:5]{index=5}
    """
    # Fields chosen to resemble your original script output:
    # query, country, regionName, city, lat, lon, isp, org, as, asname
    fields = "status,message,query,country,regionName,city,lat,lon,isp,org,as,asname"
    url = f"http://ip-api.com/batch?fields={fields}"

    out: Dict[str, Dict[str, object]] = {}
    headers = {
        "User-Agent": "broad_ip_reputation/2.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for i in range(0, len(ips), batch_size):
        chunk = ips[i : i + batch_size]
        data = json.dumps(chunk).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=60) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
            arr = json.loads(payload)
            if isinstance(arr, list):
                for item in arr:
                    ip = item.get("query")
                    if ip:
                        out[ip] = item
        except Exception:
            # If the service is blocked in your environment, keep going (no enrichment rather than failure).
            for ip in chunk:
                out.setdefault(ip, {"status": "fail", "message": "ip-api lookup failed", "query": ip})

        time.sleep(sleep_s)

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input file with IPv4s")
    ap.add_argument("--output", required=True, help="CSV output (all IPs; sorted)")
    ap.add_argument("--listed-only-out", default="", help="Optional CSV output (hits only; sorted)")
    ap.add_argument("--cache-dir", default=".cache_ipfeeds", help="Cache directory for feed downloads")
    ap.add_argument("--refresh-hours", type=int, default=12, help="Feed cache refresh window (hours)")
    ap.add_argument("--no-default-feeds", action="store_true", help="Disable default broad feed set")
    ap.add_argument("--feed", action="append", default=[], help='Add custom feed "TAG=URL" (repeatable)')
    ap.add_argument("--talos-file", default="", help="Local Talos/Snort list file (IP/CIDR per line)")
    ap.add_argument("--no-geo", action="store_true", help="Disable IP-API geo/ISP enrichment")
    ap.add_argument("--ipapi-sleep", type=float, default=1.5, help="Sleep between IP-API batch calls")
    ap.add_argument("--ipapi-batch-size", type=int, default=100, help="IP-API batch size (<=100 recommended)")
    args = ap.parse_args()

    ips = read_ips(args.input)
    if not ips:
        print("No valid IPv4 addresses found in input.")
        return 2

    feeds: List[Tuple[str, str]] = []
    if not args.no_default_feeds:
        feeds.extend(DEFAULT_FEEDS)

    for item in args.feed:
        if "=" not in item:
            print(f"Invalid --feed: {item} (expected TAG=URL)")
            return 2
        tag, url = item.split("=", 1)
        tag, url = tag.strip(), url.strip()
        if not tag or not url:
            print(f"Invalid --feed: {item}")
            return 2
        feeds.append((tag, url))

    print(f"Loaded {len(ips)} IPv4s.")
    print(f"Configured remote feeds: {len(feeds)}")
    if args.talos_file:
        print("Talos local feed ingestion: enabled.")
    if args.no_geo:
        print("Geo/ISP enrichment: disabled.")
    else:
        print("Geo/ISP enrichment: enabled (IP-API batch).")

    # Download + parse feeds
    ranges: List[Tuple[int, int, str]] = []

    for tag, url in feeds:
        try:
            text = cache_get(args.cache_dir, tag, url, args.refresh_hours)
            nets = parse_feed_text(text)
            ranges.extend(build_ranges(nets, tag))
            print(f"  - {tag}: {len(nets)} entries")
        except Exception as e:
            print(f"  - {tag}: ERROR ({e})")

    if args.talos_file:
        try:
            with open(args.talos_file, "r", encoding="utf-8") as f:
                text = f.read()
            nets = parse_feed_text(text)
            ranges.extend(build_ranges(nets, "CISCO_TALOS_SNORT_SAMPLE"))
            print(f"  - CISCO_TALOS_SNORT_SAMPLE (local): {len(nets)} entries")
        except Exception as e:
            print(f"  - CISCO_TALOS_SNORT_SAMPLE (local): ERROR ({e})")

    if not ranges:
        print("No feed data loaded. Check URLs/connectivity or Talos file path.")
        return 2

    ranges.sort(key=lambda x: (x[0], x[1], x[2]))
    index = RangeIndex(ranges=ranges)

    # First pass: compute hits per IP
    rows: List[Dict[str, object]] = []
    for ip in ips:
        ip_int = ip_to_int(ip)
        hits = index.contains(ip_int)
        label = "listed" if hits else "unknown"
        rows.append(
            {
                "ip": ip,
                "ip_int": ip_int,  # for sorting only
                "label": label,
                "hits": "|".join(hits),
                "hit_count": len(hits),
            }
        )

    # Enrichment pass (ISP/geo)
    enrich: Dict[str, Dict[str, object]] = {}
    if not args.no_geo:
        enrich = ipapi_batch_lookup(
            ips=list({r["ip"] for r in rows}),
            batch_size=max(1, min(100, args.ipapi_batch_size)),
            sleep_s=max(0.0, args.ipapi_sleep),
        )

    # Add enrichment fields to each row
    for r in rows:
        e = enrich.get(r["ip"], {})
        # If lookup failed or geo disabled, keep empty strings
        r["country"] = e.get("country", "")
        r["region"] = e.get("regionName", "")
        r["city"] = e.get("city", "")
        r["lat"] = e.get("lat", "")
        r["lon"] = e.get("lon", "")
        r["isp"] = e.get("isp", "")
        r["org"] = e.get("org", "")
        r["asn"] = e.get("as", "")
        r["asname"] = e.get("asname", "")
        r["geo_status"] = e.get("status", "")
        r["geo_message"] = e.get("message", "")

    # Sort: IPs with results first, then by IP
    # (If you prefer "most hits first", change key to (-hit_count, ip_int).)
    rows.sort(key=lambda r: (0 if r["label"] == "listed" else 1, r["ip_int"]))

    out_fields = [
        "ip",
        "label",
        "hits",
        "hit_count",
        "country",
        "region",
        "city",
        "lat",
        "lon",
        "isp",
        "org",
        "asn",
        "asname",
        "geo_status",
        "geo_message",
    ]

    # Write all results
    with open(args.output, "w", newline="", encoding="utf-8") as f_all:
        w_all = csv.DictWriter(f_all, fieldnames=out_fields)
        w_all.writeheader()
        for r in rows:
            w_all.writerow({k: r.get(k, "") for k in out_fields})

    # Write only listed (if requested) — also sorted (inherits ordering)
    if args.listed_only_out:
        with open(args.listed_only_out, "w", newline="", encoding="utf-8") as f_lst:
            w_lst = csv.DictWriter(f_lst, fieldnames=out_fields)
            w_lst.writeheader()
            for r in rows:
                if r["label"] == "listed":
                    w_lst.writerow({k: r.get(k, "") for k in out_fields})

    listed = sum(1 for r in rows if r["label"] == "listed")
    print(f"Done. Listed: {listed}/{len(rows)}")
    print(f"All results (sorted): {args.output}")
    if args.listed_only_out:
        print(f"Listed-only (sorted): {args.listed_only_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
