#!/usr/bin/env python3
"""
batch_screenshot.py

Reads URLs from a text file and for each:
 • Sends a HEAD request (following redirects) and logs the chain
 • Rotates User-Agent via CDP
 • Waits for document.readyState == "complete"
 • Captures a full-page screenshot via DevTools Protocol
 • On permanent failure, generates a placeholder PNG
 • Records per-URL metadata (including redirects) in JSON
 • Logs every step with timestamps and levels

Dependencies:
    pip install selenium webdriver-manager requests pillow
"""

import os
import sys
import time
import json
import random
import logging
import argparse
import base64
import requests

from datetime import datetime
from urllib.parse import urlparse
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from webdriver_manager.chrome import ChromeDriverManager

# Pillow for placeholder images
try:
    from PIL import Image
except ImportError:
    print(
        "ERROR: Pillow is required for placeholder image generation.\n"
        "Install via: pip install pillow",
        file=sys.stderr
    )
    sys.exit(1)

# A small selection of common User-Agents; you may extend or replace these.
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:101.0) "
    "Gecko/20100101 Firefox/101.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/14.0 Mobile/15E148 Safari/604.1"
]


def read_urls(path):
    """Read one URL or domain per line, skip comments/blanks, prepend http:// if missing."""
    urls = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            u = line.strip()
            if not u or u.startswith('#'):
                continue
            if not u.startswith(('http://', 'https://')):
                u = 'http://' + u
            urls.append(u)
    return urls


def domain_to_filename(url):
    """Convert URL’s host to a safe filename (host.png)."""
    host = urlparse(url).netloc
    return f"{host}.png"


def setup_driver(args):
    """Initialize Chrome in headless mode with a fixed viewport."""
    opts = ChromeOptions()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument(f'--window-size={args.viewport_width},{args.viewport_height}')
    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=opts
    )
    # Enable network domain so we can override UA per-request
    driver.execute_cdp_cmd('Network.enable', {})
    return driver


@contextmanager
def managed_driver(args):
    """Ensure driver.quit() even on errors."""
    driver = setup_driver(args)
    try:
        yield driver
    finally:
        driver.quit()


def capture_fullpage_cdp(driver, args, url, out_path, ua):
    """
    1. Override UA via CDP
    2. Navigate → wait for readyState == 'complete'
    3. Resize to full content and capture screenshot
    """
    # 1) Set the chosen User-Agent
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        'userAgent': ua
    })

    # 2) Navigate
    driver.get(url)
    WebDriverWait(driver, args.wait_timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )

    # 3) Capture dimensions & override viewport
    metrics = driver.execute_cdp_cmd('Page.getLayoutMetrics', {})
    width = metrics['contentSize']['width']
    height = metrics['contentSize']['height']
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'mobile': False,
        'width': width,
        'height': height,
        'deviceScaleFactor': 1,
        'screenOrientation': {'angle': 0, 'type': 'portraitPrimary'}
    })

    # 4) Take the screenshot
    data = driver.execute_cdp_cmd('Page.captureScreenshot', {
        'fromSurface': True,
        'captureBeyondViewport': True
    })['data']
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(data))


def make_placeholder(path, width, height):
    """Generate a solid-grey placeholder PNG of the given dimensions."""
    img = Image.new('RGB', (width, height), color=(200, 200, 200))
    img.save(path)


