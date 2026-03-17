#!/usr/bin/env python3
"""
github_domain_triage.py

Search GitHub code results for exact domain strings, classify findings, and save
one ranked TXT report per domain.

Usage:
    export GITHUB_TOKEN="ghp_xxxxxxxxx"
    python3 github_domain_triage.py --domain example.com
    python3 github_domain_triage.py --file domains.txt
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import http.client
import socket
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


API_BASE = "https://api.github.com"
SEARCH_ENDPOINT = f"{API_BASE}/search/code"
RATE_LIMIT_ENDPOINT = f"{API_BASE}/rate_limit"
REPOS_ENDPOINT = f"{API_BASE}/repos"

DEFAULT_PAGES = 5
DEFAULT_PER_PAGE = 100
DEFAULT_DELAY = 2.0
DEFAULT_MAX_CONTENT_BYTES = 200_000
RESULTS_DIR = Path("results")

SUSPICIOUS_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.env(\..+)?$", re.I), 7, "env-file"),
    (re.compile(r"(^|/)(docker-compose|compose)\.ya?ml$", re.I), 5, "compose-file"),
    (re.compile(r"(^|/)\.github/workflows/.+\.ya?ml$", re.I), 6, "github-actions"),
    (re.compile(r"(^|/)(application|bootstrap)\.(ya?ml|properties)$", re.I), 6, "app-config"),
    (re.compile(r"(^|/)(settings|config|secrets?)\.[a-z0-9._-]+$", re.I), 5, "config-file"),
    (re.compile(r"(^|/)(terraform\.tfvars|.*\.tfvars)$", re.I), 6, "terraform-vars"),
    (re.compile(r"(^|/).+\.tf$", re.I), 4, "terraform"),
    (re.compile(r"(^|/)(Jenkinsfile|jenkinsfile)$", re.I), 5, "jenkinsfile"),
    (re.compile(r"(^|/).+\.(sh|bash|zsh|ps1)$", re.I), 4, "script"),
    (re.compile(r"(^|/).+\.(ya?ml|json|ini|conf|cfg|toml|xml|properties)$", re.I), 3, "structured-config"),
    (re.compile(r"(^|/).+\.(py|js|ts|go|java|rb|php|cs|rs)$", re.I), 2, "source-code"),
    (re.compile(r"(^|/)(README|CHANGELOG|docs?/).*$", re.I), -2, "docs"),
    (re.compile(r"(^|/).+\.(md|rst|txt)$", re.I), -2, "text-doc"),
]

PATH_KEYWORDS = {
    "token": 4,
    "secret": 4,
    "password": 4,
    "passwd": 4,
    "api_key": 4,
    "apikey": 4,
    "auth": 3,
    "authorization": 3,
    "bearer": 3,
    "private_key": 5,
    "client_secret": 5,
    "access_key": 4,
    "secret_key": 4,
    "jwt": 3,
    "cookie": 2,
    "session": 2,
    "webhook": 3,
    "smtp": 2,
    "database": 2,
    "redis": 2,
    "postgres": 2,
    "mysql": 2,
    "mongo": 2,
    "s3": 2,
    "bucket": 2,
    "internal": 3,
    "admin": 3,
    "staging": 3,
    "prod": 3,
    "production": 3,
    "vault": 4,
    "kube": 2,
    "k8s": 2,
    "deploy": 2,
    "infra": 2,
}

DOMAIN_RISK_TERMS = {
    "admin": 3,
    "internal": 3,
    "auth": 3,
    "sso": 3,
    "prod": 3,
    "production": 3,
    "staging": 2,
    "api": 2,
    "jenkins": 3,
    "grafana": 3,
    "kibana": 3,
    "gitlab": 2,
    "vault": 4,
    "db": 3,
    "mysql": 3,
    "postgres": 3,
    "mongo": 3,
    "redis": 3,
    "smtp": 2,
    "storage": 2,
    "s3": 2,
    "backup": 3,
}

CONTENT_KEYWORDS = {
    "token": 4,
    "secret": 4,
    "password": 4,
    "passwd": 4,
    "api_key": 4,
    "apikey": 4,
    "authorization": 4,
    "bearer": 4,
    "private_key": 5,
    "client_secret": 5,
    "access_key": 4,
    "secret_key": 4,
    "jwt": 3,
    "cookie": 2,
    "session": 2,
    "webhook": 3,
    "database_url": 4,
    "redis": 2,
    "postgres": 2,
    "mysql": 2,
    "mongo": 2,
    "smtp": 2,
    "vault": 4,
}

CONTENT_FETCH_CANDIDATE = re.compile(
    r"(^|/)(\.env(\..+)?|docker-compose\.ya?ml|compose\.ya?ml|Jenkinsfile|jenkinsfile|"
    r"application\.(ya?ml|properties)|bootstrap\.(ya?ml|properties)|"
    r".+\.(sh|bash|zsh|ps1|ya?ml|json|ini|conf|cfg|toml|xml|properties|py|js|ts|go|java|rb|php|cs|rs|tf|tfvars))$",
    re.I,
)

NEGATIVE_HINTS = {
    "readme": -2,
    "example": -2,
    "sample": -2,
    "demo": -2,
    "test": -1,
    "docs": -2,
    "changelog": -2,
}

OWNER_TYPE_SCORES = {
    "Organization": 2,
    "User": 0,
}

TIER_THRESHOLDS = [
    ("urgent", 14),
    ("high", 9),
    ("medium", 4),
    ("low", -9999),
]


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    MAGENTA = "\033[35m"


def color(text: str, tone: str) -> str:
    return f"{tone}{text}{C.RESET}"


@dataclass
class RepoMeta:
    full_name: str
    archived: bool = False
    pushed_at: str | None = None
    owner_type: str | None = None
    stargazers_count: int = 0


@dataclass
class Finding:
    domain: str
    html_url: str
    repo_full_name: str
    repo_html_url: str
    repo_owner_type: str | None
    repo_archived: bool
    repo_pushed_at: str | None
    path: str
    sha: str | None = None
    score: int = 0
    tier: str = "low"
    reasons: list[str] = field(default_factory=list)


def eprint(text: str) -> None:
    print(text, file=sys.stderr)


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "domain"


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    return value.strip()


def load_domains(single_domain: str | None, file_path: str | None) -> list[str]:
    domains: list[str] = []

    if single_domain:
        d = normalize_domain(single_domain)
        if d:
            domains.append(d)

    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                d = normalize_domain(raw)
                if d:
                    domains.append(d)

    seen = set()
    deduped = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            deduped.append(d)

    return deduped


def build_headers(token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-domain-triage",
    }


def api_get_json(url: str, headers: dict[str, str], retries: int = 4, backoff: float = 2.0) -> tuple[dict, dict[str, str]]:
    last_error = None

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                return data, dict(resp.headers.items())

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except Exception:
                data = {"message": body or str(e)}

            status = e.code
            if status in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff * attempt)
                last_error = RuntimeError(f"HTTP {status}: {data.get('message', 'Transient API error')}")
                continue

            headers_out = dict(e.headers.items()) if e.headers else {}
            raise RuntimeError(
                f"HTTP {status}: {data.get('message', 'Unknown API error')}|||HEADERS|||{json.dumps(headers_out)}"
            ) from None

        except (http.client.IncompleteRead, urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_error = e
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Transient network/read error after {retries} attempts: {e}") from None

        except json.JSONDecodeError as e:
            last_error = e
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Invalid JSON response after {retries} attempts: {e}") from None

    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def get_rate_limit_status(token: str) -> dict:
    headers = build_headers(token)
    data, _ = api_get_json(RATE_LIMIT_ENDPOINT, headers)
    return data.get("resources", {})


def wait_until_reset(reset_epoch: int, extra_seconds: int = 3) -> None:
    now = int(time.time())
    sleep_for = max(0, reset_epoch - now + extra_seconds)
    if sleep_for > 0:
        print(color("[!] Rate limit reached. Waiting ", C.YELLOW) + color(f"{sleep_for}s", C.BOLD + C.YELLOW))
        time.sleep(sleep_for)


def ensure_bucket_available(token: str, bucket: str) -> None:
    resources = get_rate_limit_status(token)
    info = resources.get(bucket, {})
    remaining = info.get("remaining")
    reset = info.get("reset")
    if isinstance(remaining, int) and remaining <= 0 and isinstance(reset, int):
        wait_until_reset(reset)


def handle_rate_limit_error(token: str, bucket: str, exc: RuntimeError) -> bool:
    msg = str(exc)
    if "HTTP 403" not in msg and "HTTP 429" not in msg:
        return False
    resources = get_rate_limit_status(token)
    info = resources.get(bucket, {})
    remaining = info.get("remaining")
    reset = info.get("reset")
    if isinstance(remaining, int) and remaining <= 0 and isinstance(reset, int):
        wait_until_reset(reset)
        return True
    return False


def build_search_url(domain: str, page: int, per_page: int) -> str:
    params = {
        "q": f"\"{domain}\"",
        "page": page,
        "per_page": per_page,
    }
    return SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def days_since_iso8601(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return None


def path_score(path: str) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    lower = path.lower()

    for pattern, pts, reason in SUSPICIOUS_FILE_PATTERNS:
        if pattern.search(path):
            score += pts
            reasons.append(f"path:{reason}:{pts:+d}")
            break

    for key, pts in PATH_KEYWORDS.items():
        if key in lower:
            score += pts
            reasons.append(f"path-keyword:{key}:{pts:+d}")

    for key, pts in NEGATIVE_HINTS.items():
        if key in lower:
            score += pts
            reasons.append(f"negative-hint:{key}:{pts:+d}")

    return score, reasons


def domain_risk_score(domain: str) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    lower = domain.lower()
    for key, pts in DOMAIN_RISK_TERMS.items():
        if key in lower:
            score += pts
            reasons.append(f"domain-term:{key}:{pts:+d}")
    return score, reasons


def repo_score(meta: RepoMeta) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    owner_pts = OWNER_TYPE_SCORES.get(meta.owner_type or "", 0)
    if owner_pts:
        score += owner_pts
        reasons.append(f"owner-type:{meta.owner_type}:{owner_pts:+d}")

    if meta.archived:
        score -= 3
        reasons.append("repo:archived:-3")

    age_days = days_since_iso8601(meta.pushed_at)
    if age_days is not None:
        if age_days <= 30:
            score += 3
            reasons.append("repo:recent-push:+3")
        elif age_days <= 180:
            score += 1
            reasons.append("repo:active-ish:+1")
        elif age_days > 730:
            score -= 2
            reasons.append("repo:stale:-2")

    return score, reasons


def should_fetch_content(path: str) -> bool:
    return bool(CONTENT_FETCH_CANDIDATE.search(path))


def content_context_score(content: str, domain: str) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    lower = content.lower()

    domain_lower = domain.lower()
    idx = lower.find(domain_lower)
    if idx == -1:
        return 0, []

    start = max(0, idx - 600)
    end = min(len(lower), idx + len(domain_lower) + 600)
    window = lower[start:end]

    for key, pts in CONTENT_KEYWORDS.items():
        if key in window:
            score += pts
            reasons.append(f"content-keyword:{key}:{pts:+d}")

    secret_like_assignments = [
        r"(token|secret|password|passwd|api[_-]?key|client[_-]?secret|access[_-]?key)\s*[:=]\s*['\"]?[a-z0-9_\-\/+=]{8,}",
        r"authorization\s*[:=]\s*['\"]?bearer\s+[a-z0-9\-._~+/]+=*",
        r"private[_-]?key",
    ]
    for pat in secret_like_assignments:
        if re.search(pat, window, re.I):
            score += 5
            reasons.append("content:secret-like-assignment:+5")
            break

    return score, reasons


def finding_tier(score: int) -> str:
    for name, threshold in TIER_THRESHOLDS:
        if score >= threshold:
            return name
    return "low"


def fetch_repo_meta(token: str, repo_full_name: str, cache: dict[str, RepoMeta], delay: float) -> RepoMeta:
    if repo_full_name in cache:
        return cache[repo_full_name]

    ensure_bucket_available(token, "core")
    headers = build_headers(token)
    url = f"{REPOS_ENDPOINT}/{repo_full_name}"

    try:
        data, _ = api_get_json(url, headers)
    except RuntimeError as exc:
        if handle_rate_limit_error(token, "core", exc):
            data, _ = api_get_json(url, headers)
        else:
            data = {}

    meta = RepoMeta(
        full_name=repo_full_name,
        archived=bool(data.get("archived", False)),
        pushed_at=data.get("pushed_at"),
        owner_type=(data.get("owner") or {}).get("type"),
        stargazers_count=int(data.get("stargazers_count") or 0),
    )
    cache[repo_full_name] = meta
    time.sleep(delay)
    return meta


def fetch_file_content(token: str, repo_full_name: str, path: str, ref: str | None, delay: float) -> str | None:
    ensure_bucket_available(token, "core")
    headers = build_headers(token)
    quoted_path = urllib.parse.quote(path)
    url = f"{REPOS_ENDPOINT}/{repo_full_name}/contents/{quoted_path}"
    params = {}
    if ref:
        params["ref"] = ref
        url += "?" + urllib.parse.urlencode(params)

    try:
        data, _ = api_get_json(url, headers)
    except RuntimeError as exc:
        if handle_rate_limit_error(token, "core", exc):
            data, _ = api_get_json(url, headers)
        else:
            return None

    time.sleep(delay)

    if data.get("type") != "file":
        return None

    size = int(data.get("size") or 0)
    if size > DEFAULT_MAX_CONTENT_BYTES:
        return None

    encoding = data.get("encoding")
    content = data.get("content")
    if encoding == "base64" and content:
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None

    download_url = data.get("download_url")
    if download_url:
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "github-domain-triage"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read(DEFAULT_MAX_CONTENT_BYTES + 1)
                if len(raw) > DEFAULT_MAX_CONTENT_BYTES:
                    return None
                return raw.decode("utf-8", errors="replace")
        except Exception:
            return None

    return None


def extract_items(data: dict) -> list[dict]:
    items = data.get("items", [])
    if not isinstance(items, list):
        return []
    return items


def collect_search_hits(token: str, domain: str, pages: int, per_page: int, delay: float) -> list[dict]:
    headers = build_headers(token)
    hits = []
    seen = set()

    print(color(f"\n[>] Searching: ", C.CYAN) + color(domain, C.BOLD + C.CYAN))

    for page in range(1, pages + 1):
        ensure_bucket_available(token, "code_search")
        url = build_search_url(domain, page, per_page)

        try:
            data, _ = api_get_json(url, headers)
        except RuntimeError as exc:
            if handle_rate_limit_error(token, "code_search", exc):
                data, _ = api_get_json(url, headers)
            else:
                print(color(f"  [!] Search failed on page {page}: {exc}", C.RED))
                break

        items = extract_items(data)
        if not items:
            print(color(f"  [-] Page {page}: 0 hits", C.GRAY))
            break

        added = 0
        for item in items:
            html_url = item.get("html_url")
            if not html_url or html_url in seen:
                continue
            seen.add(html_url)
            hits.append(item)
            added += 1

        print(color(f"  [-] Page {page}: ", C.GRAY) + color(f"{added} unique hits", C.GRAY))
        time.sleep(delay)

    return hits


def classify_hits(token: str, domain: str, hits: list[dict], delay: float) -> list[Finding]:
    repo_cache: dict[str, RepoMeta] = {}
    findings: list[Finding] = []

    for item in hits:
        repo = item.get("repository") or {}
        repo_full_name = repo.get("full_name")
        repo_html_url = repo.get("html_url") or ""
        path = item.get("path") or ""
        html_url = item.get("html_url") or ""
        sha = item.get("sha")

        if not repo_full_name or not path or not html_url:
            continue

        meta = fetch_repo_meta(token, repo_full_name, repo_cache, delay)

        score = 0
        reasons = []

        s, r = path_score(path)
        score += s
        reasons.extend(r)

        s, r = domain_risk_score(domain)
        score += s
        reasons.extend(r)

        s, r = repo_score(meta)
        score += s
        reasons.extend(r)

        content_bonus = 0
        content_reasons = []
        if should_fetch_content(path):
            content = fetch_file_content(token, repo_full_name, path, sha, delay)
            if content:
                content_bonus, content_reasons = content_context_score(content, domain)
                score += content_bonus
                reasons.extend(content_reasons)

        tier = finding_tier(score)

        findings.append(
            Finding(
                domain=domain,
                html_url=html_url,
                repo_full_name=repo_full_name,
                repo_html_url=repo_html_url,
                repo_owner_type=meta.owner_type,
                repo_archived=meta.archived,
                repo_pushed_at=meta.pushed_at,
                path=path,
                sha=sha,
                score=score,
                tier=tier,
                reasons=reasons,
            )
        )

    findings.sort(key=lambda x: (-x.score, x.repo_full_name.lower(), x.path.lower()))
    return findings


def summarize_tiers(findings: list[Finding]) -> dict[str, int]:
    counts = {"urgent": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.tier] = counts.get(f.tier, 0) + 1
    return counts


def save_results(domain: str, findings: list[Finding], outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    output_file = outdir / f"{sanitize_filename(domain)}.txt"

    grouped = {"urgent": [], "high": [], "medium": [], "low": []}
    for f in findings:
        grouped.setdefault(f.tier, []).append(f)

    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write(f"Domain: {domain}\n")
        fh.write(f"Generated: {datetime.now().isoformat()}\n")
        fh.write(f"Total findings: {len(findings)}\n\n")

        for tier in ["urgent", "high", "medium", "low"]:
            items = grouped.get(tier, [])
            fh.write(f"==== {tier.upper()} ({len(items)}) ====\n\n")
            for f in items:
                fh.write(f"[score={f.score}] {f.repo_full_name} :: {f.path}\n")
                fh.write(f"URL: {f.html_url}\n")
                fh.write(f"Repo URL: {f.repo_html_url}\n")
                fh.write(f"Owner type: {f.repo_owner_type or 'unknown'}\n")
                fh.write(f"Archived: {f.repo_archived}\n")
                fh.write(f"Last push: {f.repo_pushed_at or 'unknown'}\n")
                fh.write("Reasons:\n")
                for reason in f.reasons[:20]:
                    fh.write(f"  - {reason}\n")
                fh.write("\n")

    return output_file


def print_domain_summary(domain: str, findings: list[Finding], output_file: Path) -> None:
    counts = summarize_tiers(findings)
    unique_repos = len({f.repo_full_name for f in findings})

    print(color("  [=] Findings: ", C.BLUE) + str(len(findings)))
    print(color("  [=] Repositories: ", C.BLUE) + str(unique_repos))
    print(color("  [=] Urgent: ", C.RED) + color(str(counts["urgent"]), C.BOLD + C.RED))
    print(color("  [=] High: ", C.MAGENTA) + color(str(counts["high"]), C.BOLD + C.MAGENTA))
    print(color("  [=] Medium: ", C.YELLOW) + color(str(counts["medium"]), C.BOLD + C.YELLOW))
    print(color("  [=] Low: ", C.GREEN) + color(str(counts["low"]), C.BOLD + C.GREEN))
    print(color("  [+] Saved report: ", C.CYAN) + str(output_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search GitHub for exact domain strings and rank findings for review."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--domain", help="Single domain to search")
    src.add_argument("--file", help="TXT file containing one domain per line")

    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Pages per domain")
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, help="Results per page")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests")
    parser.add_argument("--outdir", default=str(RESULTS_DIR), help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        eprint(color("[!] Missing GITHUB_TOKEN environment variable.", C.RED))
        eprint('    Example: export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"')
        return 1

    domains = load_domains(args.domain, args.file)
    if not domains:
        eprint(color("[!] No valid domains provided.", C.RED))
        return 1

    outdir = Path(args.outdir)
    print(color("[*] Output directory: ", C.BLUE) + str(outdir))
    print(color("[*] Domains: ", C.BLUE) + str(len(domains)))
    print(color("[*] Pages/domain: ", C.BLUE) + str(args.pages))
    print(color("[*] Delay/request: ", C.BLUE) + f"{args.delay:.1f}s")

    for domain in domains:
        try:
            hits = collect_search_hits(
                token=token,
                domain=domain,
                pages=args.pages,
                per_page=args.per_page,
                delay=args.delay,
            )
            findings = classify_hits(
                token=token,
                domain=domain,
                hits=hits,
                delay=args.delay,
            )
            output_file = save_results(domain, findings, outdir)
            print_domain_summary(domain, findings, output_file)
        except KeyboardInterrupt:
            print(color("\n[!] Interrupted by user.", C.RED))
            return 130
        except Exception as exc:
            print(color(f"[!] Error for {domain}: {exc}", C.RED))

    print(color("\n[✓] Done.", C.BOLD + C.GREEN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
