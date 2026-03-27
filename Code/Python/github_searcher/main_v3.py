bash -lc cat > /mnt/data/wip_main_v3.py <<'PY'
#!/usr/bin/env python3
"""
GitHub domain triage with structured CSV output.

What it does:
- Searches GitHub code search for exact domain strings.
- Scores/classifies live findings.
- Fetches matched blob content correctly via the Git blob API when possible.
- Optionally inspects recent commit diffs for already-matched repositories to find
  deleted or modified historical references without cloning repositories.
- Writes one CSV per domain plus a compact run summary TXT.

Notes:
- History mode is opportunistic, not exhaustive. GitHub does not expose a global
  "search deleted code in commit history" API. This script only inspects recent
  commits from repositories that already matched in live search.
- Classification is triage, not proof.

Usage:
    export GITHUB_TOKEN="ghp_xxx"
    python3 github_domain_triage_v3.py --domain example.com
    python3 github_domain_triage_v3.py --file domains.txt --history-commits 20
"""

from __future__ import annotations

import argparse
import base64
import csv
import http.client
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
DEFAULT_DELAY = 1.5
DEFAULT_HTTP_RETRIES = 4
DEFAULT_TOP_CANDIDATES = 15
DEFAULT_MAX_BLOB_BYTES = 200_000
DEFAULT_HISTORY_COMMITS = 15
DEFAULT_HISTORY_REPOS = 40
DEFAULT_HISTORY_FILES_PER_COMMIT = 300
RESULTS_DIR = Path("results")


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def color(text: str, tone: str) -> str:
    return f"{tone}{text}{C.RESET}"


def safe_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def eprint(text: str) -> None:
    print(text, file=sys.stderr)


def print_progress(current: int, total: int, prefix: str) -> None:
    if total <= 0:
        return
    percent = (current / total) * 100
    msg = (
        f"\r{color(prefix, C.GRAY)} "
        f"{color(f'{current}/{total}', C.BOLD + C.GRAY)} "
        f"{color(f'({percent:5.1f}%)', C.GRAY)}"
    )
    print(msg, end="", flush=True)


@dataclass
class RepoMeta:
    full_name: str
    archived: bool = False
    pushed_at: str | None = None
    owner_type: str | None = None
    stargazers_count: int = 0
    default_branch: str | None = None


@dataclass
class Finding:
    domain: str
    source_type: str  # live | history
    classification: str
    tier: str
    score: int
    tags: list[str]
    link: str
    repo_full_name: str
    path: str | None = None
    commit_sha: str | None = None
    matched_ref: str | None = None
    owner_type: str | None = None
    archived: bool = False
    repo_pushed_at: str | None = None
    notes: str = ""
    evidence: str = ""
    debug_reasons: list[str] = field(default_factory=list)


@dataclass
class Stats:
    live_hits_seen: int = 0
    live_findings: int = 0
    history_repos_scanned: int = 0
    history_commits_scanned: int = 0
    history_findings: int = 0
    repo_meta_failures: int = 0
    blob_fetch_attempts: int = 0
    blob_fetch_success: int = 0
    blob_fetch_failures: int = 0
    history_commit_failures: int = 0
    skipped_items: int = 0
    classification_failures: int = 0


TIER_THRESHOLDS = [
    ("urgent", 15),
    ("high", 10),
    ("medium", 5),
    ("low", -9999),
]

OWNER_TYPE_SCORES = {"Organization": 2, "User": 0}

NEGATIVE_HINTS = {
    "readme": -2,
    "example": -2,
    "sample": -2,
    "demo": -2,
    "test": -1,
    "docs": -2,
    "changelog": -2,
    "fixtures": -1,
    "mock": -1,
}

