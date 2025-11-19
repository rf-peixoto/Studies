#!/usr/bin/env python3
import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Set, Iterable, Pattern, Optional, Tuple, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ===========================
#   Data structures
# ===========================

@dataclass
class SecretPattern:
    name: str
    regex: Pattern
    risk: str                 # "CRITICAL", "HIGH", "MEDIUM"
    min_length: int = 0       # minimum match length
    min_entropy: float = 0.0  # min Shannon entropy per char (0 = disabled)
    context_keywords: Optional[List[str]] = None  # required/boosted context
    generic: bool = False     # if True, only used when --enable-generic


@dataclass
class HeaderGroup:
    name: str
    keys: List[str]
    risk: str


@dataclass
class Finding:
    url: str
    kind: str
    key_snippet: str
    full_key: str
    risk: str
    is_new: bool = True       # for differential mode


@dataclass
class Config:
    include_html: bool
    enable_generic: bool
    quiet: bool
    verbose: bool
    use_color: bool
    min_risk: str             # "MEDIUM" | "HIGH" | "CRITICAL"
    timeout: int


# ===========================
#   Utils
# ===========================

RISK_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    ent = 0.0
    for count in freq.values():
        p = count / length
        ent -= p * math.log2(p)
    return ent


PLACEHOLDER_PATTERNS = [
    re.compile(r'test', re.I),
    re.compile(r'dummy', re.I),
    re.compile(r'example', re.I),
    re.compile(r'sample', re.I),
    re.compile(r'fake', re.I),
    re.compile(r'foo', re.I),
    re.compile(r'bar', re.I),
    re.compile(r'xxxx+', re.I),
    re.compile(r'yyy+', re.I),
    re.compile(r'zzz+', re.I),
    re.compile(r'(your[-_ ]+)?(api|access|secret|token|key)', re.I),
]


UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-'
    r'[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
)

HEX_HASH_PATTERN = re.compile(r'^[0-9a-fA-F]{32,64}$')  # md5/sha1/sha256 etc.


def is_probably_placeholder(value: str) -> bool:
    v = value.strip().strip('"').strip("'")
    if len(v) < 8:
        return True
    for rx in PLACEHOLDER_PATTERNS:
        if rx.search(v):
            return True
    return False


def is_likely_non_secret_format(value: str) -> bool:
    """Negative heuristics: UUIDs, plain hashes, etc."""
    v = value.strip().strip('"').strip("'")
    if UUID_PATTERN.match(v):
        return True
    if HEX_HASH_PATTERN.match(v):
        return True
    return False


def has_mixed_charset(value: str) -> bool:
    """Require both digits and letters to avoid pure numeric / pure hex noise."""
    has_digit = any(ch.isdigit() for ch in value)
    has_alpha = any(ch.isalpha() for ch in value)
    return has_digit and has_alpha


def value_has_context(text: str, value: str, keywords: List[str]) -> bool:
    try:
        idx = text.index(value)
    except ValueError:
        return False
    window = 80
    start = max(0, idx - window)
    end = min(len(text), idx + len(value) + window)
    chunk = text[start:end].lower()
    return any(k.lower() in chunk for k in keywords)


# ===========================
#   Static configuration
# ===========================

