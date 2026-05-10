#!/usr/bin/env python3

import re
import json
import argparse
from collections import OrderedDict, defaultdict


# ============================================================
# CONFIG
# ============================================================

SKIP_PRIVATE = True
SKIP_IEEE_REGISTRATION_AUTHORITY = True

OUTPUT_INDENT = 4

# Prefer richer labels
PREFER_LONGER_LABELS = True

# ============================================================
# HELPERS
# ============================================================

def normalize_mac(mac: str) -> str:
    """
    Convert:
        286FB9
        28-6F-B9
        28:6F:B9
    into:
        28:6F:B9
    """

    mac = re.sub(r'[^0-9A-Fa-f]', '', mac.upper())

    if len(mac) != 6:
        return None

    return ":".join([
        mac[0:2],
        mac[2:4],
        mac[4:6]
    ])


def clean_vendor(vendor: str) -> str:
    """
    Clean IEEE vendor names.
    """

    vendor = vendor.strip()

    # Normalize whitespace
    vendor = re.sub(r'\s+', ' ', vendor)

    # Remove common garbage
    vendor = vendor.replace("\u00a0", " ")

    # Optional cleanup
    vendor = vendor.replace("Co.,Ltd", "Co., Ltd.")
    vendor = vendor.replace("TECHNOLOGIES CO.,LTD", "Technologies Co., Ltd.")
    vendor = vendor.replace("corporation", "Corporation")

    return vendor.strip()


def score_label(label: str) -> int:
    """
    Prefer more descriptive labels.
    """

    score = len(label)

    if "(" in label:
        score += 25

    if "/" in label:
        score += 10

    return score


# ============================================================
# MAIN PARSER
# ============================================================

def parse_oui_file(path):

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # IEEE format example:
    #
    # 28-6F-B9   (hex)        Nokia Shanghai Bell Co., Ltd.
    #
    pattern = re.compile(
        r'([0-9A-F]{2}-[0-9A-F]{2}-[0-9A-F]{2})\s+\(hex\)\s+(.+)',
        re.IGNORECASE
    )

    results = defaultdict(list)

    for match in pattern.finditer(content):

        raw_mac = match.group(1)
        vendor = clean_vendor(match.group(2))

        mac = normalize_mac(raw_mac)

        if not mac:
            continue

        vendor_lower = vendor.lower()

        # Skip junk entries
        if SKIP_PRIVATE and vendor_lower == "private":
            continue

        if (
            SKIP_IEEE_REGISTRATION_AUTHORITY and
            "ieee registration authority" in vendor_lower
        ):
            continue

        results[mac].append(vendor)

    # ========================================================
    # Resolve duplicates
    # ========================================================

    final = OrderedDict()

    for mac in sorted(results.keys()):

        labels = list(dict.fromkeys(results[mac]))

        if len(labels) == 1:
            final[mac] = labels[0]
            continue

        # Prefer best label
        best = max(labels, key=score_label)

        final[mac] = best

    return final


# ============================================================
# ENTRYPOINT
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Convert IEEE oui.txt into flat JSON OUI DB"
    )

    parser.add_argument(
        "input",
        help="Path to IEEE oui.txt"
    )

    parser.add_argument(
        "-o",
        "--output",
        default="oui_db.json",
        help="Output JSON file"
    )

    args = parser.parse_args()

    db = parse_oui_file(args.input)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(
            db,
            f,
            indent=OUTPUT_INDENT,
            ensure_ascii=False
        )

    print(f"[+] Parsed OUIs : {len(db)}")
    print(f"[+] Output file  : {args.output}")


if __name__ == "__main__":
    main()