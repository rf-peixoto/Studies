#!/usr/bin/env python3
import argparse
import math
import re
import sys
from dataclasses import dataclass
from typing import List, Set, Iterable, Pattern, Optional
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
    min_length: int = 0       # comprimento mínimo do match
    min_entropy: float = 0.0  # entropia mínima p/ caractere (0 = sem checagem)
    context_keywords: Optional[List[str]] = None  # palavras que aumentam confiança


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


# ===========================
#   Utils
# ===========================

def shannon_entropy(s: str) -> float:
    """
    Entropia de Shannon por caractere.
    Strings de alta aleatoriedade tendem a ficar > ~3.5–4 bits/char.
    """
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


def is_probably_placeholder(value: str) -> bool:
    v = value.strip().strip('"').strip("'")
    if len(v) < 8:
        return True
    for rx in PLACEHOLDER_PATTERNS:
        if rx.search(v):
            return True
    return False


def value_has_context(text: str, value: str, keywords: List[str]) -> bool:
    """
    Verifica se, perto do valor, existe algum keyword (ex: token, secret, key).
    """
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

VALUE_PATTERNS: List[SecretPattern] = [
    # Específicos (raramente FP)
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

    # Genéricos – restringidos por entropia e contexto
    SecretPattern(
        name="Generic long base64-like secret",
        regex=re.compile(r'"([A-Za-z0-9+/]{40,}={0,2})"'),
        risk="HIGH",
        min_length=40,
        min_entropy=3.8,
        context_keywords=["token", "secret", "key", "auth", "signature"],
    ),
    SecretPattern(
        name="Generic long token",
        regex=re.compile(r'\b[A-Za-z0-9_\-]{32,}\b'),
        risk="HIGH",
        min_length=32,
        min_entropy=3.8,
        context_keywords=["token", "secret", "key", "auth", "session", "id"],
    ),
]

# Headers agrupados (mesma lista da versão anterior)
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
#   Network / parsing
# ===========================

def fetch(url: str, session: requests.Session, timeout: int = 10) -> str:
    try:
        resp = session.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0"
        })
        resp.raise_for_status()
        return resp.text
    except Exception as e:
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

def scan_with_value_patterns(text: str, source_url: str,
                             seen: Set[str]) -> Iterable[Finding]:
    findings: List[Finding] = []

    for pat in VALUE_PATTERNS:
        for m in pat.regex.finditer(text):
            v = m.group(0)
            v_stripped = v.strip('"').strip("'")

            if len(v_stripped) < max(1, pat.min_length):
                continue
            if v_stripped in seen:
                continue
            if is_probably_placeholder(v_stripped):
                continue

            ent = shannon_entropy(v_stripped)
            if pat.min_entropy > 0 and ent < pat.min_entropy:
                continue

            if pat.context_keywords:
                if not value_has_context(text, v_stripped, pat.context_keywords):
                    risk = "MEDIUM"
                else:
                    risk = pat.risk
            else:
                risk = pat.risk

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

            ent = shannon_entropy(value)
            # define noise:
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


def scan_text_for_secrets(text: str, source_url: str,
                          seen: Set[str]) -> Iterable[Finding]:
    findings: List[Finding] = []
    findings.extend(scan_with_value_patterns(text, source_url, seen))
    findings.extend(scan_header_kv(text, source_url, seen))
    return findings


def scan_url(url: str, include_html: bool = True) -> List[Finding]:
    session = requests.Session()
    html = fetch(url, session)
    if not html:
        return []

    seen_values: Set[str] = set()
    results: List[Finding] = []

    if include_html:
        results.extend(scan_text_for_secrets(html, url, seen_values))

    script_urls = extract_script_urls(url, html)
    for s_url in sorted(script_urls):
        js = fetch(s_url, session)
        if not js:
            continue
        results.extend(scan_text_for_secrets(js, s_url, seen_values))

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    results.sort(key=lambda f: order.get(f.risk, 3))
    return results


# ===========================
#   Output
# ===========================

def print_findings(findings: List[Finding]) -> None:
    if not findings:
        print("No candidate secrets found.")
        return

    total_crit = sum(1 for f in findings if f.risk == "CRITICAL")
    print(f"Found {len(findings)} candidate secrets "
          f"({total_crit} CRITICAL):\n")

    header = f"{'RISK':<9} {'TYPE':<40} {'SNIPPET':<40} URL"
    print(header)
    print("-" * len(header))
    for f in findings:
        kind = (f.kind[:37] + "...") if len(f.kind) > 40 else f.kind
        snippet = (f.key_snippet[:37] + "...") if len(f.key_snippet) > 40 else f.key_snippet
        print(f"{f.risk:<9} {kind:<40} {snippet:<40} {f.url}")


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
    args = parser.parse_args()

    findings = scan_url(args.url, include_html=not args.no_html)
    print_findings(findings)


if __name__ == "__main__":
    main()
