import json
import random
import argparse
import os
import hashlib
import codecs
from typing import List, Dict, Tuple
from collections import defaultdict

# Predefined known invalid sequences for various encodings
INVALID_PATTERNS = {
    "UTF-8": [
        [0xC0], [0xC0, 0xAF], [0xF8, 0x88, 0x80, 0x80, 0x80], [0xED, 0xA0, 0x80],
    ],
    "Shift_JIS": [
        [0x81], [0x82, 0x20],
    ],
    "GBK": [
        [0x81, 0x20], [0xFF, 0xFF],
    ],
    "Big5": [
        [0xF9, 0xFF], [0xA1],
    ],
    "Windows-1256": [
        [0x81], [0x9F],
    ],
    "Windows-1251": [
        [0xC0, 0xC0, 0xC0],
    ],
    "KOI8-R": [
        [0xFE, 0xFE],
    ],
    "ISO-8859-6": [
        [0xAD], [0x9F],
    ],
    "EUC-JP": [
        [0x8F], [0xA1, 0xFF],
    ],
    "ISO-2022-JP": [
        [0x1B, 0x28, 0x42, 0xFF],
    ]
}

ALL_ENCODINGS = list(INVALID_PATTERNS.keys())

COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "reset": "\033[0m"
}

def validate_encoding(byte_seq: bytes, encoding: str) -> bool:
    try:
        byte_seq.decode(encoding)
        return True
    except:
        return False

def hash_bytes(byte_seq: List[int]) -> str:
    return hashlib.sha256(bytes(byte_seq)).hexdigest()

def generate_patterns(count: int, must_be_valid: List[str], must_be_invalid: List[str], retry: int = 0, avoid_duplicates: bool = True) -> List[Dict]:
    seen_hashes = set()
    patterns = []
    while len(patterns) < count:
        selected_bytes = []
        encodings_hit = set()

        for enc, seqs in INVALID_PATTERNS.items():
            if must_be_valid and enc in must_be_valid:
                continue
            if must_be_invalid and enc not in must_be_invalid:
                continue
            selected_bytes += random.choice(seqs)

        unique_bytes = list(dict.fromkeys(selected_bytes))
        hashed = hash_bytes(unique_bytes)

        if avoid_duplicates and hashed in seen_hashes:
            continue

        validation = {enc: validate_encoding(bytes(unique_bytes), enc.lower().replace("-", "")) for enc in ALL_ENCODINGS}
        invalids = [enc for enc, valid in validation.items() if not valid]

        if retry > 0 and len(invalids) < retry:
            continue

        seen_hashes.add(hashed)
        patterns.append({
            "bytes": unique_bytes,
            "hex": " ".join(f"{b:02X}" for b in unique_bytes),
            "invalid_in": sorted(invalids),
            "invalid_count": len(invalids),
            "validation_results": validation
        })

    patterns.sort(key=lambda x: x["invalid_count"], reverse=True)
    return patterns

def save_binary_files(patterns: List[Dict], output_folder: str):
    os.makedirs(output_folder, exist_ok=True)
    for idx, entry in enumerate(patterns, 1):
        with open(os.path.join(output_folder, f"pattern_{idx}.bin"), "wb") as f:
            f.write(bytes(entry["bytes"]))

def main():
    parser = argparse.ArgumentParser(description="Generate byte patterns invalid in multiple encodings.")
    parser.add_argument("--count", type=int, default=5, help="Number of patterns to generate.")
    parser.add_argument("--valid-in", nargs="*", default=[], help="Encodings where pattern must be valid.")
    parser.add_argument("--invalid-in", nargs="*", default=[], help="Encodings where pattern must be invalid.")
    parser.add_argument("--output", type=str, default="patterns.json", help="Output JSON file.")
    parser.add_argument("--retry", type=int, default=0, help="Retry generation until a pattern breaks at least this many encodings.")
    parser.add_argument("--binary-dump", type=str, default=None, help="Folder to save patterns as raw binary files.")

    args = parser.parse_args()

    patterns = generate_patterns(args.count, args.valid_in, args.invalid_in, retry=args.retry)

    for idx, entry in enumerate(patterns, 1):
        print(f"Pattern {idx}: {COLORS['red']}{entry['hex']}{COLORS['reset']}")
        print(f"  Invalid in: {COLORS['green']}{', '.join(entry['invalid_in'])}{COLORS['reset']}")

    with open(args.output, "w") as f:
        json.dump(patterns, f, indent=2)
    print(f"\nSaved to {args.output}")

    if args.binary_dump:
        save_binary_files(patterns, args.binary_dump)
        print(f"Binary files saved to {args.binary_dump}")

if __name__ == "__main__":
    main()
