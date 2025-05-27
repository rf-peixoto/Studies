import json
import random
import argparse
import os
import hashlib
import codecs
import logging
from typing import List, Dict, Tuple, Set
from collections import defaultdict

# Expanded invalid patterns with more comprehensive coverage
INVALID_PATTERNS = {
    "UTF-8": [
        # Overlong encodings
        [0xC0], [0xC0, 0xAF], [0xC1, 0xBF],
        # Invalid start bytes
        [0xF8, 0x88, 0x80, 0x80, 0x80], [0xFC, 0x84, 0x80, 0x80, 0x80, 0x80],
        # Surrogates
        [0xED, 0xA0, 0x80], [0xED, 0xBF, 0xBF],
        # Incomplete sequences
        [0xC2], [0xE0, 0x80], [0xF0, 0x80, 0x80],
        # Invalid continuation bytes
        [0x80], [0xBF], [0x80, 0x80],
        # Out of range
        [0xF4, 0x90, 0x80, 0x80], [0xF5, 0x80, 0x80, 0x80],
    ],
    "UTF-8-BOM": [
        [0xEF, 0xBB, 0xBF, 0xC0, 0xAF],  # BOM followed by overlong
        [0xEF, 0x00, 0xBB, 0xBF],        # Broken BOM sequence
        [0xEF, 0xBB, 0xBF, 0xED, 0xA0],  # BOM with surrogate
        [0xEF, 0xBB],                    # Partial BOM
    ],
    "IBM437": [
        [0x00, 0x01],                   # Control characters
        [0x1A, 0x1B],                    # SUB/ESC
        [0x7F, 0x80],                    # DEL + undefined
        [0xFE, 0xFF],                    # Undefined code points
        [0x81, 0x90],                    # Invalid combinations
    ],
    "Shift_JIS": [
        [0x81], [0x82, 0x20], [0xFD], [0xFE], [0xFF],
        [0x87, 0x40], [0xEB, 0xBF], [0xA0, 0xFD],
        # Invalid double-byte sequences
        [0x81, 0x00], [0x9F, 0xFF], [0xE0, 0x00],
    ],
    "GBK": [
        [0x81, 0x20], [0xFF, 0xFF], [0x80], [0xFE, 0xFE],
        # Invalid GB2312 extensions
        [0xA1, 0x00], [0xFE, 0x39], [0x81, 0x7F], [0xA0, 0xA0],
    ],
    "Big5": [
        [0xF9, 0xFF], [0xA1], [0x80], [0xFF],
        # Invalid high bytes
        [0x81, 0x00], [0xFE, 0x00], [0xC7, 0xFF],
        # Incomplete sequences
        [0xA4], [0xB0], [0xC0],
    ],
    "Windows-1256": [
        [0x81], [0x9F], [0x8D], [0x8E], [0x8F], [0x90],
        # Reserved/undefined code points
        [0x9D], [0x9E], [0x9F],
    ],
    "Windows-1251": [
        [0xC0, 0xC0, 0xC0], [0x98], [0x83], [0x88],
        # Undefined ranges
        [0x81], [0x83], [0x88], [0x90], [0x98],
    ],
    "KOI8-R": [
        [0xFE, 0xFE], [0xFF, 0xFF], [0x00, 0x7F, 0xFF],
        # Invalid Cyrillic patterns
        [0x9A, 0x9B], [0x9D, 0x9E],
    ],
    "ISO-8859-6": [
        [0xAD], [0x9F], [0xA1], [0xA2], [0xA3],
        # Invalid Arabic ranges
        [0xF0], [0xF1], [0xF2], [0xF8], [0xF9], [0xFA],
    ],
    "EUC-JP": [
        [0x8F], [0xA1, 0xFF], [0x8E, 0x20], [0xFF, 0xFF],
        # Invalid JIS X 0212 sequences
        [0x8F, 0xA1], [0x8F, 0xFE], [0xFE, 0xFE],
    ],
    "ISO-2022-JP": [
        [0x1B, 0x28, 0x42, 0xFF], [0x1B, 0x24, 0x42, 0x20],
        # Invalid escape sequences
        [0x1B, 0x28], [0x1B, 0x24], [0x1B, 0xFF],
        # Invalid JIS sequences
        [0x1B, 0x24, 0x40, 0x7F], [0x1B, 0x28, 0x4A, 0xFF],
    ],
    # Additional encodings for more coverage
    "CP932": [
        [0x81, 0x00], [0xFC, 0xFF], [0x80], [0xA0],
    ],
    "UTF-16": [
        [0xD8, 0x00], [0xDC, 0x00], [0xFF], [0xFE, 0xFF],
    ],
    "UTF-32": [
        [0x00, 0x11, 0x00, 0x00], [0xFF, 0xFF, 0xFF, 0xFF],
    ],
}

