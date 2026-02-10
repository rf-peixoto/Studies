#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import gzip
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set


# -----------------------------
# Input handling
# -----------------------------

def open_maybe_gzip(path: str):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return open(path, "rt", encoding="utf-8", errors="ignore")


def iter_records(path: str) -> Iterable[Dict[str, Any]]:
    """
    Supports:
      - NDJSON (one JSON object per line)  <-- typical Shodan export
      - JSON array of objects
      - Single JSON object
    Robust strategy:
      1) Read first ~128KB and try to decide.
      2) If it looks like an array/object BUT json.loads fails with "Extra data",
         fall back to NDJSON.
    """
    with open_maybe_gzip(path) as f:
        head = f.read(131072)  # 128KB preview
        if not head.strip():
            return

        # Find first non-space char
        m = re.search(r"\S", head)
        if not m:
            return
        first_char = head[m.start()]

        # Case A: likely JSON array/object
        if first_char in ("[", "{"):
            # Try parse the preview as full JSON only if file is small;
            # otherwise, try parsing the full file but handle "Extra data".
            try:
                # Try parsing the FULL file content (but do it safely: only if it is not huge?)
                # We cannot reliably know size for gz streams; so attempt and fall back if fails.
                f.seek(0)
                payload = f.read()
                data = json.loads(payload)
                if isinstance(data, list):
                    for obj in data:
                        if isinstance(obj, dict):
                            yield obj
                    return
                if isinstance(data, dict):
                    yield data
                    return
                # Unknown JSON type -> fall back to NDJSON
            except json.JSONDecodeError as e:
                # "Extra data" strongly indicates NDJSON
                if "Extra data" in str(e):
                    pass
                else:
                    # Could still be NDJSON; fall back regardless
                    pass

        # Case B: NDJSON fallback (one JSON object per line)
        f.seek(0)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


# -----------------------------
# Extraction: "what is running"
# -----------------------------

DEFAULT_NOISE = {
    "hsts", "http/2", "http2", "tls", "ssl", "https", "http",
}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def coerce_cpe_to_readable(cpe: str) -> Optional[str]:
    if not isinstance(cpe, str):
        return None
    cpe = cpe.strip()
    if not cpe:
        return None

    if cpe.startswith("cpe:/"):
        parts = cpe.split(":")
        # cpe:/a:vendor:product:version...
        if len(parts) >= 4:
            vendor = parts[2].strip()
            product = parts[3].strip()
            version = parts[4].strip() if len(parts) >= 5 else ""
            if vendor and product:
                return norm(f"{vendor} {product} {version}")
        return None

    if cpe.startswith("cpe:2.3:"):
        parts = cpe.split(":")
        # cpe:2.3:a:vendor:product:version:...
        if len(parts) >= 6:
            vendor = parts[3].strip()
            product = parts[4].strip()
            version = parts[5].strip()
            if vendor and product:
                return norm(f"{vendor} {product} {version}")
        return None

    return None


