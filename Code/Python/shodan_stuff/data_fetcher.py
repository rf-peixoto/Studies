#!/usr/bin/env python3
import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import shodan  # pip install shodan


def read_ips(path: Path) -> List[str]:
    ips = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ips.append(line)
    # de-dup while preserving order
    seen = set()
    out = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def safe_get(d: Dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def normalize_service(banner: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Shodan 'data' banner into a normalized service record.
    Tries to derive "application" from common fields (product/version/http.server/etc.).
    """
    port = banner.get("port")
    transport = banner.get("transport")  # tcp/udp (if present)
    proto = banner.get("_shodan", {}).get("module")  # protocol/module name

    product = banner.get("product")
    version = banner.get("version")
    cpe = banner.get("cpe")
    if isinstance(cpe, list):
        cpe = ";".join([str(x) for x in cpe])
    elif cpe is not None:
        cpe = str(cpe)

    http_server = safe_get(banner, "http", "server")
    http_title = safe_get(banner, "http", "title")
    tls_cn = safe_get(banner, "ssl", "cert", "subject", "CN")

    # Best-effort application label:
    # Prefer product/version; else HTTP server header; else module/proto.
    app_parts: List[str] = []
    if product:
        app_parts.append(str(product))
        if version:
            app_parts.append(str(version))
    elif http_server:
        app_parts.append(str(http_server))
    elif proto:
        app_parts.append(str(proto))

    application = " ".join(app_parts) if app_parts else None

    return {
        "port": port,
        "transport": transport,
        "protocol": proto,
        "application": application,
        "product": product,
        "version": version,
        "cpe": cpe,
        "http_server": http_server,
        "http_title": http_title,
        "tls_cn": tls_cn,
        "timestamp": banner.get("timestamp"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Query Shodan for IPs and extract ports/services/apps.")
    ap.add_argument("--ips", default="ips.txt", help="Path to ips.txt")
    ap.add_argument("--out", default="out", help="Output directory")
    ap.add_argument("--key", default=None, help="Shodan API key (or set SHODAN_API_KEY env var)")
    ap.add_argument("--sleep", type=float, default=1.1, help="Delay between requests (seconds)")
    args = ap.parse_args()

    api_key = args.key or os.getenv("SHODAN_API_KEY")
    if not api_key:
        raise SystemExit("Missing API key. Provide --key or set SHODAN_API_KEY.")

    ips_path = Path(args.ips)
    out_dir = Path(args.out)
    raw_dir = out_dir / "shodan_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    ips = read_ips(ips_path)
    if not ips:
        raise SystemExit(f"No IPs found in {ips_path}")

    api = shodan.Shodan(api_key)

    summaries: List[Dict[str, Any]] = []
    csv_rows: List[Dict[str, Any]] = []

    for i, ip in enumerate(ips, 1):
        try:
            host: Dict[str, Any] = api.host(ip)  # host lookup
        except shodan.APIError as e:
            summaries.append({"ip": ip, "error": str(e)})
            # Still rate-limit even on errors
            time.sleep(args.sleep)
            continue

        # Save raw response per IP
        (raw_dir / f"{ip}.json").write_text(json.dumps(host, indent=2, sort_keys=True), encoding="utf-8")

        banners = host.get("data", []) if isinstance(host.get("data"), list) else []
        services = [normalize_service(b) for b in banners if isinstance(b, dict)]

        open_ports = sorted({s["port"] for s in services if isinstance(s.get("port"), int)})

        summary = {
            "ip": host.get("ip_str", ip),
            "org": host.get("org"),
            "isp": host.get("isp"),
            "asn": host.get("asn"),
            "country": safe_get(host, "location", "country_name"),
            "city": safe_get(host, "location", "city"),
            "hostnames": host.get("hostnames"),
            "domains": host.get("domains"),
            "os": host.get("os"),
            "open_ports": open_ports,
            "services": services,
        }
        summaries.append(summary)

        # Flatten to CSV
        for s in services:
            csv_rows.append(
                {
                    "ip": summary["ip"],
                    "port": s.get("port"),
                    "transport": s.get("transport"),
                    "protocol": s.get("protocol"),
                    "application": s.get("application"),
                    "product": s.get("product"),
                    "version": s.get("version"),
                    "cpe": s.get("cpe"),
                    "http_server": s.get("http_server"),
                    "http_title": s.get("http_title"),
                    "tls_cn": s.get("tls_cn"),
                    "timestamp": s.get("timestamp"),
                    "org": summary.get("org"),
                    "asn": summary.get("asn"),
                    "country": summary.get("country"),
                    "city": summary.get("city"),
                }
            )

        # Basic progress + rate limiting
        print(f"[{i}/{len(ips)}] {ip}: {len(open_ports)} ports")
        time.sleep(args.sleep)

    # Write combined outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "shodan_summary.json").write_text(
        json.dumps(summaries, indent=2, sort_keys=False),
        encoding="utf-8",
    )

    csv_path = out_dir / "shodan_services.csv"
    fieldnames = [
        "ip", "port", "transport", "protocol", "application", "product", "version", "cpe",
        "http_server", "http_title", "tls_cn", "timestamp", "org", "asn", "country", "city"
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(csv_rows)

    print(f"\nDone. Raw: {raw_dir}/  Summary: {out_dir/'shodan_summary.json'}  CSV: {csv_path}")


if __name__ == "__main__":
    main()