ALL_ENCODINGS = list(INVALID_PATTERNS.keys())

# Enhanced encoding name mappings
ENCODING_ALIASES = {
    "utf-8": ["utf8", "utf_8", "u8"],
    "utf-8-bom": ["utf8-bom", "utf_8_bom", "bom-utf8"],
    "ibm437": ["cp437", "dos-latin-us"],
    "shift_jis": ["shift-jis", "sjis", "s_jis", "cp932"],
    "gbk": ["gb2312", "gb18030"],
    "big5": ["big-5", "big_5"],
    "windows-1256": ["windows1256", "cp1256"],
    "windows-1251": ["windows1251", "cp1251"],
    "koi8-r": ["koi8_r", "koi8r"],
    "iso-8859-6": ["iso8859-6", "iso88596"],
    "euc-jp": ["euc_jp", "eucjp"],
    "iso-2022-jp": ["iso2022jp", "iso2022_jp"],
    "cp932": ["shift_jis", "sjis"],
    "utf-16": ["utf16", "utf_16", "u16"],
    "utf-32": ["utf32", "utf_32", "u32"],
}

COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "reset": "\033[0m"
}

def normalize_encoding_name(encoding: str) -> str:
    """Normalize encoding name to handle various formats."""
    normalized = encoding.lower().replace("-", "_").replace(" ", "")
    
    # Check aliases
    for canonical, aliases in ENCODING_ALIASES.items():
        if normalized in aliases or normalized == canonical.replace("-", "_"):
            return canonical
    
    return encoding

def validate_encoding(byte_seq: bytes, encoding: str) -> Tuple[bool, str]:
    """Handle special cases for new encodings."""
    normalized_enc = normalize_encoding_name(encoding)
    

            
    """Validate byte sequence against encoding with detailed error info."""
    try:
        normalized_enc = normalize_encoding_name(encoding)
        if normalized_enc == "utf-8-bom":
            try:
                # Special handling for BOM validation
                decoded = byte_seq.decode('utf-8-sig', errors='strict')
                return True, "valid"
            except UnicodeDecodeError as e:
                return False, f"decode_error:{e.reason}"
        decoded = byte_seq.decode(normalized_enc, errors='strict')
        return True, "valid"
    except UnicodeDecodeError as e:
        return False, f"decode_error:{e.reason}"
    except LookupError:
        return False, "unknown_encoding"
    except Exception as e:
        return False, f"other_error:{type(e).__name__}"

def hash_bytes(byte_seq: List[int]) -> str:
    """Generate SHA256 hash of byte sequence."""
    return hashlib.sha256(bytes(byte_seq)).hexdigest()  # Shorter hash for readability

def classify_pattern(byte_seq: List[int]) -> str:
    """Enhanced pattern classification with more categories."""
    # Check for specific byte patterns
    if any(b in (0xC0, 0xC1) for b in byte_seq):
        return "overlong-utf8"
    if any(b > 0xF4 for b in byte_seq):
        return "out-of-range"
    if 0x1B in byte_seq:
        return "escape-sequence"
    if any(b == 0xFF for b in byte_seq):
        return "high-bytes"
    if any(b == 0x00 for b in byte_seq):
        return "null-bytes"
    if all(0x80 <= b <= 0xBF for b in byte_seq):
        return "continuation-only"
    if any(0xD8 <= b <= 0xDF for b in byte_seq):
        return "surrogate-range"
    if len(set(byte_seq)) == 1:
        return "repeated-byte"
    if any(b < 0x20 and b not in (0x09, 0x0A, 0x0D) for b in byte_seq):
        return "control-chars"
    
    return "mixed-invalid"

def mutate_pattern(byte_seq: List[int], count: int = 2, mutation_types: List[str] = None) -> List[int]:
    """Enhanced mutation with different strategies."""
    if mutation_types is None:
        mutation_types = ["random", "bit_flip", "increment", "boundary"]
    
    seq = byte_seq[:]
    
    for _ in range(count):
        mutation_type = random.choice(mutation_types)
        idx = random.randint(0, len(seq) - 1)
        
        if mutation_type == "random":
            seq[idx] = random.randint(0x00, 0xFF)
        elif mutation_type == "bit_flip":
            bit_pos = random.randint(0, 7)
            seq[idx] ^= (1 << bit_pos)
        elif mutation_type == "increment":
            seq[idx] = (seq[idx] + random.randint(1, 10)) % 256
        elif mutation_type == "boundary":
            boundaries = [0x00, 0x7F, 0x80, 0xBF, 0xC0, 0xF4, 0xF5, 0xFF]
            seq[idx] = random.choice(boundaries)
    
    return seq

