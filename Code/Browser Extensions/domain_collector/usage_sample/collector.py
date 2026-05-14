"""
Domain Collector
================
Polls the feed server every 5 minutes and processes new domains.
Uses the `since` parameter so each poll only fetches what's new.

Run:
  python collector.py
"""

import time
import requests
from datetime import datetime, timezone
from collections import Counter

FEED_URL = "http://localhost:5555/feed"
POLL_INTERVAL = 5 * 60  # seconds


def fetch_since(since_ts: str | None) -> tuple[list[dict], str]:
    """Fetch new entries from the feed. Returns (entries, latest_timestamp)."""
    url = FEED_URL if since_ts is None else f"{FEED_URL}?since={since_ts}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    entries = resp.json()
    latest = entries[-1]["ts"] if entries else since_ts
    return entries, latest


def process(entries: list[dict]):
    """Do whatever you want with the new batch of domains here."""
    if not entries:
        print("  (no new domains)")
        return

    counts = Counter(e["domain"] for e in entries)
    print(f"  {len(entries)} events | {len(counts)} unique domains")

    # Top 10 most seen this cycle
    for domain, n in counts.most_common(10):
        print(f"    {n:>4}x  {domain}")


def main():
    print("Domain Collector started — polling every 5 minutes.")
    print(f"Feed: {FEED_URL}\n")

    since = None

    # On first run, get the current timestamp so we only collect future data.
    since = datetime.now(timezone.utc).isoformat()

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] Polling feed...")

        try:
            entries, since = fetch_since(since)
            process(entries)
        except requests.ConnectionError:
            print("  Feed server not reachable. Is server.py running?")
        except Exception as e:
            print(f"  Error: {e}")

        print(f"  Next poll in {POLL_INTERVAL // 60} minutes.\n")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
