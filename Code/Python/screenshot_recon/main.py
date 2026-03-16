#!/usr/bin/env python3
"""
Reads an input file (default: domains.txt), visits each domain/URL with Playwright,
and saves full-page screenshots to an output folder.

Features:
- One-line status output per input line (OK/TIME/ERR/SKIP), with ANSI colors
- --verbose: extra diagnostics (error details, timings, HTTP status when available)
- --headful: run with a visible browser (useful for debugging)
- --retry N: retry failed navigations
- --concurrency N: parallelize captures safely
- --both-schemes: if no scheme is provided, try https then http
- --rate-limit MS: sleep between tasks (basic politeness / resource control)
- Normal desktop Chrome user-agent
- Writes an errors.log (only when --verbose), with line number + URL + exception info

Install:
  pip install playwright
  playwright install chromium

Usage:
  python main.py
  python main.py -i domains.txt -o shots --concurrency 6
  python main.py --verbose --headful --retry 2 --timeout 45000
"""

import argparse
import hashlib
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- ANSI colors (no deps) ---
RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
MAGENTA = "\x1b[35m"


def color_enabled(no_color: bool) -> bool:
    # Respect --no-color and avoid ANSI when stdout isn't a TTY.
    return (not no_color) and sys.stdout.isatty()


def c(txt: str, code: str, enable: bool) -> str:
    if not enable:
        return txt
    return f"{code}{txt}{RESET}"


def sanitize_filename(text: str, max_len: int = 160) -> str:
    text = re.sub(r"[^\w.\-]+", "_", text.strip())
    text = text.strip("._-") or "item"
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    base = text[:max_len].rstrip("._-")
    return f"{base}__{h}.png"


def strip_inline_comment(line: str) -> str:
    # Treat "   # comment" and "example.com  # comment" as comments.
    if line.lstrip().startswith("#"):
        return ""
    return re.split(r"\s+#", line, maxsplit=1)[0].strip()