def generate_hybrid_patterns(base_patterns: List[List[int]], count: int) -> List[List[int]]:
    """Generate hybrid patterns by combining parts from different base patterns."""
    hybrids = []
    
    for _ in range(count):
        # Select 2-3 random base patterns
        selected = random.sample(base_patterns, min(len(base_patterns), random.randint(2, 3)))
        
        # Combine them
        hybrid = []
        for pattern in selected:
            # Take a random portion of each pattern
            start = random.randint(0, max(0, len(pattern) - 2))
            end = random.randint(start + 1, len(pattern))
            hybrid.extend(pattern[start:end])
        
        hybrids.append(hybrid)
    
    return hybrids

def generate_patterns(count: int, must_be_valid: List[str], must_be_invalid: List[str], 
                     retry: int = 0, avoid_duplicates: bool = True, enable_mutation: bool = False, 
                     target_size: int = 0, enable_hybrids: bool = False) -> List[Dict]:
    """Enhanced pattern generation with more options."""
    seen_hashes = set()
    patterns = []
    all_base_patterns = []
    
    # Collect all base patterns
    for enc, seqs in INVALID_PATTERNS.items():
        all_base_patterns.extend(seqs)
    
    generation_attempts = 0
    max_attempts = count * 50  # Prevent infinite loops
    
    while len(patterns) < count and generation_attempts < max_attempts:
        generation_attempts += 1
        selected_bytes = []
        
        if enable_hybrids and random.random() < 0.3:  # 30% chance for hybrid
            hybrid_patterns = generate_hybrid_patterns(all_base_patterns, 1)
            selected_bytes = hybrid_patterns[0]
        else:
            # Original logic for selecting from specific encodings
            valid_encodings = [enc for enc in INVALID_PATTERNS.keys() 
                             if (not must_be_valid or enc in must_be_valid) and
                                (not must_be_invalid or enc in must_be_invalid)]
            
            if valid_encodings:
                selected_enc = random.choice(valid_encodings)
                selected_bytes = random.choice(INVALID_PATTERNS[selected_enc])[:]
            else:
                # Fallback: select from any encoding
                enc = random.choice(list(INVALID_PATTERNS.keys()))
                selected_bytes = random.choice(INVALID_PATTERNS[enc])[:]

        if enable_mutation:
            mutation_count = random.randint(1, 3)
            selected_bytes = mutate_pattern(selected_bytes, mutation_count)

        if target_size > 0:
            if len(selected_bytes) < target_size:
                # Pad with random bytes
                padding_needed = target_size - len(selected_bytes)
                for _ in range(padding_needed):
                    selected_bytes.append(random.randint(0x00, 0xFF))
            elif len(selected_bytes) > target_size:
                # Truncate
                selected_bytes = selected_bytes[:target_size]

        # Remove duplicates while preserving order
        unique_bytes = []
        seen_bytes = set()
        for b in selected_bytes:
            if b not in seen_bytes:
                unique_bytes.append(b)
                seen_bytes.add(b)

        if not unique_bytes:  # Skip empty patterns
            continue

        hashed = hash_bytes(unique_bytes)
        if avoid_duplicates and hashed in seen_hashes:
            continue

        # Enhanced validation with error details
        validation = {}
        error_details = {}
        for enc in ALL_ENCODINGS:
            is_valid, error_info = validate_encoding(bytes(unique_bytes), enc)
            validation[enc] = is_valid
            if not is_valid:
                error_details[enc] = error_info

        invalids = [enc for enc, valid in validation.items() if not valid]

        if retry > 0 and len(invalids) < retry:
            continue

        seen_hashes.add(hashed)
        patterns.append({
            "bytes": unique_bytes,
            "hex": " ".join(f"{b:02X}" for b in unique_bytes),
            "shellcode": "".join(f"\\x{b:02x}" for b in unique_bytes),
            "invalid_in": sorted(invalids),
            "invalid_count": len(invalids),
            "validation_results": validation,
            "error_details": error_details,
            "signature": classify_pattern(unique_bytes),
            "hash": hashed,
            "size": len(unique_bytes)
        })

    # Sort by invalid count (descending) then by signature
    patterns.sort(key=lambda x: (-x["invalid_count"], x["signature"]))
    return patterns