SUSPICIOUS_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.env(\..+)?$", re.I), 8, "env-file"),
    (re.compile(r"(^|/)(prod|production)\.env$", re.I), 9, "prod-env"),
    (re.compile(r"(^|/)(docker-compose|compose)\.ya?ml$", re.I), 5, "compose-file"),
    (re.compile(r"(^|/)\.github/workflows/.+\.ya?ml$", re.I), 7, "workflow"),
    (re.compile(r"(^|/)(application|bootstrap)\.(ya?ml|properties)$", re.I), 6, "app-config"),
    (re.compile(r"(^|/)(settings|config|secrets?)\.[a-z0-9._-]+$", re.I), 6, "config-file"),
    (re.compile(r"(^|/)(terraform\.tfvars|.*\.tfvars)$", re.I), 7, "terraform-vars"),
    (re.compile(r"(^|/).+\.tf$", re.I), 4, "terraform"),
    (re.compile(r"(^|/)(Jenkinsfile|jenkinsfile)$", re.I), 6, "ci-cd"),
    (re.compile(r"(^|/).+\.(sh|bash|zsh|ps1)$", re.I), 4, "script"),
    (re.compile(r"(^|/).+\.(ya?ml|json|ini|conf|cfg|toml|xml|properties)$", re.I), 3, "structured-config"),
    (re.compile(r"(^|/)(kubeconfig|config\.json|settings\.json|local\.settings\.json|appsettings\.json)$", re.I), 6, "app-settings"),
    (re.compile(r"(^|/)(credentials|credentials\.json)$", re.I), 8, "credentials-file"),
    (re.compile(r"(^|/)(id_rsa|id_dsa|authorized_keys|known_hosts)$", re.I), 9, "ssh-material"),
    (re.compile(r"(^|/).+\.(pem|p12|pfx|key|crt|cer)$", re.I), 7, "key-material"),
    (re.compile(r"(^|/)(vault\.ya?ml|secrets\.ya?ml)$", re.I), 7, "secret-config"),
    (re.compile(r"(^|/)(inventory|hosts)$", re.I), 4, "infra-inventory"),
    (re.compile(r"(^|/).+\.(sql)$", re.I), 3, "sql-file"),
    (re.compile(r"(^|/)(backup|dump)\.sql$", re.I), 6, "db-dump"),
    (re.compile(r"(^|/).+\.(py|js|ts|go|java|rb|php|cs|rs)$", re.I), 2, "source-code"),
    (re.compile(r"(^|/)(README|CHANGELOG|docs?/).*$", re.I), -2, "docs"),
    (re.compile(r"(^|/).+\.(md|rst|txt)$", re.I), -2, "doc-file"),
]

PATH_KEYWORDS = {
    "token": 4, "secret": 4, "password": 4, "passwd": 4,
    "api_key": 4, "apikey": 4, "auth": 3, "authorization": 3,
    "bearer": 3, "private_key": 5, "client_secret": 5,
    "access_key": 4, "secret_key": 4, "jwt": 3, "cookie": 2,
    "session": 2, "webhook": 3, "smtp": 2, "database": 2,
    "redis": 2, "postgres": 2, "postgresql": 2, "mysql": 2,
    "mongo": 2, "mongodb": 2, "s3": 2, "bucket": 2,
    "internal": 3, "admin": 3, "staging": 3, "prod": 3,
    "production": 3, "vault": 4, "kube": 2, "k8s": 2,
    "deploy": 2, "infra": 2, "oauth": 3, "oidc": 3,
    "openid": 3, "saml": 3, "client_id": 2, "refresh_token": 4,
    "access_token": 4, "id_token": 3, "x-api-key": 4,
    "service_account": 4, "connectionstring": 4, "connection_string": 4,
    "vault_token": 5, "ansible_vault": 4, "sealedsecret": 4,
    "secretref": 3, "envfrom": 3, "imagepullsecrets": 3,
    "bastion": 3, "jumpbox": 3, "monitoring": 2, "prometheus": 2,
    "alertmanager": 2, "kibana": 3, "grafana": 3, "dashboard": 2,
    "proxy": 2, "gateway": 3, "ingress": 2, "egress": 2,
    "loadbalancer": 2, "reverse-proxy": 2, "vpn": 3, "kafka": 2,
    "rabbitmq": 2, "amqp": 2, "dsn": 2, "jdbc": 2,
}

DOMAIN_RISK_TERMS = {
    "admin": 3, "internal": 3, "auth": 3, "sso": 3, "prod": 3,
    "production": 3, "staging": 2, "api": 2, "jenkins": 3,
    "grafana": 3, "kibana": 3, "gitlab": 2, "vault": 4,
    "db": 3, "mysql": 3, "postgres": 3, "mongo": 3,
    "redis": 3, "smtp": 2, "storage": 2, "s3": 2, "backup": 3,
    "vpn": 3, "gateway": 3, "proxy": 2, "ingress": 2,
    "bastion": 3, "console": 2, "dashboard": 2, "monitoring": 2,
    "kafka": 2, "rabbitmq": 2, "broker": 2, "elastic": 2,
    "opensearch": 2,
}

CONTENT_KEYWORDS = {
    "token": 4, "secret": 4, "password": 4, "passwd": 4,
    "api_key": 4, "apikey": 4, "authorization": 4, "bearer": 4,
    "private_key": 5, "client_secret": 5, "access_key": 4,
    "secret_key": 4, "jwt": 3, "cookie": 2, "session": 2,
    "webhook": 3, "database_url": 4, "redis": 2, "postgres": 2,
    "postgresql": 2, "mysql": 2, "mongo": 2, "mongodb_uri": 3,
    "smtp": 2, "vault": 4, "aws_access_key_id": 5,
    "aws_secret_access_key": 5, "aws_session_token": 4,
    "service_account": 4, "google_credentials": 4,
    "azure_keyvault": 4, "connectionstring": 4, "connection_string": 4,
    "oauth": 3, "oidc": 3, "openid": 3, "saml": 3,
    "client_id": 2, "refresh_token": 4, "access_token": 4,
    "id_token": 3, "x-api-key": 4, "vault_token": 5,
    "ansible_vault": 4, "sealedsecret": 4, "secretref": 3,
    "envfrom": 3, "imagepullsecrets": 3, "amqp": 2, "rabbitmq": 2,
    "kafka": 2, "dsn": 2, "jdbc": 2,
}