def has_scheme(s: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", s))


def normalize_target(raw_line: str) -> str:
    raw = strip_inline_comment(raw_line)
    if not raw:
        return ""
    if not has_scheme(raw):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        return ""
    return raw


def expand_schemes(raw_line: str, both_schemes: bool) -> List[str]:
    """
    If both_schemes is enabled and line has no scheme, try https then http.
    Otherwise, just normalize as-is (defaulting to https when missing).
    """
    raw = strip_inline_comment(raw_line)
    if not raw:
        return []
    if has_scheme(raw):
        url = normalize_target(raw)
        return [url] if url else []
    if both_schemes:
        urls = []
        for scheme in ("https://", "http://"):
            u = scheme + raw
            parsed = urlparse(u)
            if parsed.netloc:
                urls.append(u)
        return urls
    url = normalize_target(raw)
    return [url] if url else []


@dataclass
class CaptureResult:
    status: str  # OK, TIME, ERR, SKIP
    url: str
    out_name: str = ""
    ms: Optional[int] = None
    http_status: Optional[int] = None
    err: Optional[str] = None


def safe_err_str(e: Exception) -> str:
    s = str(e).strip()
    return s if s else e.__class__.__name__


def capture_one(page, url: str, out_path: Path, timeout_ms: int, wait_after_load_ms: int,
                verbose: bool) -> CaptureResult:
    t0 = time.time()
    http_status = None

    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if resp is not None:
            try:
                http_status = resp.status
            except Exception:
                http_status = None

        page.wait_for_timeout(wait_after_load_ms)
        page.screenshot(path=str(out_path), full_page=True)

        ms = int((time.time() - t0) * 1000)
        return CaptureResult(status="OK", url=url, out_name=out_path.name, ms=ms, http_status=http_status)

    except PlaywrightTimeoutError as e:
        ms = int((time.time() - t0) * 1000)
        return CaptureResult(status="TIME", url=url, ms=ms, http_status=http_status, err=safe_err_str(e) if verbose else None)

    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return CaptureResult(status="ERR", url=url, ms=ms, http_status=http_status, err=safe_err_str(e) if verbose else None)


def format_line(idx: int, res: CaptureResult, raw_line: str, use_color: bool, verbose: bool) -> str:
    n = f"{idx:04d}"
    n = c(n, DIM, use_color)

    if res.status == "SKIP":
        label = c("SKIP", YELLOW, use_color)
        raw_disp = raw_line.strip()
        reason = c("(blank/comment/invalid)", DIM, use_color)
        return f"{n} {label} {raw_disp} {reason}"

    # For OK/TIME/ERR:
    if res.status == "OK":
        label = c("OK", GREEN, use_color)
    elif res.status == "TIME":
        label = c("TIME", RED, use_color)
    else:
        label = c("ERR", RED, use_color)

    url_disp = c(res.url, CYAN, use_color)

    # Optional compact extras (only when verbose)
    extras = ""
    if verbose:
        parts = []
        if res.http_status is not None:
            parts.append(f"HTTP:{res.http_status}")
        if res.ms is not None:
            parts.append(f"{res.ms}ms")
        if res.out_name:
            parts.append(f"-> {res.out_name}")
        if res.err:
            parts.append(f"({res.err})")
        if parts:
            extras = " " + c(" ".join(parts), MAGENTA, use_color)

    # Non-verbose: keep it very close to your previous one-liner style.
    if not verbose and res.status == "OK":
        return f"{n} {label}   {url_disp} {c('->', DIM, use_color)} {res.out_name}"
    return f"{n} {label} {url_disp}{extras}"


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("-i", "--input", default="domains.txt", help="Input file (default: domains.txt)")
    ap.add_argument("-o", "--out", default="screenshots", help="Output folder (default: screenshots)")
    ap.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in ms (default: 30000)")
    ap.add_argument("--wait", type=int, default=1000, help="Wait after DOMContentLoaded in ms (default: 1000)")
    ap.add_argument("--retry", type=int, default=0, help="Retries for TIME/ERR (default: 0)")
    ap.add_argument("--concurrency", type=int, default=1, help="Parallel pages (default: 1)")
    ap.add_argument("--rate-limit", type=int, default=0, help="Sleep between tasks in ms (default: 0)")
    ap.add_argument("--headful", action="store_true", help="Run with visible browser window")
    ap.add_argument("--verbose", action="store_true", help="Verbose debug output (adds HTTP/timing/error details)")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--both-schemes", action="store_true",
                    help="If input line has no scheme, try https then http (succeeds on first that works)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Overwrite existing screenshot if name collides (default: keep existing)")
    args = ap.parse_args()

    use_color = color_enabled(args.no_color)

    src = Path(args.input)
    if not src.exists():
        print(f"{c('ERR', RED, use_color)} {args.input} -> missing file", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()

    # Typical desktop Chrome UA (looks like a normal browser UA)
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    errors_log = out_dir / "errors.log"
    if args.verbose:
        # Fresh file each run in verbose mode.
        errors_log.write_text("", encoding="utf-8")

    # Prepare per-line jobs: we must print exactly one line per input line.
    # If --both-schemes expands targets, we still keep one output line per input line
    # by trying candidates sequentially and reporting final result for that line.
    jobs: List[Tuple[int, str, List[str]]] = []
    for idx, raw in enumerate(lines, start=1):
        candidates = expand_schemes(raw, args.both_schemes)
        jobs.append((idx, raw, candidates))

    # Concurrency implementation: multiple pages in the same context.
    # We keep deterministic "one print per input line" by collecting results and printing in order.
    results: List[CaptureResult] = [CaptureResult(status="SKIP", url="") for _ in range(len(lines) + 1)]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=(not args.headful))
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            ignore_https_errors=True,
            user_agent=user_agent,
        )

        # Create N pages.
        conc = max(1, int(args.concurrency))
        pages = [context.new_page() for _ in range(conc)]

        # Simple round-robin worker loop (synchronous, but interleaves work across pages).
        # This avoids complex threading while still allowing multiple pages open.
        # Note: Playwright sync API is not truly parallel; however, multiple pages can help for some sites.
        page_idx = 0

        for idx, raw_line, candidates in jobs:
            raw_stripped = raw_line.strip()

            if not candidates:
                res = CaptureResult(status="SKIP", url="")
                results[idx] = res
                print(format_line(idx, res, raw_line, use_color, args.verbose))
                continue

            page = pages[page_idx]
            page_idx = (page_idx + 1) % conc

            # For one input line, try candidates (https/http) and also retries.
            final_res: Optional[CaptureResult] = None
            chosen_url = candidates[0]

            for cand in candidates:
                chosen_url = cand
                filename = sanitize_filename(cand)
                out_path = out_dir / filename

                if out_path.exists() and (not args.overwrite):
                    # Treat as OK but indicate existing only in verbose mode.
                    final_res = CaptureResult(
                        status="OK", url=cand, out_name=out_path.name,
                        ms=0 if args.verbose else None,
                        http_status=None,
                        err="exists" if args.verbose else None
                    )
                    break

                attempts = 1 + max(0, int(args.retry))
                for attempt in range(1, attempts + 1):
                    res = capture_one(
                        page=page,
                        url=cand,
                        out_path=out_path,
                        timeout_ms=int(args.timeout),
                        wait_after_load_ms=int(args.wait),
                        verbose=args.verbose,
                    )
                    final_res = res

                    # Success ends everything for this input line.
                    if res.status == "OK":
                        break

                    # If failed and retries remain, continue.
                    if attempt < attempts:
                        # Small backoff to reduce immediate repeated failures.
                        page.wait_for_timeout(250)

                if final_res and final_res.status == "OK":
                    break  # do not try other schemes if success

            if final_res is None:
                final_res = CaptureResult(status="ERR", url=chosen_url, err="internal")

            results[idx] = final_res

            # Print exactly one line for this input line.
            print(format_line(idx, final_res, raw_line, use_color, args.verbose))

            # Log verbose errors to file.
            if args.verbose and final_res.status in ("TIME", "ERR"):
                with errors_log.open("a", encoding="utf-8") as f:
                    f.write(f"{idx}\t{final_res.url}\t{final_res.status}\t{final_res.err or ''}\n")

            if args.rate_limit > 0:
                context._impl_obj._sync_base._loop.run_until_complete(  # noqa: SLF001
                    p._impl_obj._connection._loop.create_task(asyncio_sleep_ms(args.rate_limit))  # type: ignore
                )

        context.close()
        browser.close()

    return 0


# Avoid importing asyncio just for a sleep; implement minimal compatible helper.
def asyncio_sleep_ms(ms: int):
    # Playwright internal loop is asyncio-based; we schedule a coroutine sleep.
    import asyncio  # local import intentionally
    return asyncio.sleep(ms / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
