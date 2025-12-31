#!/usr/bin/env python3

# sudo dnf install -y chromium chromedriver
# python3 -m pip install --user -U selenium

import argparse
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService


# --- ANSI colors (no deps) ---
RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
MAGENTA = "\x1b[35m"


def color_enabled(no_color: bool) -> bool:
    return (not no_color) and sys.stdout.isatty()


def c(txt: str, code: str, enable: bool) -> str:
    return f"{code}{txt}{RESET}" if enable else txt


def sanitize_filename(text: str, max_len: int = 160) -> str:
    text = re.sub(r"[^\w.\-]+", "_", text.strip())
    text = text.strip("._-") or "item"
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    base = text[:max_len].rstrip("._-")
    return f"{base}__{h}.png"


def strip_inline_comment(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    return re.split(r"\s+#", line, maxsplit=1)[0].strip()


def has_scheme(s: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", s))


def expand_schemes(raw_line: str, both_schemes: bool) -> List[str]:
    raw = strip_inline_comment(raw_line)
    if not raw:
        return []

    if has_scheme(raw):
        parsed = urlparse(raw)
        return [raw] if parsed.netloc else []

    if both_schemes:
        out = []
        for scheme in ("https://", "http://"):
            u = scheme + raw
            if urlparse(u).netloc:
                out.append(u)
        return out

    u = "https://" + raw
    return [u] if urlparse(u).netloc else []


@dataclass
class CaptureResult:
    status: str  # OK, TIME, ERR, SKIP
    url: str
    out_name: str = ""
    ms: Optional[int] = None
    err: Optional[str] = None


def safe_err_str(e: Exception) -> str:
    s = str(e).strip()
    return s if s else e.__class__.__name__


def build_driver(
    *,
    headful: bool,
    timeout_ms: int,
    user_agent: str,
    chromium_binary: Optional[str],
    chromedriver_path: Optional[str],
) -> webdriver.Chrome:
    opts = Options()

    # Headless is the default for “Linux scripting”
    if not headful:
        # modern headless
        opts.add_argument("--headless=new")

    # Stability / compatibility flags
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--window-size=1366,768")

    # Normal UA
    opts.add_argument(f"--user-agent={user_agent}")

    if chromium_binary:
        opts.binary_location = chromium_binary

    service = ChromeService(executable_path=chromedriver_path) if chromedriver_path else ChromeService()
    driver = webdriver.Chrome(service=service, options=opts)

    # Selenium timeouts (page load)
    driver.set_page_load_timeout(max(1, timeout_ms // 1000))
    return driver


def format_line(idx: int, res: CaptureResult, raw_line: str, use_color: bool, verbose: bool) -> str:
    n = c(f"{idx:04d}", DIM, use_color)

    if res.status == "SKIP":
        label = c("SKIP", YELLOW, use_color)
        raw_disp = raw_line.strip()
        reason = c("(blank/comment/invalid)", DIM, use_color)
        return f"{n} {label} {raw_disp} {reason}"

    if res.status == "OK":
        label = c("OK", GREEN, use_color)
    elif res.status == "TIME":
        label = c("TIME", RED, use_color)
    else:
        label = c("ERR", RED, use_color)

    url_disp = c(res.url, CYAN, use_color)

    if not verbose and res.status == "OK":
        return f"{n} {label}   {url_disp} {c('->', DIM, use_color)} {res.out_name}"

    extras = []
    if verbose:
        if res.ms is not None:
            extras.append(f"{res.ms}ms")
        if res.out_name:
            extras.append(f"-> {res.out_name}")
        if res.err:
            extras.append(f"({res.err})")

    extra_txt = (" " + c(" ".join(extras), MAGENTA, use_color)) if extras else ""
    return f"{n} {label} {url_disp}{extra_txt}"


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("-i", "--input", default="domains.txt")
    ap.add_argument("-o", "--out", default="screenshots")
    ap.add_argument("--timeout", type=int, default=30000, help="Page-load timeout in ms")
    ap.add_argument("--wait", type=int, default=1000, help="Extra wait after load in ms")
    ap.add_argument("--retry", type=int, default=0, help="Retries for TIME/ERR")
    ap.add_argument("--rate-limit", type=int, default=0, help="Sleep between lines in ms")
    ap.add_argument("--both-schemes", action="store_true", help="Try https then http if scheme missing")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing screenshots")
    ap.add_argument("--headful", action="store_true", help="Visible browser (debug)")
    ap.add_argument("--verbose", action="store_true", help="Verbose debug output + errors.log")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--chromium", default=None, help="Path to Chromium/Chrome binary (optional)")
    ap.add_argument("--chromedriver", default=None, help="Path to chromedriver (optional)")
    args = ap.parse_args()

    use_color = color_enabled(args.no_color)

    src = Path(args.input)
    if not src.exists():
        print(f"{c('ERR', RED, use_color)} {args.input} -> missing file", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()

    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    errors_log = out_dir / "errors.log"
    if args.verbose:
        errors_log.write_text("", encoding="utf-8")

    # One driver reused for performance; restarted only if it becomes unhealthy.
    driver = None
    try:
        driver = build_driver(
            headful=args.headful,
            timeout_ms=args.timeout,
            user_agent=user_agent,
            chromium_binary=args.chromium,
            chromedriver_path=args.chromedriver,
        )

        for idx, raw_line in enumerate(lines, start=1):
            candidates = expand_schemes(raw_line, args.both_schemes)

            if not candidates:
                res = CaptureResult(status="SKIP", url="")
                print(format_line(idx, res, raw_line, use_color, args.verbose))
                continue

            final_res: Optional[CaptureResult] = None

            for url in candidates:
                filename = sanitize_filename(url)
                out_path = out_dir / filename

                if out_path.exists() and (not args.overwrite):
                    final_res = CaptureResult(status="OK", url=url, out_name=out_path.name, ms=(0 if args.verbose else None),
                                             err=("exists" if args.verbose else None))
                    break

                attempts = 1 + max(0, int(args.retry))
                for attempt in range(1, attempts + 1):
                    t0 = time.time()
                    try:
                        driver.get(url)
                        if args.wait > 0:
                            time.sleep(args.wait / 1000.0)

                        # NOTE: Selenium captures the *current viewport*. To approximate “full page”:
                        # set a tall window. This is reliable enough for many use cases.
                        # If you require true full-page stitching, that is a separate feature.
                        driver.set_window_size(1366, 8000)

                        ok = driver.save_screenshot(str(out_path))
                        ms = int((time.time() - t0) * 1000)

                        if ok:
                            final_res = CaptureResult(status="OK", url=url, out_name=out_path.name, ms=ms)
                            break
                        final_res = CaptureResult(status="ERR", url=url, ms=ms, err=("save_screenshot failed" if args.verbose else None))

                    except TimeoutException as e:
                        ms = int((time.time() - t0) * 1000)
                        final_res = CaptureResult(status="TIME", url=url, ms=ms, err=(safe_err_str(e) if args.verbose else None))

                    except WebDriverException as e:
                        ms = int((time.time() - t0) * 1000)
                        final_res = CaptureResult(status="ERR", url=url, ms=ms, err=(safe_err_str(e) if args.verbose else None))

                        # If the driver got into a bad state, restart it once.
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = build_driver(
                            headful=args.headful,
                            timeout_ms=args.timeout,
                            user_agent=user_agent,
                            chromium_binary=args.chromium,
                            chromedriver_path=args.chromedriver,
                        )

                    except Exception as e:
                        ms = int((time.time() - t0) * 1000)
                        final_res = CaptureResult(status="ERR", url=url, ms=ms, err=(safe_err_str(e) if args.verbose else None))
                    if final_res and final_res.status == "OK":
                        break
                    if attempt < attempts:
                        time.sleep(0.25)
                if final_res and final_res.status == "OK":
                    break

            if final_res is None:
                final_res = CaptureResult(status="ERR", url=candidates[0], err=("internal" if args.verbose else None))
            print(format_line(idx, final_res, raw_line, use_color, args.verbose))
            if args.verbose and final_res.status in ("TIME", "ERR"):
                with errors_log.open("a", encoding="utf-8") as f:
                    f.write(f"{idx}\t{final_res.url}\t{final_res.status}\t{final_res.err or ''}\n")
            if args.rate_limit > 0:
                time.sleep(args.rate_limit / 1000.0)

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