def main():
    p = argparse.ArgumentParser(
        description="Batch full-page screenshots with rotating UA, delays, "
                    "redirect logging, and error placeholders."
    )
    p.add_argument('-i', '--input', default='domains.txt',
                   help="Text file with one URL/domain per line.")
    p.add_argument('-o', '--output', default='screenshots',
                   help="Directory to save screenshots.")
    p.add_argument('-m', '--metadata', default='metadata.json',
                   help="Path for the output JSON metadata.")
    p.add_argument('--ua-file', default=None,
                   help="Optional file listing one User-Agent per line.")
    p.add_argument('--delay', type=float, default=5.0,
                   help="Delay between processing each URL (seconds).")
    p.add_argument('-r', '--retries', type=int, default=3,
                   help="How many times to retry screenshot on failure.")
    p.add_argument('-w', '--wait-timeout', type=int, default=30,
                   help="Seconds to wait for document.readyState == 'complete'.")
    p.add_argument('--viewport-width', type=int, default=1920,
                   help="Initial browser viewport width for placeholder image.")
    p.add_argument('--viewport-height', type=int, default=1080,
                   help="Initial browser viewport height for placeholder image.")
    p.add_argument('--log-file', default='batch_screenshot.log',
                   help="Path to the structured log file.")
    args = p.parse_args()

    # Prepare output
    os.makedirs(args.output, exist_ok=True)

    # Load or default User-Agents
    if args.ua_file:
        with open(args.ua_file, 'r', encoding='utf-8') as f:
            user_agents = [line.strip() for line in f if line.strip()]
    else:
        user_agents = DEFAULT_USER_AGENTS

    # Configure logging
    logging.basicConfig(
        filename=args.log_file,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    logging.getLogger().addHandler(console)

    urls = read_urls(args.input)
    if not urls:
        logging.error("No URLs found in input file.")
        sys.exit(1)

    metadata = []
    successes = failures = 0

    with managed_driver(args) as driver:
        for url in urls:
            ts = datetime.now().astimezone().isoformat()
            entry = {
                'url': url,
                'timestamp': ts,
                'status_code': None,
                'redirects': [],
                'selenium_final_url': None,
                'user_agent': None,
                'screenshot': None,
                'error': None
            }

            # 1) HEAD request (follow redirects)
            try:
                resp = requests.head(url, timeout=10, allow_redirects=True)
                entry['status_code'] = resp.status_code
                # log and store any redirect chain
                chain = [r.url for r in resp.history] + [resp.url]
                if len(chain) > 1:
                    logging.info("HTTP redirect chain for %s: %s",
                                 url, " -> ".join(chain))
                    entry['redirects'] = chain
                if resp.status_code >= 400:
                    msg = f"HEAD returned {resp.status_code}; skipping"
                    logging.warning("%s: %s", url, msg)
                    entry['error'] = msg
                    metadata.append(entry)
                    failures += 1
                    time.sleep(args.delay)
                    continue
            except Exception as e:
                entry['error'] = f"HEAD failed: {e}"
                logging.error("HEAD %s error: %s", url, e)
                metadata.append(entry)
                failures += 1
                time.sleep(args.delay)
                continue

            # 2) Pick a random UA and attempt screenshot
            ua = random.choice(user_agents)
            entry['user_agent'] = ua

            out_file = os.path.join(args.output, domain_to_filename(url))
            for attempt in range(1, args.retries + 1):
                try:
                    capture_fullpage_cdp(driver, args, url, out_file, ua)
                    # log any Selenium-side redirect
                    final = driver.current_url
                    if final != url:
                        logging.info("Selenium redirected %s -> %s", url, final)
                        entry['selenium_final_url'] = final
                    entry['screenshot'] = out_file
                    successes += 1
                    logging.info("Captured %s → %s", url, out_file)
                    break
                except Exception as e:
                    backoff = 2 ** (attempt - 1)
                    logging.warning(
                        "Attempt %d for %s failed: %s; retrying in %ds",
                        attempt, url, e, backoff
                    )
                    time.sleep(backoff)
            else:
                # all attempts failed → generate placeholder
                make_placeholder(
                    out_file,
                    args.viewport_width,
                    args.viewport_height
                )
                entry['screenshot'] = out_file
                entry['error'] = f"All {args.retries} attempts failed; placeholder generated"
                failures += 1
                logging.error("%s: %s", url, entry['error'])

            metadata.append(entry)
            time.sleep(args.delay)

    # Write metadata JSON
    with open(args.metadata, 'w', encoding='utf-8') as mf:
        json.dump(metadata, mf, ensure_ascii=False, indent=2)

    # Final summary
    total = len(urls)
    summary = (
        f"Total URLs : {total}\n"
        f"Successes  : {successes}\n"
        f"Failures   : {failures}\n"
        f"Metadata   : {args.metadata}\n"
        f"Log file   : {args.log_file}"
    )
    print(summary, file=sys.stdout)


if __name__ == '__main__':
    main()