# Precise patterns (low FP)
PRECISE_PATTERNS: List[SecretPattern] = [
    SecretPattern(
        name="AWS Access Key ID (AKIA)",
        regex=re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="GitHub PAT (ghp_)",
        regex=re.compile(r'\bghp_[0-9A-Za-z]{36,255}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="GitHub OAuth Token (gho_)",
        regex=re.compile(r'\bgho_[0-9A-Za-z]{36,255}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="GitHub User-to-Server Token (ghu_)",
        regex=re.compile(r'\bghu_[0-9A-Za-z]{36,255}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="GitHub App Token (ghs_)",
        regex=re.compile(r'\bghs_[0-9A-Za-z]{36,255}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="GitHub Fine-grained PAT (github_pat_)",
        regex=re.compile(r'\bgithub_pat_[0-9A-Za-z_]{60,255}\b'),
        risk="CRITICAL",
    ),
    SecretPattern(
        name="Cloudflare/Generic JWT",
        regex=re.compile(
            r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'
        ),
        risk="HIGH",
        min_length=60,
        min_entropy=3.5,
    ),
]

# Heuristic / generic patterns (optional)
GENERIC_PATTERNS: List[SecretPattern] = [
    SecretPattern(
        name="Generic long base64-like secret",
        regex=re.compile(r'"([A-Za-z0-9+/]{50,}={0,2})"'),
        risk="HIGH",
        min_length=50,
        min_entropy=4.0,
        context_keywords=["token", "secret", "key", "auth", "signature"],
        generic=True,
    ),
    SecretPattern(
        name="Generic long token",
        regex=re.compile(r'\b[A-Za-z0-9_\-]{48,}\b'),
        risk="HIGH",
        min_length=48,
        min_entropy=4.0,
        context_keywords=["token", "secret", "key", "auth", "session", "id"],
        generic=True,
    ),
]

# Header groups
GENERIC_AUTH_HEADERS = [
    "authorization", "proxy-authorization", "authentication",
    "x-authorization", "x-auth", "x-auth-token", "x-authentication-token",
    "auth-token", "access-token", "x-access-token", "id-token",
    "x-id-token", "identity-token", "refresh-token", "x-refresh-token",
    "session-token", "x-session-token", "x-session", "x-session-id",
    "x-sessionid",
]

API_KEY_HEADERS = [
    "api-key", "x-api-key", "x-api-token", "x-api-secret",
    "x-client-id", "client-id", "x-client-key", "x-client-secret",
    "client-secret", "x-app-id", "app-id", "x-app-key", "x-app-token",
    "x-app-secret", "x-organization-token", "x-tenant-token",
]

CSRF_HEADERS = [
    "csrf-token", "x-csrf-token", "x-csrftoken",
    "x-xsrf-token", "x-xsrftoken", "x-request-verification-token",
]

AWS_HEADERS = [
    "x-amz-date", "x-amz-security-token",
    "x-amz-content-sha256", "x-amz-target",
]

AZURE_HEADERS = [
    "ocp-apim-subscription-key", "ocp-apim-subscription-id",
    "x-ms-authorization-auxiliary", "x-ms-token-aad-access-token",
    "x-ms-token-aad-id-token", "x-ms-client-principal",
    "x-ms-client-principal-id", "x-ms-client-principal-name",
    "x-ms-client-principal-idp",
]

GOOGLE_HEADERS = [
    "x-goog-api-key", "x-goog-iam-authorization-token",
    "x-goog-iam-authority-selector", "x-goog-visitor-id",
]

FIREBASE_HEADERS = [
    "x-firebase-appcheck", "x-firebase-client",
]

CLOUDFLARE_HEADERS = [
    "cf-access-jwt-assertion",
]

VCS_HEADERS = [
    "x-github-token", "x-gitlab-token",
]

SLACK_DISCORD_HEADERS = [
    "x-slack-signature", "x-slack-request-timestamp",
    "x-discord-signature", "x-discord-timestamp",
]

PAYMENT_HEADERS = [
    "stripe-signature",
]

TWILIO_HEADERS = [
    "x-twilio-signature",
]

SHOPIFY_HEADERS = [
    "x-shopify-access-token",
]

SENTRY_HEADERS = [
    "x-sentry-auth",
]

MISC_SIGNATURE_HEADERS = [
    "x-token", "x-access", "x-key", "x-secret",
    "x-signature", "x-signature-timestamp",
    "x-request-signature", "x-api-signature",
    "x-authorization-signature",
]

HEADER_GROUPS: List[HeaderGroup] = [
    HeaderGroup("Generic auth/session header", GENERIC_AUTH_HEADERS, "CRITICAL"),
    HeaderGroup("API key/client credential header", API_KEY_HEADERS, "CRITICAL"),
    HeaderGroup("CSRF/XSRF header", CSRF_HEADERS, "HIGH"),
    HeaderGroup("AWS header", AWS_HEADERS, "HIGH"),
    HeaderGroup("Azure/Microsoft header", AZURE_HEADERS, "HIGH"),
    HeaderGroup("Google header", GOOGLE_HEADERS, "HIGH"),
    HeaderGroup("Firebase header", FIREBASE_HEADERS, "HIGH"),
    HeaderGroup("Cloudflare Access header", CLOUDFLARE_HEADERS, "HIGH"),
    HeaderGroup("VCS token header", VCS_HEADERS, "CRITICAL"),
    HeaderGroup("Slack/Discord signature header", SLACK_DISCORD_HEADERS, "HIGH"),
    HeaderGroup("Stripe/Payments header", PAYMENT_HEADERS, "CRITICAL"),
    HeaderGroup("Twilio header", TWILIO_HEADERS, "CRITICAL"),
    HeaderGroup("Shopify header", SHOPIFY_HEADERS, "CRITICAL"),
    HeaderGroup("Sentry header", SENTRY_HEADERS, "HIGH"),
    HeaderGroup("Misc signature header", MISC_SIGNATURE_HEADERS, "HIGH"),
]


# ===========================
#   Color utilities
# ===========================

RESET = "\033[0m"
BOLD = "\033[1m"
FG_RED = "\033[31m"
FG_YELLOW = "\033[33m"
FG_CYAN = "\033[36m"
FG_GREEN = "\033[32m"
FG_MAGENTA = "\033[35m"
FG_DIM = "\033[90m"


def colorize(text: str, color: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{color}{text}{RESET}"


# ===========================
#   Network / parsing
# ===========================

def fetch(url: str, session: requests.Session, cfg: Config) -> str:
    try:
        if cfg.verbose and not cfg.quiet:
            sys.stderr.write(f"[i] Fetching {url}\n")
        resp = session.get(url, timeout=cfg.timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0"
        })
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        if not cfg.quiet:
            sys.stderr.write(f"[!] Failed to fetch {url}: {e}\n")
        return ""


def extract_script_urls(base_url: str, html: str) -> Set[str]:
    urls: Set[str] = set()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all("script", src=True):
        u = urljoin(base_url, tag["src"])
        urls.add(u)

    hidden_js = re.findall(r'["\']([^"\']*\.js[^"\']*)["\']', html)
    for m in hidden_js:
        u = urljoin(base_url, m)
        urls.add(u)

    return urls


# ===========================
#   Scanning
# ===========================

def scan_with_value_patterns(
    text: str,
    source_url: str,
    seen: Set[str],
    cfg: Config,
) -> Iterable[Finding]:
    findings: List[Finding] = []

    patterns: List[SecretPattern] = list(PRECISE_PATTERNS)
    if cfg.enable_generic:
        patterns.extend(GENERIC_PATTERNS)

    for pat in patterns:
        for m in pat.regex.finditer(text):
            v = m.group(0)
            v_stripped = v.strip('"').strip("'")

            if len(v_stripped) < max(1, pat.min_length):
                continue
            if v_stripped in seen:
                continue
            if is_probably_placeholder(v_stripped):
                continue
            if is_likely_non_secret_format(v_stripped):
                continue

            # generic ones: require mixed charset to filter hex-only garbage
            if pat.generic and not has_mixed_charset(v_stripped):
                continue

            ent = shannon_entropy(v_stripped)
            if pat.min_entropy > 0 and ent < pat.min_entropy:
                continue

            risk = pat.risk
            if pat.context_keywords:
                if not value_has_context(text, v_stripped, pat.context_keywords):
                    risk = "MEDIUM"

            seen.add(v_stripped)
            snippet = (
                f"{v_stripped[:16]}...{v_stripped[-10:]}"
                if len(v_stripped) > 30 else v_stripped
            )
            findings.append(Finding(
                url=source_url,
                kind=pat.name,
                key_snippet=snippet,
                full_key=v_stripped,
                risk=risk,
            ))
    return findings


def build_header_regex(keys: List[str]) -> Pattern:
    key_alt = "|".join(re.escape(k) for k in keys)
    return re.compile(
        rf'(["\'](?:{key_alt})["\'])\s*[:=]\s*["\']([^"\']{{12,}})["\']',
        re.IGNORECASE,
    )


HEADER_REGEXES = {
    grp.name: (build_header_regex(grp.keys), grp.risk)
    for grp in HEADER_GROUPS
}


def scan_header_kv(text: str, source_url: str,
                   seen: Set[str]) -> Iterable[Finding]:
    findings: List[Finding] = []

    for group_name, (rx, risk) in HEADER_REGEXES.items():
        for m in rx.finditer(text):
            value = m.group(2).strip()
            if len(value) < 12:
                continue
            if value in seen:
                continue
            if is_probably_placeholder(value):
                continue
            if is_likely_non_secret_format(value):
                continue

            ent = shannon_entropy(value)
            if ent < 3.0:
                continue

            seen.add(value)
            snippet = (
                f"{value[:16]}...{value[-10:]}"
                if len(value) > 30 else value
            )
            findings.append(Finding(
                url=source_url,
                kind=group_name,
                key_snippet=snippet,
                full_key=value,
                risk=risk,
            ))
    return findings


def scan_text_for_secrets(
    text: str,
    source_url: str,
    seen: Set[str],
    cfg: Config,
) -> Iterable[Finding]:
    findings: List[Finding] = []
    findings.extend(
        scan_with_value_patterns(text, source_url, seen, cfg)
    )
    findings.extend(scan_header_kv(text, source_url, seen))
    return findings


def scan_url(url: str, cfg: Config) -> List[Finding]:
    session = requests.Session()
    html = fetch(url, session, cfg)
    if not html:
        return []

    seen_values: Set[str] = set()
    results: List[Finding] = []

    if cfg.include_html:
        results.extend(
            scan_text_for_secrets(html, url, seen_values, cfg)
        )

    script_urls = extract_script_urls(url, html)
    for s_url in sorted(script_urls):
        js = fetch(s_url, session, cfg)
        if not js:
            continue
        results.extend(
            scan_text_for_secrets(js, s_url, seen_values, cfg)
        )

    # Sort by risk
    results.sort(key=lambda f: RISK_ORDER.get(f.risk, 3))
    return results


# ===========================
#   Baseline / diff
# ===========================

def load_baseline(path: str) -> Set[Tuple[str, str]]:
    """
    Load baseline JSON and return set of (kind, full_key).
    Expects the JSON produced by this tool.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    findings = data.get("findings", [])
    keyset: Set[Tuple[str, str]] = set()
    for f in findings:
        kind = f.get("kind", "")
        full = f.get("full_key", "")
        if kind and full:
            keyset.add((kind, full))
    return keyset


def apply_diff(findings: List[Finding],
               baseline_keys: Set[Tuple[str, str]],
               only_new: bool) -> List[Finding]:
    for f in findings:
        if (f.kind, f.full_key) in baseline_keys:
            f.is_new = False
    if only_new:
        return [f for f in findings if f.is_new]
    return findings


# ===========================
#   Filtering & output
# ===========================

def filter_by_risk(findings: List[Finding], min_risk: str) -> List[Finding]:
    threshold = RISK_ORDER[min_risk]
    return [f for f in findings if RISK_ORDER.get(f.risk, 3) <= threshold]


def summarize_counts(findings: List[Finding]) -> Dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
    for f in findings:
        if f.risk in counts:
            counts[f.risk] += 1
    return counts


def print_human_readable(
    findings: List[Finding],
    cfg: Config,
    target_url: str,
    baseline_used: bool,
) -> None:
    if not findings:
        msg = "No candidate secrets found."
        print(colorize(msg, FG_GREEN, cfg.use_color))
        return

    counts = summarize_counts(findings)
    total = sum(counts.values())
    header_line = f"Found {total} candidate secrets " \
                  f"({counts['CRITICAL']} CRITICAL, " \
                  f"{counts['HIGH']} HIGH, {counts['MEDIUM']} MEDIUM)"

    if baseline_used:
        new_count = sum(1 for f in findings if f.is_new)
        header_line += f" | {new_count} NEW vs baseline"

    print(colorize(header_line, BOLD, cfg.use_color))
    print(colorize(f"Target: {target_url}", FG_DIM, cfg.use_color))
    print()

    header = f"{'RISK':<9} {'TYPE':<42} {'SNIPPET':<40} URL"
    print(colorize(header, BOLD, cfg.use_color))
    print("-" * len(header))

    for f in findings:
        kind = (f.kind[:39] + "...") if len(f.kind) > 42 else f.kind
        snippet = (f.key_snippet[:37] + "...") if len(f.key_snippet) > 40 else f.key_snippet

        risk_str = f.risk
        if f.risk == "CRITICAL":
            risk_str = colorize(risk_str, FG_RED + BOLD, cfg.use_color)
        elif f.risk == "HIGH":
            risk_str = colorize(risk_str, FG_YELLOW, cfg.use_color)
        else:
            risk_str = colorize(risk_str, FG_CYAN, cfg.use_color)

        if f.is_new and baseline_used:
            kind_display = colorize("[NEW] " + kind, FG_MAGENTA, cfg.use_color)
        else:
            kind_display = kind

        print(f"{risk_str:<9} {kind_display:<42} {snippet:<40} {f.url}")


def print_json_output(
    findings: List[Finding],
    cfg: Config,
    target_url: str,
    baseline_path: Optional[str],
) -> None:
    data = {
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "target_url": target_url,
        "include_html": cfg.include_html,
        "enable_generic": cfg.enable_generic,
        "min_risk": cfg.min_risk,
        "baseline": baseline_path,
        "findings": [
            {
                "url": f.url,
                "kind": f.kind,
                "risk": f.risk,
                "key_snippet": f.key_snippet,
                "full_key": f.full_key,
                "is_new": f.is_new,
            }
            for f in findings
        ],
    }
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


# ===========================
#   CLI
# ===========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Secret/token scanner for HTML and JavaScript assets."
    )
    parser.add_argument("url", help="Base URL to analyze (HTML page).")

    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Do not scan the main HTML body, only JavaScript assets.",
    )
    parser.add_argument(
        "--enable-generic",
        action="store_true",
        help="Enable heuristic detection of generic tokens (more findings, more FPs).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of a colored table.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress network error messages and info logs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose progress information to stderr.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in human-readable output.",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="Baseline JSON file (previous scan) to compare against.",
    )
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="With --baseline, show only findings not present in baseline.",
    )
    parser.add_argument(
        "--min-risk",
        choices=["MEDIUM", "HIGH", "CRITICAL"],
        default="MEDIUM",
        help="Minimum risk level to display (default: MEDIUM).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout in seconds (default: 10).",
    )

    args = parser.parse_args()

    # Determine if we should use colors
    use_color = (not args.no_color) and (not args.json) and sys.stdout.isatty()

    cfg = Config(
        include_html=not args.no_html,
        enable_generic=args.enable_generic,
        quiet=args.quiet,
        verbose=args.verbose,
        use_color=use_color,
        min_risk=args.min_risk,
        timeout=args.timeout,
    )

    findings = scan_url(args.url, cfg)

    if args.baseline:
        baseline_keys = load_baseline(args.baseline)
        findings = apply_diff(findings, baseline_keys, args.only_new)

    # Filter by risk threshold
    findings = filter_by_risk(findings, cfg.min_risk)

    baseline_used = args.baseline is not None

    if args.json:
        print_json_output(findings, cfg, args.url, args.baseline)
    else:
        print_human_readable(findings, cfg, args.url, baseline_used)


if __name__ == "__main__":
    main()
