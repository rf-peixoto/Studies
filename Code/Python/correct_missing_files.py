#!/usr/bin/env python3
"""
Move files from folder B to folder A, but only those whose CONTENT
(SHA-256 hash) does not already exist anywhere in folder A.

Usage:
    python move_missing_files.py /path/to/A /path/to/B
    python move_missing_files.py /path/to/A /path/to/B --dry-run
    python move_missing_files.py /path/to/A /path/to/B --recursive

Notes:
- Comparison is by content only; file names don't matter.
- If several files in B share the same content (and it's missing from A),
  only the first one is moved; the duplicates stay in B.
- If a file with the same name already exists in A (but different content),
  the moved file is renamed: photo.jpg -> photo (1).jpg
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1 MB


def file_hash(path: Path) -> str:
    """Return the SHA-256 hash of a file, read in chunks (safe for big files)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def list_files(folder: Path, recursive: bool):
    pattern = "**/*" if recursive else "*"
    return [p for p in folder.glob(pattern) if p.is_file()]


def unique_destination(dest: Path) -> Path:
    """If dest exists, add ' (1)', ' (2)', ... before the extension."""
    if not dest.exists():
        return dest
    n = 1
    while True:
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def main():
    parser = argparse.ArgumentParser(
        description="Move files from B to A that are not already in A (by hash)."
    )
    parser.add_argument("folder_a", type=Path, help="Destination folder (A)")
    parser.add_argument("folder_b", type=Path, help="Source folder (B)")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Include subfolders (keeps B's subfolder structure inside A)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Only show what would be moved; don't move anything")
    args = parser.parse_args()

    a, b = args.folder_a.resolve(), args.folder_b.resolve()
    for folder in (a, b):
        if not folder.is_dir():
            sys.exit(f"Error: '{folder}' is not a folder.")
    if a == b:
        sys.exit("Error: A and B are the same folder.")

    # 1. Hash everything in A
    print(f"Hashing files in A: {a}")
    hashes_a = set()
    for p in list_files(a, args.recursive):
        try:
            hashes_a.add(file_hash(p))
        except OSError as e:
            print(f"  ! Could not read {p}: {e}")
    print(f"  {len(hashes_a)} unique files in A")

    # 2. Hash everything in B and pick the ones missing from A
    print(f"Hashing files in B: {b}")
    to_move = []
    for p in list_files(b, args.recursive):
        try:
            h = file_hash(p)
        except OSError as e:
            print(f"  ! Could not read {p}: {e}")
            continue
        if h not in hashes_a:
            to_move.append(p)
            hashes_a.add(h)  # so duplicates inside B are only moved once
    print(f"  {len(to_move)} files in B are not in A")

    # 3. Move them
    moved = 0
    for src in to_move:
        rel = src.relative_to(b)
        dest = unique_destination(a / rel)
        if args.dry_run:
            print(f"[dry-run] {src} -> {dest}")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            print(f"Moved: {src} -> {dest}")
            moved += 1
        except OSError as e:
            print(f"  ! Could not move {src}: {e}")

    if args.dry_run:
        print(f"\nDry run finished. {len(to_move)} files would be moved.")
    else:
        print(f"\nDone. {moved} of {len(to_move)} files moved to A.")


if __name__ == "__main__":
    main()