CONTENT_FETCH_CANDIDATE = re.compile(
    r"(^|/)(\.env(\..+)?|"
    r"(prod|production)\.env|"
    r"docker-compose\.ya?ml|compose\.ya?ml|"
    r"Jenkinsfile|jenkinsfile|"
    r"application\.(ya?ml|properties)|"
    r"bootstrap\.(ya?ml|properties)|"
    r".*\.tfvars|"
    r"\.github/workflows/.+\.ya?ml|"
    r"(settings|config|secrets?)\.(ya?ml|json|ini|conf|cfg|toml|xml|properties)|"
    r"credentials(\.json)?|"
    r"kubeconfig|"
    r"local\.settings\.json|"
    r"appsettings\.json|"
    r".+\.(pem|key|p12|pfx|crt|cer))$",
    re.I,
)

SECRET_LIKE_PATTERNS = [
    (r"(token|secret|password|passwd|api[_-]?key|client[_-]?secret|access[_-]?key)\s*[:=]\s*['\"]?[a-z0-9_\-\/=+]{8,}", "credential-pattern", 5),
    (r"authorization\s*[:=]\s*['\"]?bearer\s+[a-z0-9\-._~+/]+=*", "bearer", 5),
    (r"aws_access_key_id\s*[:=]", "aws-access-key", 5),
    (r"aws_secret_access_key\s*[:=]", "aws-secret-key", 5),
    (r"-----begin [a-z0-9 ]*private key-----", "private-key", 6),
    (r"(connectionstring|connection_string)\s*[:=]", "connection-string", 4),
    (r"(mongodb(\+srv)?://|postgres(ql)?://|mysql://|redis://|amqp://)", "service-uri", 4),
]


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    return value.strip()


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "domain"


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
    out = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def build_headers(token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-domain-triage-v3",
    }


