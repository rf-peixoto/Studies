#!/usr/bin/env python3
"""
batch_screenshot.py

Reads URLs from a text file and saves a true full-page screenshot of each,
using Chrome DevTools Protocol. Implements:

1. Explicit waits instead of fixed sleeps.
2. Retry logic with exponential back-off.
3. Structured logging.
4. HTTP HEAD validation before browser load.
6. Fully configurable parameters via CLI or environment.
7. Per-URL metadata capture (JSON).
8. Context-managed WebDriver.
9. Externalized dependencies and environment (USER_AGENT, proxy).
10. Summary report at the end.
"""

import os
import sys
import time
import json
import logging
import argparse
import base64
import requests

from datetime import datetime
from contextlib import contextmanager
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


def read_urls(path):
    """Read one URL/domain per line, skip blanks/comments, prepend http:// if missing."""
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
    """Filename = host + .png"""
    return f"{urlparse(url).netloc}.png"


def setup_driver(args):
    """Configure ChromeOptions (headless, UA, proxy, viewport) and return WebDriver."""
    opts = ChromeOptions()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--hide-scrollbars')
    opts.add_argument(f'--window-size={args.viewport_width},1080')

    # User-agent
    ua = args.user_agent or os.getenv('USER_AGENT')
    if ua:
        opts.add_argument(f'--user-agent={ua}')

    # Proxy (optional, via environment)
    proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
    if proxy:
        opts.add_argument(f'--proxy-server={proxy}')

    return webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=opts
    )


@contextmanager
def managed_driver(args):
    """Context manager to guarantee driver.quit()."""
    driver = setup_driver(args)
    try:
        yield driver
    finally:
        driver.quit()


def capture_fullpage_cdp(driver, args, url, out_path):
    """
    Load URL, wait for <body>, then use CDP to resize to full content and screenshot.
    Raises on failure.
    """
    driver.get(url)
    # explicit wait for DOM ready
    WebDriverWait(driver, args.wait_timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, 'body'))
    )

    # get content size
    metrics = driver.execute_cdp_cmd('Page.getLayoutMetrics', {})
    w = metrics['contentSize']['width']
    h = metrics['contentSize']['height']

    # override viewport
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'mobile': False,
        'width': w,
        'height': h,
        'deviceScaleFactor': 1,
        'screenOrientation': {'angle': 0, 'type': 'portraitPrimary'}
    })

    # screenshot
    data = driver.execute_cdp_cmd('Page.captureScreenshot', {
        'fromSurface': True,
        'captureBeyondViewport': True
    })['data']
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(data))


def main():
    parser = argparse.ArgumentParser(
        description="Batch full-page screenshots via Chrome CDP."
    )
    parser.add_argument('-i', '--input', default='domains.txt',
                        help="Text file with one URL/domain per line.")
    parser.add_argument('-o', '--output', default='screenshots',
                        help="Directory to save screenshots.")
    parser.add_argument('-m', '--metadata', default='metadata.json',
                        help="Path for output JSON metadata.")
    parser.add_argument('-p', '--pause', type=float, default=2.0,
                        help="Initial pause before capture (seconds).")
    parser.add_argument('-r', '--retries', type=int, default=3,
                        help="Retry attempts on failure.")
    parser.add_argument('-w', '--wait-timeout', type=int, default=15,
                        help="Seconds to wait for page DOM readiness.")
    parser.add_argument('-v', '--viewport-width', type=int, default=1920,
                        help="Browser viewport width in pixels.")
    parser.add_argument('-u', '--user-agent', default=None,
                        help="Override User-Agent string.")
    parser.add_argument('--log-file', default='batch_screenshot.log',
                        help="Path for the log file.")
    args = parser.parse_args()

    # ensure output dir exists
    os.makedirs(args.output, exist_ok=True)

    # configure logging
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
        logging.error("No URLs found in input.")
        sys.exit(1)

    metadata = []
    success = 0
    failure = 0

    with managed_driver(args) as driver:
        for url in urls:
            now = datetime.now().astimezone().isoformat()
            entry = {'url': url, 'timestamp': now, 'screenshot': None,
                     'status_code': None, 'title': None, 'error': None}

            # 1) HEAD check
            try:
                resp = requests.head(url, timeout=5)
                entry['status_code'] = resp.status_code
                if resp.status_code >= 400:
                    msg = f"HTTP {resp.status_code}, skipping"
                    logging.warning("%s: %s", url, msg)
                    entry['error'] = msg
                    metadata.append(entry)
                    failure += 1
                    continue
            except Exception as e:
                entry['error'] = f"HEAD failed: {e}"
                logging.error("HEAD %s failed: %s", url, e)
                metadata.append(entry)
                failure += 1
                continue

            # 2) Screenshot with retries
            out_file = os.path.join(args.output, domain_to_filename(url))
            for attempt in range(1, args.retries + 1):
                try:
                    time.sleep(args.pause)
                    capture_fullpage_cdp(driver, args, url, out_file)
                    entry.update({
                        'screenshot': out_file,
                        'title': driver.title
                    })
                    logging.info("Captured %s → %s", url, out_file)
                    success += 1
                    break
                except Exception as e:
                    backoff = 2 ** (attempt - 1)
                    logging.warning("%s attempt %d failed: %s; retrying in %ds",
                                    url, attempt, e, backoff)
                    time.sleep(backoff)
            else:
                entry['error'] = f"All {args.retries} attempts failed"
                logging.error("%s: %s", url, entry['error'])
                failure += 1

            metadata.append(entry)

    # write metadata JSON
    with open(args.metadata, 'w', encoding='utf-8') as mf:
        json.dump(metadata, mf, ensure_ascii=False, indent=2)

    # summary
    total = len(urls)
    summary = (
        f"Total URLs: {total}\n"
        f"Successes : {success}\n"
        f"Failures  : {failure}\n"
        f"Metadata  : {args.metadata}\n"
        f"Logs      : {args.log_file}"
    )
    print(summary, file=sys.stdout)


if __name__ == '__main__':
    main()
