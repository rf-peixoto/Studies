#!/usr/bin/env python3
"""
github_domain_search.py

Search GitHub code results for exact domain strings, page through the first 5 pages,
print minimal colored output, and save one TXT file per domain with the links found.

Usage examples:
    export GITHUB_TOKEN="ghp_xxxxxxxxx"
    python3 github_domain_search.py --domain example.com
    python3 github_domain_search.py --file domains.txt
    python3 github_domain_search.py --file domains.txt --delay 3.0 --pages 5

Notes:
- Uses GitHub REST API code search.
- Reads GITHUB_TOKEN from the environment.
- Saves outputs under ./results/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Iterable


API_BASE = "https://api.github.com"
SEARCH_ENDPOINT = f"{API_BASE}/search/code"
RATE_LIMIT_ENDPOINT = f"{API_BASE}/rate_limit"

DEFAULT_PAGES = 5
DEFAULT_PER_PAGE = 100
DEFAULT_DELAY = 2.5
RESULTS_DIR = Path("results")


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def color(text: str, tone: str) -> str:
    return f"{tone}{text}{C.RESET}"


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

    deduped = []
    seen = set()
    for d in domains:
        if d not in seen:
            seen.add(d)
            deduped.append(d)

    return deduped


def build_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-domain-search-script",
    }


def api_get_json(url: str, headers: dict[str, str]) -> tuple[dict, dict[str, str]]:
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
        headers_out = dict(e.headers.items()) if e.headers else {}
        raise RuntimeError(
            f"HTTP {e.code}: {data.get('message', 'Unknown API error')}"
        ) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e}") from None


def read_code_search_bucket(headers: dict[str, str]) -> tuple[int | None, int | None]:
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    try:
        rem_int = int(remaining) if remaining is not None else None
    except ValueError:
        rem_int = None
    try:
        reset_int = int(reset) if reset is not None else None
    except ValueError:
        reset_int = None
    return rem_int, reset_int


def get_rate_limit_status(token: str) -> tuple[int | None, int | None]:
    headers = build_headers(token)
    data, _ = api_get_json(RATE_LIMIT_ENDPOINT, headers)
    resources = data.get("resources", {})
    code_search = resources.get("code_search", {})
    remaining = code_search.get("remaining")
    reset = code_search.get("reset")
    return remaining, reset


def wait_until_reset(reset_epoch: int, extra_seconds: int = 3) -> None:
    now = int(time.time())
    sleep_for = max(0, reset_epoch - now + extra_seconds)
    if sleep_for > 0:
        print(
            color("[!] Rate limit reached. Waiting ", C.YELLOW)
            + color(f"{sleep_for}s", C.BOLD + C.YELLOW)
        )
        time.sleep(sleep_for)


def build_search_url(domain: str, page: int, per_page: int) -> str:
    # Exact string search for the target domain.
    query = f"\"{domain}\""
    params = {
        "q": query,
        "page": page,
        "per_page": per_page,
    }
    return SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def extract_links(items: Iterable[dict]) -> list[str]:
    links: list[str] = []

    for item in items:
        html_url = item.get("html_url")
        if html_url:
            links.append(html_url)
            continue

        repo = item.get("repository", {}).get("full_name")
        path = item.get("path")
        sha = item.get("sha")
        if repo and path and sha:
            links.append(f"https://github.com/{repo}/blob/{sha}/{path}")

    # stable dedupe
    deduped = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def search_domain(
    token: str,
    domain: str,
    pages: int,
    per_page: int,
    delay: float,
) -> list[str]:
    headers = build_headers(token)
    found: list[str] = []

    print(color(f"\n[>] Searching: ", C.CYAN) + color(domain, C.BOLD + C.CYAN))

    for page in range(1, pages + 1):
        # proactive rate-limit check
        remaining, reset = get_rate_limit_status(token)
        if remaining is not None and remaining <= 0 and reset is not None:
            wait_until_reset(reset)

        url = build_search_url(domain, page, per_page)

        try:
            data, resp_headers = api_get_json(url, headers)
        except RuntimeError as exc:
            msg = str(exc)
            if "HTTP 403" in msg:
                remaining, reset = get_rate_limit_status(token)
                if remaining is not None and remaining <= 0 and reset is not None:
                    wait_until_reset(reset)
                    data, resp_headers = api_get_json(url, headers)
                else:
                    print(color(f"[!] Page {page}: {msg}", C.RED))
                    break
            else:
                print(color(f"[!] Page {page}: {msg}", C.RED))
                break

        items = data.get("items", [])
        page_links = extract_links(items)

        print(
            color("  [-] Page ", C.GRAY)
            + color(str(page), C.BOLD + C.GRAY)
            + color(" -> ", C.GRAY)
            + color(f"{len(page_links)} links", C.GRAY)
        )

        for link in page_links:
            if link not in found:
                found.append(link)
                print(color("      + ", C.GREEN) + link)

        # if nothing came back, no reason to keep paging
        if not items:
            break

        # reactive header-based handling
        header_remaining, header_reset = read_code_search_bucket(resp_headers)
        if header_remaining is not None and header_remaining <= 0 and header_reset is not None:
            wait_until_reset(header_reset)
        else:
            time.sleep(delay)

    return found


def save_results(domain: str, links: list[str], outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    output_file = outdir / f"{sanitize_filename(domain)}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for link in links:
            f.write(link + "\n")
    return output_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search GitHub code results for exact domain strings."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--domain", help="Single domain to search for")
    src.add_argument("--file", help="TXT file containing one domain per line")

    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_PAGES,
        help=f"How many pages to fetch per domain (default: {DEFAULT_PAGES})",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
        help=f"Results per page (default: {DEFAULT_PER_PAGE})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--outdir",
        default=str(RESULTS_DIR),
        help=f"Directory to save result files (default: {RESULTS_DIR})",
    )

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
    print(color("[*] Total domains: ", C.BLUE) + str(len(domains)))
    print(color("[*] Pages/domain: ", C.BLUE) + str(args.pages))
    print(color("[*] Delay/request: ", C.BLUE) + f"{args.delay:.1f}s")

    for domain in domains:
        try:
            links = search_domain(
                token=token,
                domain=domain,
                pages=args.pages,
                per_page=args.per_page,
                delay=args.delay,
            )
            output_file = save_results(domain, links, outdir)
            print(
                color("[+] Saved ", C.GREEN)
                + color(str(len(links)), C.BOLD + C.GREEN)
                + color(" links -> ", C.GREEN)
                + str(output_file)
            )
        except KeyboardInterrupt:
            print(color("\n[!] Interrupted by user.", C.RED))
            return 130
        except Exception as exc:
            print(color(f"[!] Error for {domain}: {exc}", C.RED))

    print(color("\n[✓] Done.", C.BOLD + C.GREEN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