def save_binary_files(patterns: List[Dict], output_folder: str):
    """Save patterns as binary files with enhanced naming."""
    os.makedirs(output_folder, exist_ok=True)
    for idx, entry in enumerate(patterns, 1):
        filename = f"pattern_{idx:03d}_{entry['signature']}_{entry['hash']}.bin"
        filepath = os.path.join(output_folder, filename)
        with open(filepath, "wb") as f:
            f.write(bytes(entry["bytes"]))

def print_detailed_results(patterns: List[Dict], verbose: bool = False):
    """Enhanced result printing with color coding."""
    for idx, entry in enumerate(patterns, 1):
        signature_color = COLORS["magenta"] if "utf8" in entry["signature"] else COLORS["cyan"]
        
        print(f"Pattern {idx}: {COLORS['red']}{entry['hex']}{COLORS['reset']} | "
              f"Signature: {signature_color}{entry['signature']}{COLORS['reset']} | "
              f"Hash: {COLORS['yellow']}{entry['hash']}{COLORS['reset']}")
        
        print(f"  Invalid in {entry['invalid_count']} encodings: "
              f"{COLORS['green']}{', '.join(entry['invalid_in'])}{COLORS['reset']}")
              
        print(f"  Shellcode: {COLORS['blue']}{entry['shellcode']}{COLORS['reset']}")
        
        if verbose and entry['error_details']:
            print(f"  Error details:")
            for enc, error in entry['error_details'].items():
                print(f"    {enc}: {COLORS['red']}{error}{COLORS['reset']}")
        
        print()

def main():
    parser = argparse.ArgumentParser(
        description="Generate byte patterns invalid in multiple encodings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --count 10 --mutate --hybrids
  %(prog)s --invalid-in UTF-8 GBK --retry 3 --size 8
  %(prog)s --count 5 --verbose --binary-dump ./patterns/
        """
    )
    parser.add_argument("--count", type=int, default=5, 
                       help="Number of patterns to generate (default: 5)")
    parser.add_argument("--valid-in", nargs="*", default=[], 
                       help="Encodings where pattern must be valid")
    parser.add_argument("--invalid-in", nargs="*", default=[], 
                       help="Encodings where pattern must be invalid")
    parser.add_argument("--output", type=str, default="patterns.json", 
                       help="Output JSON file (default: patterns.json)")
    parser.add_argument("--retry", type=int, default=0, 
                       help="Retry until pattern breaks at least N encodings")
    parser.add_argument("--binary-dump", type=str, default=None, 
                       help="Folder to save patterns as binary files")
    parser.add_argument("--mutate", action="store_true", 
                       help="Enable mutation of base patterns")
    parser.add_argument("--hybrids", action="store_true", 
                       help="Enable generation of hybrid patterns")
    parser.add_argument("--size", type=int, default=0, 
                       help="Target byte size (0 = variable size)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Show detailed error information")

    args = parser.parse_args()

    print(f"{COLORS['cyan']}Generating {args.count} encoding-breaking patterns...{COLORS['reset']}\n")

    patterns = generate_patterns(
        args.count, args.valid_in, args.invalid_in, 
        retry=args.retry, enable_mutation=args.mutate, 
        target_size=args.size, enable_hybrids=args.hybrids
    )

    if not patterns:
        print(f"{COLORS['red']}No patterns generated. Try relaxing constraints.{COLORS['reset']}")
        return

    print_detailed_results(patterns, args.verbose)

    # Save JSON output
    with open(args.output, "w") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)
    print(f"Saved to {COLORS['green']}{args.output}{COLORS['reset']}")

    # Save binary files if requested
    if args.binary_dump:
        save_binary_files(patterns, args.binary_dump)
        print(f"Binary files saved to {COLORS['green']}{args.binary_dump}{COLORS['reset']}")

    # Summary statistics
    total_invalids = sum(p["invalid_count"] for p in patterns)
    avg_invalids = total_invalids / len(patterns) if patterns else 0
    print(f"\n{COLORS['yellow']}Statistics:{COLORS['reset']}")
    print(f"  Total patterns: {len(patterns)}")
    print(f"  Average encodings broken per pattern: {avg_invalids:.1f}")
    print(f"  Most destructive pattern breaks {max(p['invalid_count'] for p in patterns)} encodings")

if __name__ == "__main__":
    main()
