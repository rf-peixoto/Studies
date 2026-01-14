#!/usr/bin/env python3
"""
  pip install requests beautifulsoup4 mmh3 rich pillow
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup
import mmh3
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

try:
    from PIL import Image
    from io import BytesIO
except Exception:
    Image = None  # type: ignore


console = Console()


@dataclass
class FaviconCandidate:
    source: str               # where we found it (link rel, fallback, file, etc.)
    url: str                  # resolved absolute URL, data: URI, or file path
    content_type: str = ""
    size_bytes: int = 0


@dataclass
class FaviconHashes:
    md5_hex: str
    sha256_hex: str
    shodan_mmh3: int          # mmh3 over base64 WITH newline (Shodan-compat)
    fofa_mmh3: int            # mmh3 over base64 WITHOUT newline (FOFA-typical)
    dhash_hex: Optional[str]  # 16-hex (64-bit) dHash if PIL available


ICON_RELS_PRIORITY = [
    "icon",
    "shortcut icon",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
    "mask-icon",
]


def normalize_input_to_base_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty input")

    # If user passed just a domain, assume https
    if "://" not in raw:
        raw = "https://" + raw

    p = urlparse(raw)
    if not p.netloc:
        raise ValueError(f"Invalid domain/URL: {raw}")

    return f"{p.scheme}://{p.netloc}/"


def http_get(url: str, timeout: int = 12) -> requests.Response:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0"}
    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def parse_favicon_links(html: str, base_url: str) -> List[FaviconCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    cands: List[FaviconCandidate] = []

    for link in soup.find_all("link"):
        rel = link.get("rel")
        href = link.get("href")
        if not href:
            continue

        # rel can be list like ['icon']
        rel_str = ""
        if isinstance(rel, list):
            rel_str = " ".join([str(x).strip().lower() for x in rel if x])
        elif isinstance(rel, str):
            rel_str = rel.strip().lower()

        if "icon" not in rel_str and "apple-touch-icon" not in rel_str and "mask-icon" not in rel_str:
            continue

        abs_url = href if href.startswith("data:") else urljoin(base_url, href)
        cands.append(FaviconCandidate(source=f"<link rel='{rel_str}'>", url=abs_url))

    # Sort by a rough priority of rel values
    def rel_score(src: str) -> int:
        src_l = src.lower()
        for i, r in enumerate(ICON_RELS_PRIORITY):
            if r in src_l:
                return i
        return len(ICON_RELS_PRIORITY) + 10

    cands.sort(key=lambda c: rel_score(c.source))
    return cands


def fallback_candidates(base_url: str) -> List[FaviconCandidate]:
    return [
        FaviconCandidate(source="fallback:/favicon.ico", url=urljoin(base_url, "favicon.ico")),
        FaviconCandidate(source="fallback:/favicon.png", url=urljoin(base_url, "favicon.png")),
    ]


_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[-\w.+/]+)?(;charset=[-\w]+)?(;base64)?,(?P<data>.*)$",
    re.IGNORECASE,
)


def fetch_favicon_bytes(candidate: FaviconCandidate, timeout: int = 12) -> Tuple[bytes, str]:
    """
    Returns (bytes, content_type)
    Supports:
      - data: URIs
      - http/https URLs
      - local files (path exists)
    """
    # Local file path support
    if os.path.isfile(candidate.url):
        with open(candidate.url, "rb") as f:
            data = f.read()

        # best-effort content-type by extension
        ext = os.path.splitext(candidate.url.lower())[1]
        if ext == ".ico":
            ctype = "image/x-icon"
        elif ext == ".png":
            ctype = "image/png"
        elif ext in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif ext == ".svg":
            ctype = "image/svg+xml"
        else:
            ctype = "application/octet-stream"

        return data, ctype

    # data: URI support
    if candidate.url.startswith("data:"):
        m = _DATA_URI_RE.match(candidate.url)
        if not m:
            raise ValueError("Invalid data: URI")
        mime = m.group("mime") or "application/octet-stream"
        data_part = m.group("data") or ""
        # data: URIs might be URL-escaped; but most favicon data URIs are base64
        # Try base64 first, fallback to raw percent-decoding if needed.
        try:
            raw = base64.b64decode(data_part, validate=False)
        except binascii.Error:
            raw = requests.utils.unquote_to_bytes(data_part)
        return raw, mime

    # http(s) URL support
    r = http_get(candidate.url, timeout=timeout)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return r.content, ctype or "application/octet-stream"


def b64_with_newline(data: bytes) -> bytes:
    # Shodan-style: base64 with a trailing newline (encodebytes inserts newlines; for small payloads it's just one at end).
    return base64.encodebytes(data)


def b64_no_newline(data: bytes) -> bytes:
    return base64.b64encode(data)


def mmh3_signed_int(data: bytes) -> int:
    # mmh3.hash returns a signed 32-bit int in Python bindings.
    return int(mmh3.hash(data))


def compute_dhash_hex(image_bytes: bytes) -> Optional[str]:
    if Image is None:
        return None

    try:
        img = Image.open(BytesIO(image_bytes)).convert("L")
        # Standard dHash: resize to 9x8, compare adjacent pixels horizontally
        img = img.resize((9, 8))
        pixels = list(img.getdata())
        rows = [pixels[i * 9:(i + 1) * 9] for i in range(8)]
        bits = []
        for row in rows:
            for x in range(8):
                bits.append(1 if row[x] > row[x + 1] else 0)
        # Pack into 64-bit
        v = 0
        for b in bits:
            v = (v << 1) | b
        return f"{v:016x}"
    except Exception:
        return None


def compute_hashes(favicon_bytes: bytes) -> FaviconHashes:
    md5_hex = hashlib.md5(favicon_bytes).hexdigest()
    sha256_hex = hashlib.sha256(favicon_bytes).hexdigest()

    shodan_payload = b64_with_newline(favicon_bytes)
    fofa_payload = b64_no_newline(favicon_bytes)

    shodan_mmh3 = mmh3_signed_int(shodan_payload)
    fofa_mmh3 = mmh3_signed_int(fofa_payload)

    dhash_hex = compute_dhash_hex(favicon_bytes)

    return FaviconHashes(
        md5_hex=md5_hex,
        sha256_hex=sha256_hex,
        shodan_mmh3=shodan_mmh3,
        fofa_mmh3=fofa_mmh3,
        dhash_hex=dhash_hex,
    )


def engine_queries(h: FaviconHashes) -> Dict[str, str]:
    """
    Queries to paste in each engine.
    If a platform is URL-only or has unclear public syntax, keep it conservative.
    """
    q: Dict[str, str] = {}

    # Core
    q["Shodan"] = f"http.favicon.hash:{h.shodan_mmh3}"
    q["FOFA"] = f'icon_hash="{h.fofa_mmh3}"'
    q["ZoomEye"] = f"iconhash:{h.shodan_mmh3}"

    # Censys has multiple favicon fields. Their dataset exposes a Shodan-compatible integer.
    q["Censys"] = f"services.http.response.favicons.shodan_hash:{h.shodan_mmh3}"

    # BinaryEdge fields
    q["BinaryEdge (mmh3)"] = f"favicon.mmh3:{h.shodan_mmh3}"
    q["BinaryEdge (md5)"] = f"favicon.md5:{h.md5_hex}"

    # Netlas supports sha256 + perceptual hash; provide sha256 exact match.
    q["Netlas (sha256)"] = f"http.favicon.hash_sha256:{h.sha256_hex}"

    # ONYPHE fields for favicon
    q["ONYPHE (mmh3)"] = f"app.favicon.imagemmh3:{h.shodan_mmh3}"
    q["ONYPHE (md5)"] = f"app.favicon.imagemd5:{h.md5_hex}"

    # Hunter.how commonly uses MD5 for favicon hash
    q["Hunter.how"] = f'favicon_hash="{h.md5_hex}"'

    # VirusTotal Intelligence uses visual hashes for icon similarity; provide dHash when available.
    if h.dhash_hex:
        q["VirusTotal Intel"] = f"entity:url main_icon_dhash:{h.dhash_hex}"
    else:
        q["VirusTotal Intel"] = "entity:url main_icon_dhash:<dhash_hex>  # Install pillow to compute automatically"

    return q


def engine_urls(queries: Dict[str, str]) -> Dict[str, str]:
    """
    Best-effort clickable URLs. Some platforms require auth; still useful to prefill search.
    """
    u: Dict[str, str] = {}
    for name, query in queries.items():
        qp = quote_plus(query)

        if name == "Shodan":
            u[name] = f"https://www.shodan.io/search?query={qp}"
        elif name == "FOFA":
            # FOFA web UI expects qbase64
            u[name] = f"https://en.fofa.info/result?qbase64={base64.b64encode(query.encode()).decode()}"
        elif name == "ZoomEye":
            u[name] = f"https://www.zoomeye.ai/searchResult?q={qp}"
        elif name.startswith("Censys"):
            u[name] = f"https://search.censys.io/search?resource=hosts&q={qp}"
        elif name.startswith("BinaryEdge"):
            u[name] = "https://app.binaryedge.io/"
        elif name.startswith("Netlas"):
            u[name] = f"https://app.netlas.io/responses/?q={qp}"
        elif name.startswith("ONYPHE"):
            u[name] = f"https://search.onyphe.io/?q={qp}"
        elif name == "Hunter.how":
            u[name] = f"https://hunter.how/search?q={qp}"
        elif name.startswith("VirusTotal"):
            u[name] = f"https://www.virustotal.com/gui/search/{qp}"
        else:
            u[name] = ""
    return u


def pick_best_candidate(cands: List[FaviconCandidate]) -> List[FaviconCandidate]:
    """
    Try candidates in order; return a shortlist (still hash multiple candidates).
    """
    return cands[:5] if len(cands) > 5 else cands


def is_probably_file_path(s: str) -> bool:
    s = s.strip()
    if not s:
        return False

    # If it exists as a file, treat as file input.
    if os.path.isfile(s):
        return True

    # Also accept file:// URIs if the file exists
    if s.lower().startswith("file://"):
        path = s[7:]
        return os.path.isfile(path)

    return False


def resolve_file_path(raw: str) -> str:
    raw = raw.strip()
    if raw.lower().startswith("file://"):
        raw = raw[7:]
    return raw


def render_single_candidate_result(candidate: FaviconCandidate, h: FaviconHashes):
    queries = engine_queries(h)
    urls = engine_urls(queries)

    info = Table(box=box.SIMPLE_HEAVY)
    info.add_column("Field", style="bold magenta", no_wrap=True)
    info.add_column("Value", style="white")

    info.add_row("Source", candidate.source)
    info.add_row("Location", candidate.url)
    info.add_row("Content-Type", candidate.content_type or "unknown")
    info.add_row("Size", f"{candidate.size_bytes} bytes")
    info.add_row("MD5", h.md5_hex)
    info.add_row("SHA-256", h.sha256_hex)
    info.add_row("MMH3 (Shodan)", str(h.shodan_mmh3))
    info.add_row("MMH3 (FOFA)", str(h.fofa_mmh3))
    info.add_row("dHash (VT)", h.dhash_hex or "n/a (install pillow)")

    console.print(Panel(info, title="[bold green]Favicon Hashes[/bold green]", border_style="green"))

    t = Table(title="Ready-to-paste Queries", box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Engine", style="bold")
    t.add_column("Query", style="white")
    t.add_column("Prefilled URL", style="dim")

    for eng, q in queries.items():
        link = urls.get(eng, "")
        t.add_row(eng, q, link)

    console.print(t)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute favicon hashes + print search-engine pivot queries.")
    ap.add_argument("domain", help="Domain/URL (e.g., example.com or https://example.com) OR a local favicon file path")
    ap.add_argument("--timeout", type=int, default=12, help="HTTP timeout seconds")
    ap.add_argument("--max-icons", type=int, default=3, help="Max favicon candidates to hash (top-N)")
    args = ap.parse_args()

    raw_target = args.domain

    # New feature: local file input
    if is_probably_file_path(raw_target):
        file_path = resolve_file_path(raw_target)
        header = Text()
        header.append("Favicon Pivot Builder", style="bold")
        header.append(f"\nInput: {file_path}", style="cyan")
        header.append("\nMode: local file", style="bright_blue")
        console.print(Panel(header, box=box.ROUNDED, border_style="bright_blue"))

        try:
            cand = FaviconCandidate(source="local_file", url=file_path)
            data, ctype = fetch_favicon_bytes(cand, timeout=args.timeout)
            cand.content_type = ctype
            cand.size_bytes = len(data)

            h = compute_hashes(data)
            render_single_candidate_result(cand, h)

            note = Text()
            note.append("Notes\n", style="bold")
            note.append("- Shodan’s favicon hash is MMH3 over base64 output that includes a trailing newline.\n", style="white")
            note.append("- FOFA icon_hash is commonly computed as MMH3 over base64 without the newline.\n", style="white")
            note.append("- Some engines store multiple favicon representations; pivots are strongest when you also combine title/body/ASN/SSL filters.\n", style="white")
            console.print(Panel(note, border_style="bright_black", box=box.ROUNDED))
            return 0
        except Exception as e:
            console.print(Panel(f"[bold red]Failed to read/hash local file:[/bold red] {file_path}\n{e}", border_style="red"))
            return 4

    # Domain/URL mode (existing behavior)
    try:
        base_url = normalize_input_to_base_url(raw_target)
    except Exception as e:
        console.print(f"[bold red]Input error:[/bold red] {e}")
        return 2

    # Fetch HTML (best-effort; if it fails, we still try fallbacks)
    html = ""
    html_err = None
    try:
        r = http_get(base_url, timeout=args.timeout)
        r.raise_for_status()
        html = r.text or ""
    except Exception as e:
        html_err = str(e)

    cands: List[FaviconCandidate] = []
    if html:
        cands.extend(parse_favicon_links(html, base_url))
    cands.extend(fallback_candidates(base_url))

    if not cands:
        console.print("[bold red]No favicon candidates found.[/bold red]")
        return 3

    cands = pick_best_candidate(cands)
    cands = cands[: max(1, args.max_icons)]

    header = Text()
    header.append("Favicon Pivot Builder", style="bold")
    header.append(f"\nTarget: {base_url}", style="cyan")
    header.append("\nMode: domain/url", style="bright_blue")
    if html_err:
        header.append("\nHTML fetch failed; using fallbacks only.", style="yellow")
        header.append(f"\nReason: {html_err}", style="dim")
    console.print(Panel(header, box=box.ROUNDED, border_style="bright_blue"))

    hashed_any = False

    for idx, c in enumerate(cands, start=1):
        try:
            data, ctype = fetch_favicon_bytes(c, timeout=args.timeout)
            c.content_type = ctype
            c.size_bytes = len(data)
            h = compute_hashes(data)

            info = Table(box=box.SIMPLE_HEAVY)
            info.add_column("Field", style="bold magenta", no_wrap=True)
            info.add_column("Value", style="white")

            info.add_row("Candidate", f"{idx}/{len(cands)}")
            info.add_row("Source", c.source)
            info.add_row("URL", c.url)
            info.add_row("Content-Type", c.content_type or "unknown")
            info.add_row("Size", f"{c.size_bytes} bytes")
            info.add_row("MD5", h.md5_hex)
            info.add_row("SHA-256", h.sha256_hex)
            info.add_row("MMH3 (Shodan)", str(h.shodan_mmh3))
            info.add_row("MMH3 (FOFA)", str(h.fofa_mmh3))
            info.add_row("dHash (VT)", h.dhash_hex or "n/a (install pillow)")

            console.print(Panel(info, title="[bold green]Favicon Hashes[/bold green]", border_style="green"))

            queries = engine_queries(h)
            urls = engine_urls(queries)

            t = Table(title="Ready-to-paste Queries", box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Engine", style="bold")
            t.add_column("Query", style="white")
            t.add_column("Prefilled URL", style="dim")

            for eng, q in queries.items():
                link = urls.get(eng, "")
                t.add_row(eng, q, link)

            console.print(t)

            hashed_any = True

        except Exception as e:
            console.print(Panel(f"[bold red]Failed candidate:[/bold red] {c.url}\n{e}", border_style="red"))

    if not hashed_any:
        console.print("[bold red]Could not fetch/hash any favicon candidate.[/bold red]")
        return 4

    # Small footnotes on “why two mmh3 values”
    note = Text()
    note.append("Notes\n", style="bold")
    note.append("- Shodan’s favicon hash is MMH3 over base64 output that includes a trailing newline.\n", style="white")
    note.append("- FOFA icon_hash is commonly computed as MMH3 over base64 without the newline.\n", style="white")
    note.append("- Some engines store multiple favicon representations; pivots are strongest when you also combine title/body/ASN/SSL filters.\n", style="white")
    console.print(Panel(note, border_style="bright_black", box=box.ROUNDED))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
