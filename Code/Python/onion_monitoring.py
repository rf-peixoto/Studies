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
    print(f"[!] KEYWORD MATCH DETECTED")
    print(f"[+] Time: {now()}")
    print(f"[+] URL:  {url}")
    print(f"[+] Matches:")

    for match in matches:
        print(f"    - {match}")

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

    print(f"[+] Onion keyword monitor started")
    print(f"[+] Target: {args.url}")
    print(f"[+] Keywords loaded: {len(keywords)}")
    print(f"[+] Interval: {args.interval}s")
    print(f"[+] Started at: {now()}")

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
            print(f"[{now()}] Request error: {e}", file=sys.stderr)

        except Exception as e:
            print(f"[{now()}] Error: {e}", file=sys.stderr)

        if args.once:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()