def extract_techs_from_record(rec: Dict[str, Any], include_titles: bool) -> Set[str]:
    out: Set[str] = set()

    # Product/version (strong)
    product = rec.get("product")
    version = rec.get("version")
    if isinstance(product, str) and product.strip():
        if isinstance(version, str) and version.strip():
            out.add(norm(f"{product} {version}"))
        else:
            out.add(norm(product))

    # CPEs (strong)
    cpe = rec.get("cpe")
    if isinstance(cpe, str) and cpe.strip():
        readable = coerce_cpe_to_readable(cpe)
        out.add(readable if readable else f"CPE:{cpe.strip()}")
    elif isinstance(cpe, list):
        for item in cpe:
            if isinstance(item, str) and item.strip():
                readable = coerce_cpe_to_readable(item)
                out.add(readable if readable else f"CPE:{item.strip()}")

    # Shodan module (helpful label)
    sh = rec.get("_shodan")
    if isinstance(sh, dict):
        mod = sh.get("module")
        if isinstance(mod, str) and mod.strip():
            out.add(norm(f"module:{mod}"))

    # HTTP (best for CMS/panels)
    http = rec.get("http")
    if isinstance(http, dict):
        server = http.get("server")
        if isinstance(server, str) and server.strip():
            out.add(norm(server))

        comps = http.get("components")
        if isinstance(comps, dict):
            for name, meta in comps.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                name_n = norm(name)
                versions = []
                if isinstance(meta, dict):
                    v = meta.get("versions")
                    if isinstance(v, list):
                        versions = [norm(str(x)) for x in v if str(x).strip()]
                if versions:
                    for ver in versions[:10]:
                        out.add(norm(f"{name_n} {ver}"))
                else:
                    out.add(name_n)

        headers = http.get("headers")
        if isinstance(headers, dict):
            xpb = headers.get("X-Powered-By") or headers.get("x-powered-by")
            if isinstance(xpb, str) and xpb.strip():
                out.add(norm(xpb))

            wa = headers.get("WWW-Authenticate") or headers.get("www-authenticate")
            if isinstance(wa, str) and wa.strip():
                out.add(norm(f"WWW-Authenticate: {wa.strip()[:140]}"))

        if include_titles:
            title = http.get("title")
            if isinstance(title, str) and title.strip():
                out.add(norm(f"Title: {title.strip()[:140]}"))

    # Cleanup
    cleaned = set()
    for t in out:
        if not isinstance(t, str):
            continue
        tt = norm(t)
        if not tt:
            continue
        cleaned.add(tt)
    return cleaned


def is_noise(t: str) -> bool:
    return t.strip().lower() in DEFAULT_NOISE


# -----------------------------
# Main aggregation
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Extract technologies (what is running) from Shodan export JSON/NDJSON (.json/.json.gz).")
    ap.add_argument("-i", "--input", required=True, help="Input Shodan export file (.json or .json.gz).")
    ap.add_argument("--counts-csv", default="tech_counts.csv", help="Output counts CSV.")
    ap.add_argument("--per-ip-csv", default="per_ip.csv", help="Output per-IP CSV.")
    ap.add_argument("--include-titles", action="store_true", help="Include HTTP titles (can be noisy).")
    ap.add_argument("--keep-noise", action="store_true", help="Keep generic tokens like TLS/HTTP/HTTPS.")
    ap.add_argument("--count-per", choices=["ip", "record"], default="ip",
                    help="Count once per IP (default) or per record (banner).")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"Input file not found: {args.input}")

    ip_to_techs = defaultdict(set)  # ip -> set(tech)
    tech_counter = Counter()

    records = 0
    for rec in iter_records(args.input):
        records += 1
        ip = rec.get("ip_str") or rec.get("ip") or ""
        ip = str(ip) if ip is not None else ""

        techs = extract_techs_from_record(rec, include_titles=args.include_titles)
        if not args.keep_noise:
            techs = {t for t in techs if not is_noise(t)}

        if ip:
            ip_to_techs[ip].update(techs)

        if args.count_per == "record":
            for t in techs:
                tech_counter[t] += 1

    if args.count_per == "ip":
        for _ip, techs in ip_to_techs.items():
            for t in techs:
                tech_counter[t] += 1

    # Write counts
    with open(args.counts_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["technology_or_fingerprint", "count"])
        for tech, count in tech_counter.most_common():
            w.writerow([tech, count])

    # Write per IP
    with open(args.per_ip_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ip", "technologies"])
        for ip in sorted(ip_to_techs.keys()):
            w.writerow([ip, "|".join(sorted(ip_to_techs[ip]))])

    print(f"Done. Records processed: {records} | Unique IPs: {len(ip_to_techs)}")
    print(f"Wrote: {args.counts_csv} and {args.per_ip_csv}")


if __name__ == "__main__":
    main()
