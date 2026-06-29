#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


STATE_FILE = "onion_monitor_state.json"

# ANSI color codes
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BOLD = "\033[1m"

def color(text, code):
    """Wrap text with ANSI color code and reset."""
    return f"{code}{text}{COLOR_RESET}"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_keywords(path):
    with open(path, "r", encoding="utf-8") as f:
        keywords = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not keywords:
        raise ValueError("Keyword file is empty.")

    return keywords


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "seen_matches": [],
            "last_page_hash": None
        }

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_page(url, timeout):
    headers = {
        "User-Agent": "Mozilla/5.0 onion-keyword-monitor/1.0"
    }

    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def find_matches(text, keywords):
    matches = []
    lowered_text = text.lower()

    for keyword in keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in lowered_text:
            matches.append(keyword)

    return matches


def alert(url, matches):
    print("\n" + "=" * 80)
    print(color("[!] KEYWORD MATCH DETECTED", COLOR_BOLD + COLOR_RED))
    print(color(f"[+] Time: {now()}", COLOR_GREEN))
    print(color(f"[+] URL:  {url}", COLOR_GREEN))
    print("[+] Matches:")
    for match in matches:
        print(color(f"    - {match}", COLOR_YELLOW))
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor an onion page for keyword appearances."
    )

    parser.add_argument(
        "--url",
        required=True,
        help="Target onion URL, for example: http://example.onion/"
    )

    parser.add_argument(
        "--keywords",
        required=True,
        help="Path to keyword list file."
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between checks. Default: 300"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Request timeout in seconds. Default: 60"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run only one check and exit."
    )

    args = parser.parse_args()

    keywords = load_keywords(args.keywords)
    state = load_state()

    print(color("[+] Onion keyword monitor started", COLOR_GREEN))
    print(color(f"[+] Target: {args.url}", COLOR_GREEN))
    print(color(f"[+] Keywords loaded: {len(keywords)}", COLOR_GREEN))
    print(color(f"[+] Interval: {args.interval}s", COLOR_GREEN))
    print(color(f"[+] Started at: {now()}", COLOR_GREEN))

    while True:
        try:
            html = fetch_page(args.url, args.timeout)
            text = html_to_text(html)

            page_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

            matches = find_matches(text, keywords)
            new_matches = []

            for match in matches:
                match_id = hashlib.sha256(
                    f"{args.url}|{match}".encode("utf-8")
                ).hexdigest()

                if match_id not in state["seen_matches"]:
                    new_matches.append(match)
                    state["seen_matches"].append(match_id)

            if new_matches:
                alert(args.url, new_matches)
            else:
                if page_hash != state.get("last_page_hash"):
                    print(f"[{now()}] Page changed, but no new keyword match.")
                else:
                    print(f"[{now()}] No change, no match.")

            state["last_page_hash"] = page_hash
            save_state(state)

        except requests.exceptions.RequestException as e:
            print(color(f"[{now()}] Request error: {e}", COLOR_RED), file=sys.stderr)

        except Exception as e:
            print(color(f"[{now()}] Error: {e}", COLOR_RED), file=sys.stderr)

        if args.once:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
