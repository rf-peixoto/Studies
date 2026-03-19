#!/usr/bin/env python3
import argparse
import itertools
import os
import re
import sys
from pathlib import Path


TEXT_EXTENSIONS = {
    ".txt", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".md", ".sql",
    ".conf", ".ini", ".yaml", ".yml", ".tsv", ".psv"
}

IGNORED_PARTICLES = {
    "de", "da", "do", "das", "dos", "e"
}


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def load_names(names_file: Path) -> list[str]:
    names = []
    with names_file.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = normalize_spaces(line)
            if line:
                names.append(line)
    return names


def tokenize_name(full_name: str) -> list[str]:
    return normalize_spaces(full_name).split()


def strip_particles(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t.casefold() not in IGNORED_PARTICLES]


def generate_name_combinations(full_name: str, min_tokens: int = 2) -> list[str]:
    """
    Generate all combinations that:
    - preserve token order
    - always include the first non-particle token
    - ignore particles from the source name for combination generation

    Example:
      "A da B e C"
      normalized tokens => ["A", "B", "C"]

      combinations =>
        A B
        A C
        A B C
    """
    raw_tokens = tokenize_name(full_name)
    tokens = strip_particles(raw_tokens)

    if len(tokens) < min_tokens:
        return []

    first = tokens[0]
    rest = tokens[1:]
    combos = []

    for r in range(1, len(rest) + 1):
        for subset in itertools.combinations(rest, r):
            combo_tokens = [first, *subset]
            if len(combo_tokens) >= min_tokens:
                combos.append(" ".join(combo_tokens))

    return combos


def build_regex_for_combo(combo: str, ignore_case: bool = True) -> re.Pattern:
    """
    Build a regex that matches the combo while allowing ignored particles
    between the meaningful name tokens.

    Example combo:
      "A B C"

    Will match:
      "A B C"
      "A da B C"
      "A B e C"
      "A da B e C"
    """
    words = combo.split()
    if not words:
        raise ValueError("Empty combo cannot be compiled")

    particle_group = r"(?:de|da|do|das|dos|e)"
    separator = rf"(?:\s+{particle_group})*\s+"

    pattern = r"\b" + separator.join(re.escape(w) for w in words) + r"\b"
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(pattern, flags)


def looks_binary(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except Exception:
        return True


def should_scan_file(path: Path, all_files: bool) -> bool:
    if not path.is_file():
        return False

    if looks_binary(path):
        return False

    if all_files:
        return True

    return path.suffix.lower() in TEXT_EXTENSIONS or path.suffix == ""


def scan_file(path: Path, combo_map: dict[str, list[tuple[str, re.Pattern]]]) -> list[dict]:
    results = []

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, start=1):
                line_clean = line.rstrip("\n")

                for full_name, combo_entries in combo_map.items():
                    for combo, regex in combo_entries:
                        match = regex.search(line_clean)
                        if match:
                            results.append({
                                "file": str(path),
                                "line_number": lineno,
                                "full_name": full_name,
                                "matched_combo": combo,
                                "matched_text": match.group(0),
                                "line": line_clean,
                            })
    except Exception as e:
        print(f"[WARN] Failed to read {path}: {e}", file=sys.stderr)

    return results


def walk_files(root: Path):
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            yield Path(dirpath) / filename


def main():
    parser = argparse.ArgumentParser(
        description="Recursively grep files for all meaningful name combinations, ignoring particles."
    )
    parser.add_argument("names_file", help="Path to names.txt")
    parser.add_argument("target_folder", help="Folder to recursively scan")
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Scan all non-binary files, not just common text-like extensions",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use case-sensitive matching",
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=2,
        help="Minimum number of meaningful tokens in a generated combination (default: 2)",
    )
    parser.add_argument(
        "--tsv",
        action="store_true",
        help="Output as TSV instead of human-readable blocks",
    )
    args = parser.parse_args()

    names_file = Path(args.names_file)
    target_folder = Path(args.target_folder)

    if not names_file.is_file():
        print(f"[ERROR] Names file not found: {names_file}", file=sys.stderr)
        sys.exit(1)

    if not target_folder.is_dir():
        print(f"[ERROR] Target folder not found or not a directory: {target_folder}", file=sys.stderr)
        sys.exit(1)

    names = load_names(names_file)
    if not names:
        print("[ERROR] No names found in the names file.", file=sys.stderr)
        sys.exit(1)

    combo_map: dict[str, list[tuple[str, re.Pattern]]] = {}

    for full_name in names:
        combos = generate_name_combinations(full_name, min_tokens=args.min_tokens)
        compiled = [
            (combo, build_regex_for_combo(combo, ignore_case=not args.case_sensitive))
            for combo in combos
        ]
        if compiled:
            combo_map[full_name] = compiled

    total_hits = 0

    for path in walk_files(target_folder):
        if not should_scan_file(path, args.all_files):
            continue

        results = scan_file(path, combo_map)
        for r in results:
            total_hits += 1
            if args.tsv:
                print(
                    f"{r['file']}\t{r['line_number']}\t{r['full_name']}\t"
                    f"{r['matched_combo']}\t{r['matched_text']}\t{r['line']}"
                )
            else:
                print(f"FILE           : {r['file']}")
                print(f"LINE           : {r['line_number']}")
                print(f"FULL NAME      : {r['full_name']}")
                print(f"MATCHED COMBO  : {r['matched_combo']}")
                print(f"MATCHED TEXT   : {r['matched_text']}")
                print(f"CONTENT        : {r['line']}")
                print("-" * 100)

    if not args.tsv:
        print(f"\nTotal matches: {total_hits}")


if __name__ == "__main__":
    main()
