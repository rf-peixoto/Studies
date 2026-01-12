#!/usr/bin/env python3
"""
nuclei_rank.py
Parse Nuclei results (preferably -jsonl) and rank "best candidates" by a scoring heuristic.

Usage examples:
  nuclei -l targets.txt -jsonl -o nuclei.jsonl
  python3 nuclei_rank.py -i nuclei.jsonl -n 50

  # from stdin
  nuclei -l targets.txt -jsonl | python3 nuclei_rank.py -n 30

  # export
  python3 nuclei_rank.py -i nuclei.jsonl -n 100 --csv out.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

SEVERITY_WEIGHT = {
    "critical": 100,
    "high": 70,
    "medium": 40,
    "low": 15,
    "info": 3,
    "unknown": 1,
}

# Simple boosts/penalties to help bubble up actionable items
TAG_BOOST = {
    "cve": 20,
    "cvss": 10,
    "rce": 25,
    "sqli": 20,
    "lfi": 18,
    "ssrf": 18,
    "xss": 12,
    "auth-bypass": 22,
    "takeover": 20,
    "exposed-panels": 8,
    "default-login": 14,
    "misconfig": 10,
    "exposure": 10,
    "token": 12,
    "apikey": 12,
    "oauth": 10,
    "jwt": 10,
    "secrets": 14,
    "credentials": 16,
    "kev": 15,  # if you tag this yourself downstream
}

NEGATIVE_TAGS = {
    "tech": -5,
    "detect": -8,
    "fingerprint": -10,
    "enum": -8,
    "info": -5,
}

VERIFIED_HINTS = ("verified", "vuln", "cve", "rce", "sqli", "lfi", "ssrf", "auth", "takeover")

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
CVSS_RE = re.compile(r"\bCVSS[:\s]*([0-9]+(?:\.[0-9]+)?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    template_id: str
    name: str
    severity: str
    host: str
    matched: str
    ip: str
    tags: Tuple[str, ...]
    description: str
    reference: Tuple[str, ...]
    cves: Tuple[str, ...]
    cvss: Optional[float]
    extracted: Tuple[str, ...]
    matcher_name: str
    type: str
    timestamp: str
    raw: Dict[str, Any]


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _tuple_str_list(x: Any) -> Tuple[str, ...]:
    if not x:
        return tuple()
    if isinstance(x, (list, tuple)):
        return tuple(_safe_str(i) for i in x if _safe_str(i))
    return (str(x),)


def _host_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        return p.netloc or p.path.split("/")[0]
    except Exception:
        return url.split("/")[0]


def parse_jsonl(lines: Iterable[str]) -> Iterable[Finding]:
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue

        info = obj.get("info", {}) or {}
        classification = info.get("classification", {}) or {}

        template_id = _safe_str(obj.get("template-id") or obj.get("templateID") or obj.get("template_id"))
        name = _safe_str(info.get("name") or obj.get("name"))
        severity = _safe_str(info.get("severity") or obj.get("severity") or "unknown").lower().strip()

        matched = _safe_str(obj.get("matched-at") or obj.get("matched") or obj.get("url") or obj.get("host"))
        host = _safe_str(obj.get("host") or _host_from_url(matched) or matched)

        ip = _safe_str(obj.get("ip") or "")
        tags = _tuple_str_list(info.get("tags"))
        description = _safe_str(info.get("description") or "")
        reference = _tuple_str_list(info.get("reference"))
        matcher_name = _safe_str(obj.get("matcher-name") or obj.get("matcher") or "")
        ftype = _safe_str(obj.get("type") or "")
        timestamp = _safe_str(obj.get("timestamp") or "")

        # Extracted results (often very useful evidence)
        extracted = _tuple_str_list(obj.get("extracted-results") or obj.get("extracted_results") or obj.get("extracted"))

        # CVEs / CVSS (best-effort)
        cves = set()
        for s in [template_id, name, description, " ".join(reference), " ".join(tags), " ".join(extracted)]:
            for m in CVE_RE.findall(s or ""):
                cves.add(m.upper())

        cvss = None
        # nuclei often places cvss-score or cvss-metrics in classification
        if "cvss-score" in classification:
            try:
                cvss = float(classification.get("cvss-score"))
            except Exception:
                cvss = None
        if cvss is None:
            # sometimes in free text
            m = CVSS_RE.search(" ".join([description, " ".join(extracted)]))
            if m:
                try:
                    cvss = float(m.group(1))
                except Exception:
                    cvss = None

        yield Finding(
            template_id=template_id or "unknown-template",
            name=name or "unknown-name",
            severity=severity or "unknown",
            host=host,
            matched=matched,
            ip=ip,
            tags=tuple(sorted(set(t.lower() for t in tags if t))),
            description=description,
            reference=tuple(reference),
            cves=tuple(sorted(cves)),
            cvss=cvss,
            extracted=tuple(extracted),
            matcher_name=matcher_name,
            type=ftype,
            timestamp=timestamp,
            raw=obj,
        )


TEXT_LINE_RE = re.compile(
    r"^\[(?P<template>[^\]]+)\]\s+\[(?P<severity>[^\]]+)\]\s+(?P<matched>\S+)(?:\s+\[(?P<extra>.+)\])?$"
)

def parse_text(lines: Iterable[str]) -> Iterable[Finding]:
    # Basic support for default nuclei console format:
    # [template] [severity] https://host/path [optional...]
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        m = TEXT_LINE_RE.match(ln)
        if not m:
            continue
        template_id = m.group("template").strip()
        severity = m.group("severity").strip().lower()
        matched = m.group("matched").strip()
        host = _host_from_url(matched)

        yield Finding(
            template_id=template_id,
            name=template_id,
            severity=severity,
            host=host,
            matched=matched,
            ip="",
            tags=tuple(),
            description="",
            reference=tuple(),
            cves=tuple(sorted(set(CVE_RE.findall(ln.upper())))),
            cvss=None,
            extracted=tuple(),
            matcher_name="",
            type="",
            timestamp="",
            raw={"line": ln},
        )


def score_finding(f: Finding) -> int:
    sev = f.severity.lower()
    base = SEVERITY_WEIGHT.get(sev, SEVERITY_WEIGHT["unknown"])

    score = base

    # CVSS: boost proportional (if present)
    if f.cvss is not None:
        score += int(round(min(max(f.cvss, 0.0), 10.0) * 2.5))  # up to +25

    # CVE presence: meaningful boost
    if f.cves:
        score += 18 + min(len(f.cves), 3) * 3

    # Tags: boost for certain classes, penalize pure detection/enum
    for t in f.tags:
        score += TAG_BOOST.get(t, 0)
        score += NEGATIVE_TAGS.get(t, 0)

    # Extracted results are evidence; boost
    if f.extracted:
        score += 8 + min(len(f.extracted), 5)

    # “Verified-ish” hints in template id/name/matcher
    hay = " ".join([f.template_id, f.name, f.matcher_name]).lower()
    if any(h in hay for h in VERIFIED_HINTS):
        score += 6

    # Prefer specific matched URLs over bare hosts
    if f.matched and ("/" in f.matched or "?" in f.matched):
        score += 2

    # De-prioritize info findings unless they have CVE/CVSS/extracts
    if sev == "info" and not (f.cves or (f.cvss is not None) or f.extracted):
        score -= 10

    return score


def dedup_key(f: Finding, mode: str) -> Tuple[str, ...]:
    if mode == "template+host":
        return (f.template_id, f.host)
    if mode == "template+matched":
        return (f.template_id, f.matched)
    if mode == "matched":
        return (f.matched,)
    return (f.template_id, f.host)


def choose_best(existing: Tuple[Finding, int], candidate: Tuple[Finding, int]) -> Tuple[Finding, int]:
    # Prefer higher score; if tie, prefer one with more evidence
    (f1, s1), (f2, s2) = existing, candidate
    if s2 != s1:
        return (f2, s2) if s2 > s1 else (f1, s1)
    ev1 = (len(f1.cves), 1 if f1.cvss is not None else 0, len(f1.extracted))
    ev2 = (len(f2.cves), 1 if f2.cvss is not None else 0, len(f2.extracted))
    return (f2, s2) if ev2 > ev1 else (f1, s1)


def to_row(f: Finding, s: int) -> Dict[str, Any]:
    return {
        "score": s,
        "severity": f.severity,
        "template_id": f.template_id,
        "name": f.name,
        "host": f.host,
        "matched": f.matched,
        "ip": f.ip,
        "cves": ",".join(f.cves),
        "cvss": f.cvss if f.cvss is not None else "",
        "tags": ",".join(f.tags),
        "matcher": f.matcher_name,
        "extracted": " | ".join(f.extracted[:5]),
    }


def print_ranked(rows: List[Dict[str, Any]]) -> None:
    # Minimal table without third-party deps
    cols = ["score", "severity", "template_id", "host", "matched", "cves", "cvss", "tags"]
    widths = {c: len(c) for c in cols}
    for r in rows:
        for c in cols:
            widths[c] = max(widths[c], len(_safe_str(r.get(c, "")))[:200] and min(len(_safe_str(r.get(c, ""))), 80) or widths[c])

    def clip(s: str, n: int) -> str:
        return s if len(s) <= n else s[: n - 1] + "…"

    header = " | ".join(clip(c, widths[c]).ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        line = " | ".join(clip(_safe_str(r.get(c, "")), widths[c]).ljust(widths[c]) for c in cols)
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", help="Input file (default: stdin).")
    ap.add_argument("-n", "--top", type=int, default=50, help="Show top N findings.")
    ap.add_argument("--format", choices=["auto", "jsonl", "text"], default="auto", help="Input format.")
    ap.add_argument("--dedup", choices=["template+host", "template+matched", "matched", "none"], default="template+host")
    ap.add_argument("--min-sev", choices=["info", "low", "medium", "high", "critical"], default="info")
    ap.add_argument("--csv", help="Write ranked results to CSV file.")
    ap.add_argument("--json", help="Write ranked results to JSON file.")
    args = ap.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            lines = list(f)
    else:
        lines = list(sys.stdin)

    fmt = args.format
    if fmt == "auto":
        # Heuristic: if first non-empty line parses as json -> jsonl
        fmt = "text"
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                json.loads(ln)
                fmt = "jsonl"
            except Exception:
                fmt = "text"
            break

    parser = parse_jsonl if fmt == "jsonl" else parse_text
    findings = list(parser(lines))

    # Filter by min severity
    sev_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    min_lvl = sev_order[args.min_sev]
    findings = [f for f in findings if sev_order.get(f.severity, 0) >= min_lvl]

    scored: List[Tuple[Finding, int]] = [(f, score_finding(f)) for f in findings]

    if args.dedup != "none":
        best_by_key: Dict[Tuple[str, ...], Tuple[Finding, int]] = {}
        for f, s in scored:
            k = dedup_key(f, args.dedup)
            if k in best_by_key:
                best_by_key[k] = choose_best(best_by_key[k], (f, s))
            else:
                best_by_key[k] = (f, s)
        scored = list(best_by_key.values())

    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[: max(args.top, 0)]

    rows = [to_row(f, s) for f, s in scored]
    print_ranked(rows)

    if args.csv:
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["score"])
            w.writeheader()
            for r in rows:
                w.writerow(r)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
