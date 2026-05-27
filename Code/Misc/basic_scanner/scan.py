#!/usr/bin/env python3
"""
Small own-domain recon scanner.

Pipeline:
  1. Validate in-scope domains from an input file.
  2. Enumerate subdomains with assetfinder, subfinder, and optionally crt.sh.
  3. Resolve DNS records: A, AAAA, MX, TXT, CNAME, NS, CAA.
  4. Enrich IPs with PTR, Shodan InternetDB, and optional ASN/RDAP data.
  5. Probe live HTTP(S) targets with ProjectDiscovery httpx using JSONL output.
  6. Optionally run nuclei with JSONL output.
  7. Write timestamped history, latest snapshot, metadata, and a lightweight diff.

The script is intentionally defensive: it avoids shell=True, validates domain input,
keeps per-scan metadata, and writes structured output suitable for later automation.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import re
import shutil
import socket
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiohttp

try:
    import aiodns  # type: ignore
except ImportError:  # optional dependency
    aiodns = None

try:
    from ipwhois import IPWhois  # type: ignore
except ImportError:  # optional dependency
    IPWhois = None


# ---------------------------- DEFAULT CONFIGURATION -------------------------
DEFAULT_OUTPUT_DIR = "scan_results"
DEFAULT_RESOLVE_CONCURRENCY = 50
DEFAULT_SHODAN_CONCURRENCY = 20
DEFAULT_DOMAIN_CONCURRENCY = 1
DEFAULT_HTTP_TIMEOUT = 15
DEFAULT_DNS_TIMEOUT = 8
DEFAULT_NUCLEI_SEVERITIES = "low,medium,high,critical"
DEFAULT_NUCLEI_RATE_LIMIT = 25
DEFAULT_HTTPX_THREADS = 50
DEFAULT_RETRIES = 3

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
COMMENT_PREFIXES = ("#", ";")
DNS_RECORD_TYPES = ("A", "AAAA", "MX", "TXT", "CNAME", "NS", "CAA")
NUCLEI_SEVERITY_KEYS = ("info", "low", "medium", "high", "critical", "unknown")


@dataclass(frozen=True)
class Tool:
    name: str
    path: str | None
    version: str | None


@dataclass
class ShodanEntry:
    ports: list[int]
    vulns: list[str]
    cpes: list[str]
    tags: list[str]
    hostnames: list[str]


@dataclass
class ScanStats:
    domain: str
    started_at_utc: str
    finished_at_utc: str | None = None
    duration_seconds: float | None = None
    subdomains_total: int = 0
    resolved_hosts_total: int = 0
    unique_ipv4_total: int = 0
    unique_ipv6_total: int = 0
    unique_ips_total: int = 0
    dns_hosts_with_ipv6: int = 0
    shodan_ips_with_ports: int = 0
    shodan_total_ports: int = 0
    shodan_vulns_total: int = 0
    shodan_cpes_total: int = 0
    shodan_tags_total: int = 0
    live_targets_total: int = 0
    nuclei_findings_total: int = 0
    nuclei_info: int = 0
    nuclei_low: int = 0
    nuclei_medium: int = 0
    nuclei_high: int = 0
    nuclei_critical: int = 0
    nuclei_unknown: int = 0
    errors: list[str] | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp_for_path() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_domain_dir_name(domain: str) -> str:
    return domain.replace("/", "_").replace("\\", "_")


def normalize_domain(raw: str) -> str | None:
    value = raw.strip().lower().rstrip(".")
    if not value or value.startswith(COMMENT_PREFIXES):
        return None
    forbidden = ("://", "/", "\\", "*", " ", "\t", "&", "|", ";", "`", "$", "(", ")", "<", ">")
    if any(token in value for token in forbidden):
        return None
    if not DOMAIN_RE.match(value):
        return None
    return value


def load_domains(path: Path) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith(COMMENT_PREFIXES):
            continue
        domain = normalize_domain(stripped)
        if domain is None:
            rejected.append(stripped)
            continue
        if domain not in seen:
            accepted.append(domain)
            seen.add(domain)
    return accepted, rejected


def find_tool(name: str, script_dir: Path) -> str | None:
    local = script_dir / name
    if local.is_file() and local.stat().st_mode & 0o111:
        return str(local)
    return shutil.which(name)


async def run_exec(args: list[str], *, timeout: int | None = None) -> tuple[int, list[str], str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return 124, [], f"timeout after {timeout}s"
        return proc.returncode or 0, stdout.decode(errors="replace").splitlines(), stderr.decode(errors="replace").strip()
    except FileNotFoundError:
        return 127, [], f"binary not found: {args[0]}"
    except Exception as exc:
        return 1, [], f"{type(exc).__name__}: {exc}"


async def tool_version(path: str | None, name: str) -> str | None:
    if not path:
        return None
    args_by_name = {
        "assetfinder": [path, "--version"],
        "subfinder": [path, "-version"],
        "nuclei": [path, "-version"],
        "httpx": [path, "-version"],
    }
    code, stdout, stderr = await run_exec(args_by_name.get(name, [path, "--version"]), timeout=8)
    text = "\n".join(stdout).strip() or stderr.strip()
    if code == 0 and text:
        return text.splitlines()[0][:240]
    return None


def filter_in_scope(candidates: Iterable[str], root_domain: str) -> list[str]:
    results: set[str] = set()
    suffix = f".{root_domain}"
    for item in candidates:
        value = item.strip().lower().rstrip(".")
        if not value:
            continue
        if value.startswith("*." ):
            value = value[2:]
        if normalize_domain(value) is None:
            continue
        if value == root_domain or value.endswith(suffix):
            results.add(value)
    results.add(root_domain)
    return sorted(results)


async def http_get_json_with_retries(session: aiohttp.ClientSession, url: str, *, timeout: int, retries: int, errors: list[str], label: str) -> Any | None:
    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status in {429, 500, 502, 503, 504} and attempt < retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
                    continue
                if resp.status not in {404}:
                    errors.append(f"{label} returned HTTP {resp.status} for {url}")
                return None
        except Exception as exc:
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 10))
                continue
            errors.append(f"{label} failed for {url}: {type(exc).__name__}: {exc}")
    return None


async def enumerate_crtsh(session: aiohttp.ClientSession, domain: str, errors: list[str], timeout: int, retries: int) -> list[str]:
    url = f"https://crt.sh/?q=%.{domain}&output=json"
    data = await http_get_json_with_retries(session, url, timeout=timeout, retries=retries, errors=errors, label="crt.sh")
    if not isinstance(data, list):
        return []
    names: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        for name in str(entry.get("name_value", "")).splitlines():
            cleaned = name.strip().lower().rstrip(".")
            if cleaned.startswith("*." ):
                cleaned = cleaned[2:]
            names.add(cleaned)
    return sorted(names)


async def enumerate_subdomains(domain: str, tools: dict[str, Tool], errors: list[str], args: argparse.Namespace) -> list[str]:
    tasks: list[tuple[str, asyncio.Future | asyncio.Task]] = []
    assetfinder = tools["assetfinder"].path
    if assetfinder:
        tasks.append(("assetfinder", asyncio.create_task(run_exec([assetfinder, "--subs-only", domain], timeout=900))))
    subfinder = tools["subfinder"].path
    if subfinder:
        tasks.append(("subfinder", asyncio.create_task(run_exec([subfinder, "-d", domain, "-silent"], timeout=900))))

    raw_lines: list[str] = []
    if tasks:
        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                errors.append(f"{name} crashed: {type(result).__name__}: {result}")
                continue
            code, stdout, stderr = result
            if code != 0:
                errors.append(f"{name} failed with exit code {code}: {stderr[:300]}")
            raw_lines.extend(stdout)
    else:
        errors.append("No binary subdomain enumeration tool available: assetfinder/subfinder not found.")

    if not args.skip_crtsh:
        async with aiohttp.ClientSession() as session:
            raw_lines.extend(await enumerate_crtsh(session, domain, errors, args.http_timeout, args.retries))

    return filter_in_scope(raw_lines, domain)


def _record_value(record: Any, rtype: str) -> str:
    if rtype in {"A", "AAAA"}:
        return str(getattr(record, "host", record))
    if rtype == "PTR":
        return str(getattr(record, "name", record)).rstrip(".")
    if rtype == "MX":
        host = str(getattr(record, "host", record)).rstrip(".")
        priority = getattr(record, "priority", None)
        return f"{priority} {host}" if priority is not None else host
    if rtype == "TXT":
        text = getattr(record, "text", None)
        if isinstance(text, bytes):
            return text.decode(errors="replace")
        if isinstance(text, list):
            return "".join(x.decode(errors="replace") if isinstance(x, bytes) else str(x) for x in text)
        return str(text if text is not None else record)
    if rtype == "CAA":
        flags = getattr(record, "flags", None)
        tag = getattr(record, "tag", None)
        value = getattr(record, "value", None)
        return " ".join(str(x) for x in (flags, tag, value) if x is not None) or str(record)
    for attr in ("host", "name"):
        if hasattr(record, attr):
            return str(getattr(record, attr)).rstrip(".")
    return str(record).rstrip(".")


async def resolve_record_aiodns(hostname: str, rtype: str, resolver: Any, timeout: int) -> list[str]:
    try:
        result = await asyncio.wait_for(resolver.query(hostname, rtype), timeout=timeout)
        if not isinstance(result, list):
            result = [result]
        return sorted({_record_value(r, rtype) for r in result if _record_value(r, rtype)})
    except Exception:
        return []


async def resolve_record_builtin(hostname: str, rtype: str, timeout: int) -> list[str]:
    if rtype not in {"A", "AAAA"}:
        return []
    family = socket.AF_INET if rtype == "A" else socket.AF_INET6
    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(loop.getaddrinfo(hostname, None, family=family, type=0, proto=0, flags=0), timeout=timeout)
        return sorted({item[4][0] for item in infos if item and item[4]})
    except Exception:
        return []


async def resolve_all_records(hostname: str, resolver: Any | None, timeout: int) -> tuple[str, dict[str, list[str]]]:
    records: dict[str, list[str]] = {}
    for rtype in DNS_RECORD_TYPES:
        if resolver is not None:
            records[rtype] = await resolve_record_aiodns(hostname, rtype, resolver, timeout)
        else:
            records[rtype] = await resolve_record_builtin(hostname, rtype, timeout)
    return hostname, records


async def reverse_dns(ip: str, resolver: Any | None, timeout: int) -> tuple[str, list[str]]:
    try:
        parsed = ipaddress.ip_address(ip)
        ptr_name = parsed.reverse_pointer
        if resolver is not None:
            return ip, await resolve_record_aiodns(ptr_name, "PTR", resolver, timeout)
        loop = asyncio.get_running_loop()
        names = await asyncio.wait_for(loop.run_in_executor(None, socket.gethostbyaddr, ip), timeout=timeout)
        return ip, [str(names[0]).rstrip(".")]
    except Exception:
        return ip, []


async def fetch_shodan_data(session: aiohttp.ClientSession, ip: str, timeout: int, retries: int, errors: list[str]) -> tuple[str, ShodanEntry]:
    url = f"https://internetdb.shodan.io/{ip}"
    data = await http_get_json_with_retries(session, url, timeout=timeout, retries=retries, errors=errors, label="Shodan InternetDB")
    if not isinstance(data, dict):
        return ip, ShodanEntry([], [], [], [], [])
    ports = sorted({int(p) for p in data.get("ports", []) if isinstance(p, int) or str(p).isdigit()})
    return ip, ShodanEntry(
        ports=ports,
        vulns=sorted({str(v) for v in data.get("vulns", [])}),
        cpes=sorted({str(v) for v in data.get("cpes", [])}),
        tags=sorted({str(v) for v in data.get("tags", [])}),
        hostnames=sorted({str(v).rstrip(".") for v in data.get("hostnames", [])}),
    )


def asn_lookup_sync(ip: str) -> dict[str, Any]:
    if IPWhois is None:
        return {}
    try:
        result = IPWhois(ip).lookup_rdap(depth=1)
        return {
            "asn": result.get("asn"),
            "asn_description": result.get("asn_description"),
            "asn_cidr": result.get("asn_cidr"),
            "network_name": (result.get("network") or {}).get("name"),
            "network_country": (result.get("network") or {}).get("country"),
        }
    except Exception:
        return {}


async def asn_lookup(ip: str) -> tuple[str, dict[str, Any]]:
    return ip, await asyncio.to_thread(asn_lookup_sync, ip)


def write_lines(path: Path, lines: Iterable[str]) -> None:
    data = "\n".join(lines)
    path.write_text((data + "\n") if data else "", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError:
            continue
    return rows


def count_nonempty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def pick_httpx_url(row: dict[str, Any]) -> str | None:
    for key in ("url", "input"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


async def run_httpx(httpx: str, sub_file: Path, alive_jsonl: Path, alive_txt: Path, alive_json: Path, errors: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    cmd = [
        httpx,
        "-l", str(sub_file),
        "-json",
        "-o", str(alive_jsonl),
        "-status-code",
        "-title",
        "-tech-detect",
        "-follow-redirects",
        "-threads", str(args.httpx_threads),
    ]
    code, _, stderr = await run_exec(cmd, timeout=1200)
    if code != 0:
        errors.append(f"httpx failed with exit code {code}: {stderr[:500]}")
        return []
    rows = read_jsonl(alive_jsonl)
    urls = sorted({u for row in rows if (u := pick_httpx_url(row))})
    write_lines(alive_txt, urls)
    alive_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return rows


async def run_nuclei(nuclei: str, target_file: Path, output_file: Path, severity: str, rate_limit: int, errors: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    cmd = [
        nuclei,
        "-l", str(target_file),
        "-jsonl",
        "-severity", severity,
        "-rate-limit", str(rate_limit),
        "-stats",
        "-etags", "dos",
        "-o", str(output_file),
    ]
    if args.nuclei_templates:
        cmd.extend(["-t", args.nuclei_templates])
    if args.nuclei_tags:
        cmd.extend(["-tags", args.nuclei_tags])
    code, _, stderr = await run_exec(cmd, timeout=None)
    if code != 0:
        errors.append(f"nuclei failed with exit code {code}: {stderr[:700]}")
    return read_jsonl(output_file)


def extract_nuclei_severity(row: dict[str, Any]) -> str:
    info = row.get("info")
    if isinstance(info, dict):
        sev = str(info.get("severity", "unknown")).lower()
    else:
        sev = str(row.get("severity", "unknown")).lower()
    return sev if sev in NUCLEI_SEVERITY_KEYS else "unknown"


def previous_latest_dir(domain_root: Path, current_history: Path) -> Path | None:
    hist_root = domain_root / "history"
    if not hist_root.exists():
        return None
    candidates = sorted([p for p in hist_root.iterdir() if p.is_dir() and p != current_history])
    return candidates[-1] if candidates else None


def load_lines_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()}


def write_diff(history_dir: Path, prev_dir: Path | None) -> dict[str, Any]:
    if prev_dir is None:
        diff = {"previous_scan": None, "subdomains_added": [], "subdomains_removed": [], "nuclei_findings_delta": None}
    else:
        current_subs = load_lines_set(history_dir / "subdomains.txt")
        prev_subs = load_lines_set(prev_dir / "subdomains.txt")
        current_nuclei = count_nonempty_lines(history_dir / "nuclei_results.jsonl")
        prev_nuclei = count_nonempty_lines(prev_dir / "nuclei_results.jsonl")
        diff = {
            "previous_scan": str(prev_dir),
            "subdomains_added": sorted(current_subs - prev_subs),
            "subdomains_removed": sorted(prev_subs - current_subs),
            "nuclei_findings_delta": current_nuclei - prev_nuclei,
            "current_nuclei_findings": current_nuclei,
            "previous_nuclei_findings": prev_nuclei,
        }
    (history_dir / "diff.json").write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")
    return diff


def write_markdown_summary(domain_dir: Path, stats: ScanStats, target_file: Path | None, diff: dict[str, Any]) -> None:
    errors = stats.errors or []
    lines = [
        f"# Scan summary: {stats.domain}",
        "",
        f"- Started UTC: `{stats.started_at_utc}`",
        f"- Finished UTC: `{stats.finished_at_utc}`",
        f"- Duration: `{stats.duration_seconds:.2f}s`" if stats.duration_seconds is not None else "- Duration: `unknown`",
        f"- Subdomains: `{stats.subdomains_total}`",
        f"- Resolved hosts: `{stats.resolved_hosts_total}`",
        f"- Unique IPv4: `{stats.unique_ipv4_total}`",
        f"- Unique IPv6: `{stats.unique_ipv6_total}`",
        f"- Hosts with IPv6: `{stats.dns_hosts_with_ipv6}`",
        f"- IPs with Shodan InternetDB ports: `{stats.shodan_ips_with_ports}`",
        f"- Total Shodan InternetDB ports: `{stats.shodan_total_ports}`",
        f"- Shodan CVEs: `{stats.shodan_vulns_total}`",
        f"- Shodan CPEs: `{stats.shodan_cpes_total}`",
        f"- Shodan tags: `{stats.shodan_tags_total}`",
        f"- Live HTTP targets: `{stats.live_targets_total}`",
        f"- Nuclei findings: `{stats.nuclei_findings_total}`",
        f"  - info: `{stats.nuclei_info}` low: `{stats.nuclei_low}` medium: `{stats.nuclei_medium}` high: `{stats.nuclei_high}` critical: `{stats.nuclei_critical}` unknown: `{stats.nuclei_unknown}`",
    ]
    if target_file:
        lines.append(f"- Nuclei target file: `{target_file.name}`")
    lines.extend(["", "## Diff from previous scan"])
    if diff.get("previous_scan") is None:
        lines.append("- No previous scan available.")
    else:
        lines.append(f"- New subdomains: `{len(diff.get('subdomains_added', []))}`")
        lines.append(f"- Removed subdomains: `{len(diff.get('subdomains_removed', []))}`")
        lines.append(f"- Nuclei findings delta: `{diff.get('nuclei_findings_delta')}`")
    if errors:
        lines.extend(["", "## Errors / warnings"])
        lines.extend(f"- {e}" for e in errors)
    write_lines(domain_dir / "summary.md", lines)


async def scan_domain(domain: str, args: argparse.Namespace, tools: dict[str, Tool]) -> ScanStats:
    start = time.monotonic()
    stats = ScanStats(domain=domain, started_at_utc=utc_now_iso(), errors=[])
    domain_root = Path(args.output_dir) / safe_domain_dir_name(domain)
    history_dir = domain_root / "history" / timestamp_for_path()
    latest_dir = domain_root / "latest"
    history_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[+] Scanning {domain}\n    Output: {history_dir}")

    print("    [1/7] Enumerating subdomains...")
    subdomains = await enumerate_subdomains(domain, tools, stats.errors, args)
    stats.subdomains_total = len(subdomains)
    sub_file = history_dir / "subdomains.txt"
    write_lines(sub_file, subdomains)
    print(f"    Found {len(subdomains)} in-scope hostnames")

    print("    [2/7] Resolving DNS records...")
    resolver = aiodns.DNSResolver(timeout=args.dns_timeout) if aiodns is not None else None
    if resolver is None:
        stats.errors.append("aiodns not installed; only A/AAAA records will be resolved with the built-in resolver.")
    resolve_sem = asyncio.Semaphore(args.resolve_concurrency)

    async def limited_resolve(host: str) -> tuple[str, dict[str, list[str]]]:
        async with resolve_sem:
            return await resolve_all_records(host, resolver, args.dns_timeout)

    dns_records = dict(await asyncio.gather(*(limited_resolve(host) for host in subdomains)))
    host_to_ips: dict[str, list[str]] = {}
    ip_to_subs: dict[str, set[str]] = defaultdict(set)
    for host, records in dns_records.items():
        ips = sorted(set(records.get("A", []) + records.get("AAAA", [])))
        host_to_ips[host] = ips
        for ip in ips:
            ip_to_subs[ip].add(host)

    all_ips = sorted(ip_to_subs.keys(), key=lambda x: (ipaddress.ip_address(x).version, x))
    ipv4 = [ip for ip in all_ips if ipaddress.ip_address(ip).version == 4]
    ipv6 = [ip for ip in all_ips if ipaddress.ip_address(ip).version == 6]
    stats.resolved_hosts_total = sum(1 for ips in host_to_ips.values() if ips)
    stats.unique_ipv4_total = len(ipv4)
    stats.unique_ipv6_total = len(ipv6)
    stats.unique_ips_total = len(all_ips)
    stats.dns_hosts_with_ipv6 = sum(1 for rec in dns_records.values() if rec.get("AAAA"))
    write_lines(history_dir / "ip_addresses.txt", all_ips)
    write_lines(history_dir / "ipv4_addresses.txt", ipv4)
    write_lines(history_dir / "ipv6_addresses.txt", ipv6)
    (history_dir / "host_to_ips.json").write_text(json.dumps(host_to_ips, indent=2, sort_keys=True), encoding="utf-8")
    (history_dir / "dns_records.json").write_text(json.dumps(dns_records, indent=2, sort_keys=True), encoding="utf-8")
    print(f"    Resolved {stats.resolved_hosts_total} hosts to {len(ipv4)} IPv4 and {len(ipv6)} IPv6 addresses")

    print("    [3/7] Running PTR and ASN enrichment...")
    ptr_records: dict[str, list[str]] = {}
    if all_ips:
        ptr_sem = asyncio.Semaphore(args.resolve_concurrency)
        async def limited_ptr(ip: str) -> tuple[str, list[str]]:
            async with ptr_sem:
                return await reverse_dns(ip, resolver, args.dns_timeout)
        ptr_records = dict(await asyncio.gather(*(limited_ptr(ip) for ip in all_ips)))
    (history_dir / "ptr_records.json").write_text(json.dumps(ptr_records, indent=2, sort_keys=True), encoding="utf-8")

    asn_data: dict[str, dict[str, Any]] = {}
    if args.skip_asn:
        stats.errors.append("ASN/RDAP lookup skipped by CLI flag.")
    elif IPWhois is None:
        stats.errors.append("ipwhois not installed; ASN/RDAP lookup skipped.")
    else:
        asn_data = dict(await asyncio.gather(*(asn_lookup(ip) for ip in all_ips))) if all_ips else {}
    (history_dir / "asn_records.json").write_text(json.dumps(asn_data, indent=2, sort_keys=True), encoding="utf-8")

    print("    [4/7] Querying Shodan InternetDB...")
    shodan_data: dict[str, dict[str, Any]] = {}
    if args.skip_shodan:
        stats.errors.append("Shodan InternetDB skipped by CLI flag.")
    else:
        shodan_sem = asyncio.Semaphore(args.shodan_concurrency)
        async with aiohttp.ClientSession() as session:
            async def limited_shodan(ip: str) -> tuple[str, ShodanEntry]:
                async with shodan_sem:
                    return await fetch_shodan_data(session, ip, args.http_timeout, args.retries, stats.errors)
            shodan_results = await asyncio.gather(*(limited_shodan(ip) for ip in all_ips)) if all_ips else []
        for ip, entry in shodan_results:
            row = asdict(entry)
            row["subdomains"] = sorted(ip_to_subs.get(ip, []))
            shodan_data[ip] = row
    stats.shodan_ips_with_ports = sum(1 for entry in shodan_data.values() if entry.get("ports"))
    stats.shodan_total_ports = sum(len(entry.get("ports", [])) for entry in shodan_data.values())
    stats.shodan_vulns_total = sum(len(entry.get("vulns", [])) for entry in shodan_data.values())
    stats.shodan_cpes_total = sum(len(entry.get("cpes", [])) for entry in shodan_data.values())
    stats.shodan_tags_total = sum(len(entry.get("tags", [])) for entry in shodan_data.values())
    (history_dir / "shodan_internetdb.json").write_text(json.dumps(shodan_data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"    Passive ports: {stats.shodan_total_ports}; CVEs: {stats.shodan_vulns_total}; CPEs: {stats.shodan_cpes_total}; tags: {stats.shodan_tags_total}")

    print("    [5/7] Probing live HTTP(S) targets...")
    target_file = sub_file
    alive_jsonl = history_dir / "alive_targets.jsonl"
    alive_json = history_dir / "alive_targets.json"
    alive_txt = history_dir / "alive_targets.txt"
    httpx = tools["httpx"].path
    if args.skip_httpx:
        stats.errors.append("httpx probing skipped by CLI flag.")
        print("    httpx skipped")
    elif httpx:
        rows = await run_httpx(httpx, sub_file, alive_jsonl, alive_txt, alive_json, stats.errors, args)
        stats.live_targets_total = len({u for row in rows if (u := pick_httpx_url(row))})
        if stats.live_targets_total:
            target_file = alive_txt
        print(f"    Live HTTP targets: {stats.live_targets_total}")
    else:
        stats.errors.append("ProjectDiscovery httpx not found; nuclei will use the full subdomain list.")
        print("    httpx not found; using full subdomain list")

    print("    [6/7] Running nuclei...")
    nuclei_output = history_dir / "nuclei_results.jsonl"
    nuclei = tools["nuclei"].path
    if args.skip_nuclei:
        stats.errors.append("nuclei skipped by CLI flag.")
        nuclei_output.write_text("", encoding="utf-8")
        print("    nuclei skipped")
    elif nuclei:
        rows = await run_nuclei(nuclei, target_file, nuclei_output, args.nuclei_severity, args.nuclei_rate_limit, stats.errors, args)
        counts = Counter(extract_nuclei_severity(row) for row in rows)
        stats.nuclei_findings_total = sum(counts.values())
        stats.nuclei_info = counts["info"]
        stats.nuclei_low = counts["low"]
        stats.nuclei_medium = counts["medium"]
        stats.nuclei_high = counts["high"]
        stats.nuclei_critical = counts["critical"]
        stats.nuclei_unknown = counts["unknown"]
        print(f"    Nuclei findings: {stats.nuclei_findings_total} (critical={stats.nuclei_critical}, high={stats.nuclei_high}, medium={stats.nuclei_medium})")
    else:
        stats.errors.append("nuclei not found; vulnerability scan skipped.")
        nuclei_output.write_text("", encoding="utf-8")
        print("    nuclei not found; skipped")

    print("    [7/7] Writing metadata and diff...")
    stats.finished_at_utc = utc_now_iso()
    stats.duration_seconds = round(time.monotonic() - start, 3)
    prev_dir = previous_latest_dir(domain_root, history_dir)
    diff = write_diff(history_dir, prev_dir)
    metadata = {
        "stats": asdict(stats),
        "tools": {name: asdict(tool) for name, tool in tools.items()},
        "config": vars(args),
    }
    (history_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown_summary(history_dir, stats, target_file, diff)
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(history_dir, latest_dir)
    print(f"[+] Finished {domain} in {stats.duration_seconds:.2f}s")
    return stats


async def build_tools(script_dir: Path) -> dict[str, Tool]:
    names = ["assetfinder", "subfinder", "httpx", "nuclei"]
    paths = {name: find_tool(name, script_dir) for name in names}
    versions = await asyncio.gather(*(tool_version(paths[name], name) for name in names))
    tools: dict[str, Tool] = {}
    for name, version in zip(names, versions):
        path = paths[name]
        if name == "httpx" and path and (version is None or "projectdiscovery" not in version.lower() and "httpx" not in version.lower()):
            # Avoid common collision with the unrelated Python httpx CLI.
            path = None
            version = None
        tools[name] = Tool(name=name, path=path, version=version)
    return tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Small own-domain recon scanner")
    parser.add_argument("domains_file", help="Text file with one bare domain per line")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory, default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--domain-concurrency", type=int, default=DEFAULT_DOMAIN_CONCURRENCY, help="How many root domains to scan in parallel; 1 is safest, 3-5 is usually fine for larger authorized inventories")
    parser.add_argument("--resolve-concurrency", type=int, default=DEFAULT_RESOLVE_CONCURRENCY, help="DNS resolver concurrency")
    parser.add_argument("--shodan-concurrency", type=int, default=DEFAULT_SHODAN_CONCURRENCY, help="Shodan InternetDB concurrency")
    parser.add_argument("--http-timeout", type=int, default=DEFAULT_HTTP_TIMEOUT, help="HTTP timeout for Shodan/crt.sh")
    parser.add_argument("--dns-timeout", type=int, default=DEFAULT_DNS_TIMEOUT, help="DNS query timeout")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="HTTP retries for passive APIs")
    parser.add_argument("--skip-crtsh", action="store_true", help="Do not query crt.sh")
    parser.add_argument("--skip-shodan", action="store_true", help="Do not query Shodan InternetDB")
    parser.add_argument("--skip-asn", action="store_true", help="Do not perform ASN/RDAP enrichment")
    parser.add_argument("--skip-httpx", action="store_true", help="Do not probe live HTTP(S) targets before nuclei")
    parser.add_argument("--skip-nuclei", action="store_true", help="Do not run nuclei")
    parser.add_argument("--httpx-threads", type=int, default=DEFAULT_HTTPX_THREADS, help="ProjectDiscovery httpx thread count")
    parser.add_argument("--nuclei-severity", default=DEFAULT_NUCLEI_SEVERITIES, help="Nuclei severities to include")
    parser.add_argument("--nuclei-rate-limit", type=int, default=DEFAULT_NUCLEI_RATE_LIMIT, help="Nuclei request rate limit")
    parser.add_argument("--nuclei-templates", help="Optional nuclei template path passed with -t")
    parser.add_argument("--nuclei-tags", help="Optional nuclei tags passed with -tags, e.g. ssl,misconfig")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    domains_file = Path(args.domains_file)
    if not domains_file.is_file():
        print(f"[-] Domains file not found: {domains_file}", file=sys.stderr)
        return 1
    domains, rejected = load_domains(domains_file)
    if rejected:
        print("[!] Rejected invalid/non-bare domain lines:")
        for item in rejected[:20]:
            print(f"    - {item}")
        if len(rejected) > 20:
            print(f"    ... plus {len(rejected) - 20} more")
    if not domains:
        print("[-] No valid domains provided.", file=sys.stderr)
        return 1
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    tools = await build_tools(script_dir)
    print("[*] Tool discovery:")
    for tool in tools.values():
        print(f"    - {tool.name}: {tool.path if tool.path else 'not found'}")
    if aiodns is None:
        print("[!] aiodns not installed; DNS enrichment will be limited to A/AAAA.")
    if IPWhois is None and not args.skip_asn:
        print("[!] ipwhois not installed; ASN/RDAP enrichment will be skipped.")
    sem = asyncio.Semaphore(max(1, args.domain_concurrency))
    async def limited_scan(domain: str) -> ScanStats:
        async with sem:
            return await scan_domain(domain, args, tools)
    all_start = time.monotonic()
    results = await asyncio.gather(*(limited_scan(domain) for domain in domains))
    elapsed = time.monotonic() - all_start
    aggregate = {
        "finished_at_utc": utc_now_iso(),
        "duration_seconds": round(elapsed, 3),
        "domains_scanned": len(results),
        "subdomains_total": sum(r.subdomains_total for r in results),
        "unique_ips_total": sum(r.unique_ips_total for r in results),
        "unique_ipv4_total": sum(r.unique_ipv4_total for r in results),
        "unique_ipv6_total": sum(r.unique_ipv6_total for r in results),
        "shodan_vulns_total": sum(r.shodan_vulns_total for r in results),
        "nuclei_findings_total": sum(r.nuclei_findings_total for r in results),
        "nuclei_critical": sum(r.nuclei_critical for r in results),
        "nuclei_high": sum(r.nuclei_high for r in results),
        "nuclei_medium": sum(r.nuclei_medium for r in results),
        "domains": [asdict(r) for r in results],
    }
    aggregate_path = Path(args.output_dir) / "last_run_summary.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    print("\n[✓] All scans completed")
    print(f"    Domains scanned: {len(results)}")
    print(f"    Total subdomains: {aggregate['subdomains_total']}")
    print(f"    Total unique IPs: {aggregate['unique_ips_total']} (IPv4={aggregate['unique_ipv4_total']}, IPv6={aggregate['unique_ipv6_total']})")
    print(f"    Shodan CVEs: {aggregate['shodan_vulns_total']}")
    print(f"    Total nuclei findings: {aggregate['nuclei_findings_total']} (critical={aggregate['nuclei_critical']}, high={aggregate['nuclei_high']}, medium={aggregate['nuclei_medium']})")
    print(f"    Summary: {aggregate_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
