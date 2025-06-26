#!/usr/bin/env python3
"""
monitor_index.py

Monitors one or more "Index of" directory listing pages via HTTP and
prints to the terminal whenever a file is created, modified, or deleted.
"""

import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import colorama
from colorama import Fore, Style

# Initialize colorama (enables ANSI colors on Windows as well)
colorama.init()

def parse_index(url):
    """
    Fetches the given URL and returns a dict mapping
    filename -> (size_bytes, modified_timestamp).
    """
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    files = {}
    for link in soup.find_all("a"):
        name = link.get_text()
        href = link.get("href", "")
        # Skip parent directory links
        if href in ("../",) or name.lower() == "parent directory":
            continue

        parent_text = link.parent.get_text(separator=" ").strip()
        parts = parent_text.split()
        try:
            # Assume last token is size (e.g. "1.2K", "34M", or bytes)
            raw_size = parts[-1]
            multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3}
            if raw_size[-1] in multipliers:
                size_bytes = float(raw_size[:-1]) * multipliers[raw_size[-1]]
            else:
                size_bytes = float(raw_size)
            # Assume the two tokens before size are date and time
            date_str = parts[-3] + " " + parts[-2]
            modified = datetime.strptime(date_str, "%d-%b-%Y %H:%M")
        except Exception:
            size_bytes = None
            modified = None

        files[name] = (size_bytes, modified)
    return files

def monitor(urls, interval):
    """
    Loads the initial state for each URL, then enters a loop
    polling every `interval` seconds. Prints colored events
    when files are created, deleted, or modified.
    """
    prev_states = {url: parse_index(url) for url in urls}
    print(f"[{datetime.now()}] Initial state loaded for {len(urls)} URL(s).")

    while True:
        time.sleep(interval)
        for url in urls:
            try:
                current = parse_index(url)
            except Exception as e:
                print(f"[{datetime.now()}] ERROR accessing {url}: {e}")
                continue

            previous = prev_states[url]
            added    = set(current) - set(previous)
            removed  = set(previous) - set(current)
            modified = {
                name for name in set(current) & set(previous)
                if current[name] != previous[name]
            }

            for name in added:
                print(f"[{datetime.now()}] {Fore.GREEN}CREATED{Style.RESET_ALL}: {name} ({url})")
            for name in removed:
                print(f"[{datetime.now()}] {Fore.RED}DELETED{Style.RESET_ALL}: {name} ({url})")
            for name in modified:
                print(f"[{datetime.now()}] {Fore.YELLOW}MODIFIED{Style.RESET_ALL}: {name} ({url})")

            prev_states[url] = current

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Monitor 'Index of' listings for file changes"
    )
    parser.add_argument(
        "-u", "--url", action="append", required=True,
        help="URL of the directory listing to monitor (use multiple times for multiple URLs)"
    )
    parser.add_argument(
        "-i", "--interval", type=int, default=60,
        help="Polling interval in seconds (default: 60)"
    )
    args = parser.parse_args()
    monitor(args.url, args.interval)