def parse_link_header(value: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not value:
        return out
    for part in value.split(","):
        m = re.search(r'<([^>]+)>;\s*rel="([^"]+)"', part.strip())
        if m:
            out[m.group(2)] = m.group(1)
    return out


def api_get_json(url: str, headers: dict[str, str], retries: int = DEFAULT_HTTP_RETRIES, backoff: float = 2.0) -> tuple[dict | list, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body), dict(resp.headers.items())
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
                data = json.loads(body)
            except Exception:
                data = {"message": str(e)}
            status = e.code
            if status in (403, 429, 500, 502, 503, 504) and attempt < retries:
                safe_sleep(backoff * attempt)
                last_error = RuntimeError(f"HTTP {status}: {data.get('message', 'API error')}")
                continue
            headers_out = dict(e.headers.items()) if e.headers else {}
            raise RuntimeError(f"HTTP {status}: {data.get('message', 'API error')}|||HEADERS|||{json.dumps(headers_out)}") from None
        except (http.client.IncompleteRead, urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_error = e
            if attempt < retries:
                safe_sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Transient network/read error after {retries} attempts: {e}") from None
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < retries:
                safe_sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Invalid JSON after {retries} attempts: {e}") from None
    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def api_get_text(url: str, headers: dict[str, str], retries: int = DEFAULT_HTTP_RETRIES, backoff: float = 2.0) -> tuple[str, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace"), dict(resp.headers.items())
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(e)
            if status in (403, 429, 500, 502, 503, 504) and attempt < retries:
                safe_sleep(backoff * attempt)
                last_error = RuntimeError(f"HTTP {status}: {body}")
                continue
            raise RuntimeError(f"HTTP {status}: {body}") from None
        except (http.client.IncompleteRead, urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_error = e
            if attempt < retries:
                safe_sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Transient network/read error after {retries} attempts: {e}") from None
    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def get_rate_limit_status(token: str) -> dict:
    data, _ = api_get_json(RATE_LIMIT_ENDPOINT, build_headers(token))
    resources = data.get("resources", {}) if isinstance(data, dict) else {}
    return resources if isinstance(resources, dict) else {}


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


def handle_rate_limit_error(token: str, bucket: str, exc: Exception) -> bool:
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
    params = {"q": f'"{domain}"', "page": page, "per_page": per_page}
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


def shorten(text: str | None, limit: int = 180) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def path_score(path: str) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    tags: list[str] = []
    lower = path.lower()
    for pattern, pts, tag in SUSPICIOUS_FILE_PATTERNS:
        if pattern.search(path):
            score += pts
            reasons.append(f"path:{tag}:{pts:+d}")
            tags.append(tag)
            break
    for key, pts in PATH_KEYWORDS.items():
        if key in lower:
            score += pts
            reasons.append(f"path-keyword:{key}:{pts:+d}")
            tags.append(key.replace("_", "-"))
    for key, pts in NEGATIVE_HINTS.items():
        if key in lower:
            score += pts
            reasons.append(f"negative-hint:{key}:{pts:+d}")
            tags.append(f"likely-{key}")
    return score, reasons, tags


def domain_risk_score(domain: str) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    tags: list[str] = []
    lower = domain.lower()
    for key, pts in DOMAIN_RISK_TERMS.items():
        if key in lower:
            score += pts
            reasons.append(f"domain-term:{key}:{pts:+d}")
            tags.append(key)
    return score, reasons, tags


def repo_score(meta: RepoMeta) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    tags: list[str] = []
    owner_pts = OWNER_TYPE_SCORES.get(meta.owner_type or "", 0)
    if owner_pts:
        score += owner_pts
        reasons.append(f"owner-type:{meta.owner_type}:{owner_pts:+d}")
        if meta.owner_type == "Organization":
            tags.append("org-repo")
    if meta.archived:
        score -= 3
        reasons.append("repo:archived:-3")
        tags.append("archived-repo")
    age_days = days_since_iso8601(meta.pushed_at)
    if age_days is not None:
        if age_days <= 30:
            score += 3
            reasons.append("repo:recent-push:+3")
            tags.append("active-repo")
        elif age_days <= 180:
            score += 1
            reasons.append("repo:active-ish:+1")
            tags.append("recent-repo")
        elif age_days > 730:
            score -= 2
            reasons.append("repo:stale:-2")
            tags.append("stale-repo")
    if meta.stargazers_count >= 500:
        score += 1
        reasons.append("repo:stars>=500:+1")
        tags.append("popular-repo")
    return score, reasons, tags


def should_fetch_content(path: str) -> bool:
    return bool(CONTENT_FETCH_CANDIDATE.search(path))


def content_context_score(content: str, domain: str) -> tuple[int, list[str], list[str], str]:
    score = 0
    reasons: list[str] = []
    tags: list[str] = []
    lower = content.lower()
    domain_lower = domain.lower()
    idx = lower.find(domain_lower)
    if idx == -1:
        return 0, [], [], ""
    start = max(0, idx - 700)
    end = min(len(lower), idx + len(domain_lower) + 700)
    window = lower[start:end]
    for key, pts in CONTENT_KEYWORDS.items():
        if key in window:
            score += pts
            reasons.append(f"content-keyword:{key}:{pts:+d}")
            tags.append(key.replace("_", "-"))
    for pattern, tag, pts in SECRET_LIKE_PATTERNS:
        if re.search(pattern, window, re.I):
            score += pts
            reasons.append(f"content:{tag}:{pts:+d}")
            tags.append(tag)
    snippet = extract_evidence_snippet(content, domain)
    return score, reasons, tags, snippet


def extract_evidence_snippet(content: str, needle: str, context_lines: int = 1, max_len: int = 220) -> str:
    lines = content.splitlines()
    needle_lower = needle.lower()
    for i, line in enumerate(lines):
        if needle_lower in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            joined = " | ".join(l.strip() for l in lines[start:end] if l.strip())
            return shorten(joined, max_len)
    return ""


def extract_deleted_evidence(patch: str, domain: str, max_len: int = 220) -> str:
    domain_lower = domain.lower()
    for line in patch.splitlines():
        if line.startswith("-") and not line.startswith("---") and domain_lower in line.lower():
            return shorten(line[1:].strip(), max_len)
    for line in patch.splitlines():
        if domain_lower in line.lower():
            return shorten(line.lstrip("+- ").strip(), max_len)
    return ""


def finding_tier(score: int) -> str:
    for name, threshold in TIER_THRESHOLDS:
        if score >= threshold:
            return name
    return "low"


def unique_tags(tags: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for tag in tags:
        t = tag.strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def classify_label(full_tags: list[str], score: int, path: str, source_type: str) -> str:
    tagset = set(t.lower() for t in full_tags)
    path_lower = (path or "").lower()
    direct_secret_markers = {
        "credential-pattern", "private-key", "aws-access-key", "aws-secret-key",
        "api-key", "token", "secret", "password", "client-secret", "vault-token",
        "connection-string",
    }
    ci_cd_markers = {"workflow", "ci-cd", "deploy", "jenkinsfile", "bearer"}
    infra_markers = {"terraform", "terraform-vars", "config-file", "app-config", "structured-config", "compose-file", "k8s", "kube"}
    endpoint_markers = {"admin", "internal", "api", "auth", "sso", "prod", "production", "staging", "vpn", "gateway"}
    db_markers = {"database", "database-url", "postgres", "postgresql", "mysql", "mongo", "mongodb", "service-uri", "jdbc", "dsn"}
    cloud_markers = {"s3", "bucket", "service-account", "google-credentials", "azure-keyvault", "vault"}
    doc_markers = {"docs", "doc-file", "likely-readme", "likely-docs", "likely-example", "likely-sample", "likely-demo"}

    if source_type == "history" and "deleted-match" in tagset:
        if tagset & direct_secret_markers:
            return "deleted_secret_signal"
        return "deleted_historical_reference"
    if tagset & direct_secret_markers:
        return "direct_secret_signal"
    if tagset & ci_cd_markers and (tagset & direct_secret_markers or "auth" in tagset or "bearer" in tagset):
        return "ci_cd_exposure"
    if tagset & infra_markers and (tagset & endpoint_markers or tagset & direct_secret_markers):
        return "infra_config_exposure"
    if tagset & db_markers:
        return "database_reference"
    if tagset & cloud_markers:
        return "cloud_storage_reference"
    if tagset & endpoint_markers:
        return "sensitive_endpoint_reference"
    if "internal" in tagset or "admin" in tagset:
        return "internal_service_reference"
    if tagset & doc_markers or path_lower.endswith((".md", ".rst", ".txt")):
        return "documentation_reference"
    if score <= 2:
        return "likely_noise"
    return "probable_secret_context"


def fetch_repo_meta(token: str, repo_full_name: str, cache: dict[str, RepoMeta], delay: float, stats: Stats) -> RepoMeta:
    if repo_full_name in cache:
        return cache[repo_full_name]
    ensure_bucket_available(token, "core")
    url = f"{REPOS_ENDPOINT}/{repo_full_name}"
    try:
        data, _ = api_get_json(url, build_headers(token))
    except Exception as exc:
        if handle_rate_limit_error(token, "core", exc):
            data, _ = api_get_json(url, build_headers(token))
        else:
            stats.repo_meta_failures += 1
            data = {}
    meta = RepoMeta(
        full_name=repo_full_name,
        archived=bool(data.get("archived", False)) if isinstance(data, dict) else False,
        pushed_at=data.get("pushed_at") if isinstance(data, dict) else None,
        owner_type=(data.get("owner") or {}).get("type") if isinstance(data, dict) else None,
        stargazers_count=int(data.get("stargazers_count") or 0) if isinstance(data, dict) else 0,
        default_branch=data.get("default_branch") if isinstance(data, dict) else None,
    )
    cache[repo_full_name] = meta
    safe_sleep(delay)
    return meta


def fetch_blob_text(token: str, repo_full_name: str, blob_sha: str, max_bytes: int, delay: float, stats: Stats) -> str | None:
    stats.blob_fetch_attempts += 1
    ensure_bucket_available(token, "core")
    url = f"{REPOS_ENDPOINT}/{repo_full_name}/git/blobs/{blob_sha}"
    headers = build_headers(token)
    try:
        data, _ = api_get_json(url, headers)
    except Exception as exc:
        if handle_rate_limit_error(token, "core", exc):
            data, _ = api_get_json(url, headers)
        else:
            stats.blob_fetch_failures += 1
            return None
    safe_sleep(delay)
    if not isinstance(data, dict):
        stats.blob_fetch_failures += 1
        return None
    if data.get("encoding") != "base64" or not data.get("content"):
        stats.blob_fetch_failures += 1
        return None
    try:
        raw = base64.b64decode(data["content"], validate=False)
    except Exception:
        stats.blob_fetch_failures += 1
        return None
    if len(raw) > max_bytes:
        stats.blob_fetch_failures += 1
        return None
    if b"\x00" in raw:
        stats.blob_fetch_failures += 1
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        stats.blob_fetch_failures += 1
        return None
    stats.blob_fetch_success += 1
    return text


def extract_items(data: dict | list) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("items", [])
        return items if isinstance(items, list) else []
    return []


def collect_search_hits(token: str, domain: str, pages: int, per_page: int, delay: float, stats: Stats) -> list[dict]:
    hits: list[dict] = []
    seen = set()
    total_count: int | None = None
    print(color("\n[>] Searching: ", C.CYAN) + color(domain, C.BOLD + C.CYAN))
    for page in range(1, pages + 1):
        ensure_bucket_available(token, "code_search")
        url = build_search_url(domain, page, per_page)
        try:
            data, headers = api_get_json(url, build_headers(token))
        except Exception as exc:
            if handle_rate_limit_error(token, "code_search", exc):
                data, headers = api_get_json(url, build_headers(token))
            else:
                print(color(f"  [!] Search failed on page {page}: {exc}", C.RED))
                break
        items = extract_items(data)
        if total_count is None and isinstance(data, dict):
            try:
                total_count = int(data.get("total_count") or 0)
            except Exception:
                total_count = None
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
        links = parse_link_header(headers.get("Link") if isinstance(headers, dict) else None)
        safe_sleep(delay)
        if "next" not in links:
            break
    stats.live_hits_seen = len(hits)
    if total_count is not None and total_count > len(hits):
        print(color(f"  [i] API reported at least {total_count} results; collected {len(hits)} within page limits.", C.YELLOW))
    return hits


def classify_live_hits(token: str, domain: str, hits: list[dict], delay: float, max_blob_bytes: int, stats: Stats) -> tuple[list[Finding], dict[str, RepoMeta]]:
    repo_cache: dict[str, RepoMeta] = {}
    findings: list[Finding] = []
    total = len(hits)
    if total:
        print_progress(0, total, "[~] Classifying live")
    for idx, item in enumerate(hits, 1):
        repo = item.get("repository") or {}
        repo_full_name = repo.get("full_name")
        path = item.get("path") or ""
        html_url = item.get("html_url") or ""
        sha = item.get("sha")
        if not repo_full_name or not path or not html_url:
            stats.skipped_items += 1
            if idx == total or idx % 10 == 0:
                print_progress(idx, total, "[~] Classifying live")
            continue
        try:
            meta = fetch_repo_meta(token, repo_full_name, repo_cache, delay, stats)
            score = 0
            reasons: list[str] = []
            tags: list[str] = []
            evidence = ""

            s, r, t = path_score(path)
            score += s
            reasons.extend(r)
            tags.extend(t)

            s, r, t = domain_risk_score(domain)
            score += s
            reasons.extend(r)
            tags.extend(t)

            s, r, t = repo_score(meta)
            score += s
            reasons.extend(r)
            tags.extend(t)

            if sha and should_fetch_content(path):
                content = fetch_blob_text(token, repo_full_name, sha, max_blob_bytes, delay, stats)
                if content:
                    s, r, t, evidence = content_context_score(content, domain)
                    score += s
                    reasons.extend(r)
                    tags.extend(t)

            full_tags = unique_tags(tags)
            tier = finding_tier(score)
            classification = classify_label(full_tags, score, path, "live")

            findings.append(
                Finding(
                    domain=domain,
                    source_type="live",
                    classification=classification,
                    tier=tier,
                    score=score,
                    tags=full_tags,
                    link=html_url,
                    repo_full_name=repo_full_name,
                    path=path,
                    commit_sha=sha,
                    matched_ref=sha,
                    owner_type=meta.owner_type,
                    archived=meta.archived,
                    repo_pushed_at=meta.pushed_at,
                    evidence=evidence,
                    notes="live code-search hit",
                    debug_reasons=reasons,
                )
            )
        except Exception as exc:
            stats.classification_failures += 1
            eprint(f"[!] live classification failure repo={repo_full_name} path={path}: {exc}")
        if idx == total or idx % 10 == 0:
            print_progress(idx, total, "[~] Classifying live")
    if total:
        print()
    findings.sort(key=lambda x: (-x.score, x.link.lower()))
    stats.live_findings = len(findings)
    return findings, repo_cache


def iter_recent_commits(token: str, repo_full_name: str, limit: int, delay: float) -> list[dict]:
    ensure_bucket_available(token, "core")
    url = f"{REPOS_ENDPOINT}/{repo_full_name}/commits?per_page={min(limit,100)}"
    data, _ = api_get_json(url, build_headers(token))
    safe_sleep(delay)
    if isinstance(data, list):
        return data[:limit]
    return []


def fetch_commit_detail(token: str, repo_full_name: str, commit_sha: str, delay: float) -> dict | None:
    ensure_bucket_available(token, "core")
    url = f"{REPOS_ENDPOINT}/{repo_full_name}/commits/{commit_sha}"
    data, _ = api_get_json(url, build_headers(token))
    safe_sleep(delay)
    return data if isinstance(data, dict) else None


def history_score(path: str, patch: str, domain: str, meta: RepoMeta) -> tuple[int, list[str], list[str], str]:
    score = 0
    reasons: list[str] = []
    tags: list[str] = ["deleted-match"]

    s, r, t = path_score(path)
    score += s
    reasons.extend(r)
    tags.extend(t)

    s, r, t = domain_risk_score(domain)
    score += s
    reasons.extend(r)
    tags.extend(t)

    s, r, t = repo_score(meta)
    score += s
    reasons.extend(r)
    tags.extend(t)

    lowered = patch.lower()
    for key, pts in CONTENT_KEYWORDS.items():
        if key in lowered:
            score += pts
            reasons.append(f"history-content-keyword:{key}:{pts:+d}")
            tags.append(key.replace("_", "-"))
    for pattern, tag, pts in SECRET_LIKE_PATTERNS:
        if re.search(pattern, patch, re.I):
            score += pts
            reasons.append(f"history-content:{tag}:{pts:+d}")
            tags.append(tag)

    if "\n-" in patch or patch.startswith("-"):
        score += 2
        reasons.append("history:deleted-line:+2")

    evidence = extract_deleted_evidence(patch, domain)
    return score, reasons, unique_tags(tags), evidence


def inspect_history(token: str, domain: str, live_findings: list[Finding], repo_cache: dict[str, RepoMeta], delay: float, commits_per_repo: int, max_repos: int, max_files_per_commit: int, stats: Stats) -> list[Finding]:
    findings: list[Finding] = []
    repos: list[str] = []
    seen_repo = set()
    for finding in sorted(live_findings, key=lambda x: (-x.score, x.repo_full_name)):
        if finding.repo_full_name not in seen_repo:
            seen_repo.add(finding.repo_full_name)
            repos.append(finding.repo_full_name)
        if len(repos) >= max_repos:
            break

    if not repos or commits_per_repo <= 0:
        return findings

    total = len(repos)
    print_progress(0, total, "[~] Inspecting history")
    domain_lower = domain.lower()
    seen_keys = set()

    for idx, repo_full_name in enumerate(repos, 1):
        try:
            meta = repo_cache.get(repo_full_name) or fetch_repo_meta(token, repo_full_name, repo_cache, delay, stats)
            commits = iter_recent_commits(token, repo_full_name, commits_per_repo, delay)
            stats.history_repos_scanned += 1
            for commit_stub in commits:
                sha = commit_stub.get("sha")
                if not sha:
                    continue
                try:
                    detail = fetch_commit_detail(token, repo_full_name, sha, delay)
                except Exception as exc:
                    stats.history_commit_failures += 1
                    eprint(f"[!] history commit fetch failure repo={repo_full_name} sha={sha}: {exc}")
                    continue
                if not detail:
                    continue
                stats.history_commits_scanned += 1
                files = detail.get("files") or []
                if not isinstance(files, list):
                    continue
                for file_item in files[:max_files_per_commit]:
                    patch = file_item.get("patch")
                    filename = file_item.get("filename") or ""
                    previous_filename = file_item.get("previous_filename")
                    status = file_item.get("status") or ""
                    if not patch or domain_lower not in patch.lower():
                        continue
                    key = (repo_full_name, sha, filename, domain_lower)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    score, reasons, tags, evidence = history_score(filename, patch, domain, meta)
                    classification = classify_label(tags, score, filename, "history")
                    tier = finding_tier(score)
                    commit_html = ((detail.get("html_url") or f"https://github.com/{repo_full_name}/commit/{sha}")).strip())
                    notes_parts = ["historical diff match", f"status={status}"]
                    if previous_filename:
                        notes_parts.append(f"previous={previous_filename}")
                    findings.append(
                        Finding(
                            domain=domain,
                            source_type="history",
                            classification=classification,
                            tier=tier,
                            score=score,
                            tags=tags,
                            link=commit_html,
                            repo_full_name=repo_full_name,
                            path=filename,
                            commit_sha=sha,
                            matched_ref=sha,
                            owner_type=meta.owner_type,
                            archived=meta.archived,
                            repo_pushed_at=meta.pushed_at,
                            evidence=evidence,
                            notes="; ".join(notes_parts),
                            debug_reasons=reasons,
                        )
                    )
        except Exception as exc:
            stats.history_commit_failures += 1
            eprint(f"[!] history scan failure repo={repo_full_name}: {exc}")
        if idx == total or idx % 5 == 0:
            print_progress(idx, total, "[~] Inspecting history")
    if total:
        print()
    findings.sort(key=lambda x: (-x.score, x.link.lower()))
    stats.history_findings = len(findings)
    return findings


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    best: dict[tuple[str, str, str | None, str | None], Finding] = {}
    for f in findings:
        key = (f.source_type, f.link, f.path, f.commit_sha)
        prev = best.get(key)
        if prev is None or f.score > prev.score:
            best[key] = f
    return sorted(best.values(), key=lambda x: (-x.score, x.source_type, x.link.lower()))


def write_csv(domain: str, findings: list[Finding], out_dir: Path, include_debug: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(domain)}.csv"
    fieldnames = [
        "domain", "source_type", "classification", "tier", "score", "tags",
        "repo", "path", "link", "commit_sha", "matched_ref", "owner_type",
        "archived", "repo_pushed_at", "notes", "evidence",
    ]
    if include_debug:
        fieldnames.append("debug_reasons")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in findings:
            row = {
                "domain": item.domain,
                "source_type": item.source_type,
                "classification": item.classification,
                "tier": item.tier,
                "score": item.score,
                "tags": "|".join(item.tags),
                "repo": item.repo_full_name,
                "path": item.path or "",
                "link": item.link,
                "commit_sha": item.commit_sha or "",
                "matched_ref": item.matched_ref or "",
                "owner_type": item.owner_type or "",
                "archived": str(item.archived).lower(),
                "repo_pushed_at": item.repo_pushed_at or "",
                "notes": item.notes,
                "evidence": item.evidence,
            }
            if include_debug:
                row["debug_reasons"] = "|".join(item.debug_reasons)
            writer.writerow(row)
    return out_path


def write_summary(domain: str, csv_path: Path, findings: list[Finding], stats: Stats, out_dir: Path) -> Path:
    out_path = out_dir / f"{sanitize_filename(domain)}_summary.txt"
    live_count = sum(1 for f in findings if f.source_type == "live")
    history_count = sum(1 for f in findings if f.source_type == "history")
    high_count = sum(1 for f in findings if f.tier in {"urgent", "high"})
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"domain={domain}\n")
        f.write(f"csv={csv_path.name}\n")
        f.write(f"total_findings={len(findings)}\n")
        f.write(f"live_findings={live_count}\n")
        f.write(f"history_findings={history_count}\n")
        f.write(f"urgent_or_high={high_count}\n")
        f.write(f"live_hits_seen={stats.live_hits_seen}\n")
        f.write(f"history_repos_scanned={stats.history_repos_scanned}\n")
        f.write(f"history_commits_scanned={stats.history_commits_scanned}\n")
        f.write(f"blob_fetch_attempts={stats.blob_fetch_attempts}\n")
        f.write(f"blob_fetch_success={stats.blob_fetch_success}\n")
        f.write(f"blob_fetch_failures={stats.blob_fetch_failures}\n")
        f.write(f"repo_meta_failures={stats.repo_meta_failures}\n")
        f.write(f"classification_failures={stats.classification_failures}\n")
        f.write(f"history_commit_failures={stats.history_commit_failures}\n")
        f.write(f"skipped_items={stats.skipped_items}\n")
    return out_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GitHub domain triage with CSV output and optional history scan.")
    p.add_argument("--domain", help="Single domain to search")
    p.add_argument("--file", help="File with domains, one per line")
    p.add_argument("--pages", type=int, default=DEFAULT_PAGES, help=f"Search pages per domain (default: {DEFAULT_PAGES})")
    p.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, help=f"Results per page, max 100 (default: {DEFAULT_PER_PAGE})")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})")
    p.add_argument("--max-blob-bytes", type=int, default=DEFAULT_MAX_BLOB_BYTES, help=f"Max blob size for content fetch (default: {DEFAULT_MAX_BLOB_BYTES})")
    p.add_argument("--out-dir", default=str(RESULTS_DIR), help=f"Output directory (default: {RESULTS_DIR})")
    p.add_argument("--history-commits", type=int, default=DEFAULT_HISTORY_COMMITS, help=f"Recent commits per matched repo to inspect for historical deleted refs (default: {DEFAULT_HISTORY_COMMITS})")
    p.add_argument("--history-max-repos", type=int, default=DEFAULT_HISTORY_REPOS, help=f"Max matched repos to inspect in history mode (default: {DEFAULT_HISTORY_REPOS})")
    p.add_argument("--history-max-files-per-commit", type=int, default=DEFAULT_HISTORY_FILES_PER_COMMIT, help=f"Max changed files to inspect per commit detail (default: {DEFAULT_HISTORY_FILES_PER_COMMIT})")
    p.add_argument("--no-history", action="store_true", help="Disable historical commit diff inspection")
    p.add_argument("--include-debug-columns", action="store_true", help="Append debug_reasons column to CSV")
    return p.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.domain and not args.file:
        raise SystemExit("error: provide --domain or --file")
    if args.per_page < 1 or args.per_page > 100:
        raise SystemExit("error: --per-page must be between 1 and 100")
    if args.pages < 1:
        raise SystemExit("error: --pages must be >= 1")
    if args.max_blob_bytes < 1024:
        raise SystemExit("error: --max-blob-bytes too small")
    if args.history_commits < 0:
        raise SystemExit("error: --history-commits must be >= 0")


