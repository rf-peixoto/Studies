#!/usr/bin/env python3
"""
bin_summary.py

Reads a file with one card number per line and produces:
- total lines (non-empty)
- unique card count
- unique BIN count (BIN = first 6 digits)
- counts of unique cards per BIN
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path


def normalize_line(line: str) -> str:
    # Keep only digits (tolerates spaces/dashes); strip newline, etc.
    digits = "".join(ch for ch in line.strip() if ch.isdigit())
    return digits


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize cards and BIN distribution.")
    parser.add_argument("file", type=Path, help="Input file (one card number per line).")
    parser.add_argument("--bin-len", type=int, default=6, help="BIN length (default: 6).")
    parser.add_argument(
        "--min-pan-len",
        type=int,
        default=12,
        help="Minimum digits to consider a line a PAN (default: 12).",
    )
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")

    raw_cards: list[str] = []
    invalid_lines = 0

    with args.file.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            pan = normalize_line(line)
            if not pan:
                continue  # skip empty/whitespace-only
            if len(pan) < args.min_pan_len:
                invalid_lines += 1
                continue
            raw_cards.append(pan)

    total_cards = len(raw_cards)
    unique_cards = set(raw_cards)
    unique_count = len(unique_cards)

    # BIN counting is done on UNIQUE cards (as requested: "removing duplicates")
    bin_counts = Counter()
    short_for_bin = 0
    for pan in unique_cards:
        if len(pan) < args.bin_len:
            short_for_bin += 1
            continue
        bin_counts[pan[: args.bin_len]] += 1

    print("=== Card File Summary ===")
    print(f"File: {args.file}")
    print(f"Total cards (non-empty, >= {args.min_pan_len} digits): {total_cards}")
    print(f"Unique cards (duplicates removed): {unique_count}")
    print(f"Duplicates removed: {total_cards - unique_count}")
    print(f"Invalid/too-short lines skipped: {invalid_lines}")
    if short_for_bin:
        print(f"Unique cards too short to extract BIN (len < {args.bin_len}): {short_for_bin}")

    print("\n=== BIN Summary (unique cards per BIN) ===")
    print(f"Unique BINs: {len(bin_counts)}")

    # Print in descending order of count, then BIN numeric
    for b, c in sorted(bin_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{b}\t{c}")


if __name__ == "__main__":
    main()