def main() -> int:
    args = parse_args()
    validate_args(args)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        eprint("[!] GITHUB_TOKEN is not set")
        return 1

    domains = load_domains(args.domain, args.file)
    if not domains:
        eprint("[!] No valid domains loaded")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(color("[*] Output directory: ", C.GREEN) + str(out_dir))
    print(color("[*] Domains: ", C.GREEN) + str(len(domains)))
    print(color("[*] Pages/domain: ", C.GREEN) + str(args.pages))
    print(color("[*] Delay/request: ", C.GREEN) + f"{args.delay}s")
    if args.no_history:
        print(color("[*] History scan: ", C.GREEN) + "disabled")
    else:
        print(color("[*] History scan: ", C.GREEN) + f"enabled ({args.history_commits} commits/repo, max {args.history_max_repos} repos)")

    total_written = 0
    for domain in domains:
        stats = Stats()
        hits = collect_search_hits(token, domain, args.pages, args.per_page, args.delay, stats)
        live_findings, repo_cache = classify_live_hits(token, domain, hits, args.delay, args.max_blob_bytes, stats)
        history_findings: list[Finding] = []
        if not args.no_history and args.history_commits > 0 and live_findings:
            history_findings = inspect_history(
                token=token,
                domain=domain,
                live_findings=live_findings,
                repo_cache=repo_cache,
                delay=args.delay,
                commits_per_repo=args.history_commits,
                max_repos=args.history_max_repos,
                max_files_per_commit=args.history_max_files_per_commit,
                stats=stats,
            )
        findings = dedupe_findings(live_findings + history_findings)
        csv_path = write_csv(domain, findings, out_dir, include_debug=args.include_debug_columns)
        summary_path = write_summary(domain, csv_path, findings, stats, out_dir)
        total_written += len(findings)
        print(color("[+] Saved: ", C.GREEN) + color(csv_path.name, C.BOLD + C.GREEN) + color(f" ({len(findings)} findings)", C.GRAY))
        print(color("[+] Summary: ", C.GREEN) + color(summary_path.name, C.BOLD + C.GREEN))

    print(color("\n[+] Done. Total findings written: ", C.GREEN) + color(str(total_written), C.BOLD + C.GREEN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
