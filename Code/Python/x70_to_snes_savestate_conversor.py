#!/usr/bin/env python3

import argparse
import hashlib
import sys
from pathlib import Path


SNES9X_MAGIC = b"#!s9xsnp:"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_snapshots(data: bytes) -> list[int]:
    """
    Return offsets of all embedded Snes9x snapshots.

    Example signatures:
        #!s9xsnp:0008
        #!s9xsnp:0010
        etc.
    """
    offsets = []
    pos = 0

    while True:
        offset = data.find(SNES9X_MAGIC, pos)

        if offset == -1:
            break

        offsets.append(offset)
        pos = offset + len(SNES9X_MAGIC)

    return offsets


def validate_snapshot(data: bytes, offset: int) -> bool:
    """
    Perform a basic validation of the Snes9x snapshot header.

    Expected form:
        #!s9xsnp:NNNN
    """
    minimum_length = len(SNES9X_MAGIC) + 4

    if len(data) - offset < minimum_length:
        return False

    version = data[
        offset + len(SNES9X_MAGIC):
        offset + len(SNES9X_MAGIC) + 4
    ]

    return version.isdigit()


def snapshot_version(data: bytes, offset: int) -> str:
    start = offset + len(SNES9X_MAGIC)
    return data[start:start + 4].decode("ascii", errors="replace")


def convert_file(
    source: Path,
    output_dir: Path | None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> int:

    try:
        data = source.read_bytes()
    except OSError as exc:
        print(f"[ERROR] Cannot read {source}: {exc}")
        return 0

    offsets = find_snapshots(data)

    offsets = [
        offset
        for offset in offsets
        if validate_snapshot(data, offset)
    ]

    if not offsets:
        print(f"[SKIP]  {source}: no Snes9x snapshot found")
        return 0

    destination = output_dir if output_dir else source.parent
    destination.mkdir(parents=True, exist_ok=True)

    basename = source.stem

    print()
    print(f"[FILE]  {source}")
    print(f"        Size:      {len(data):,} bytes")
    print(f"        Wrapper:   {offsets[0]:,} bytes")
    print(f"        Snapshots: {len(offsets)}")

    converted = 0

    for index, start in enumerate(offsets):
        if index + 1 < len(offsets):
            end = offsets[index + 1]
        else:
            end = len(data)

        snapshot = data[start:end]

        version = snapshot_version(data, start)

        output_name = f"{basename}.{index:03d}"
        output_path = destination / output_name

        print()
        print(f"        [{index:03d}]")
        print(f"        Version:   {version}")
        print(f"        Offset:    0x{start:X} ({start:,})")
        print(f"        Length:    {len(snapshot):,} bytes")
        print(f"        SHA-256:   {sha256(snapshot)}")
        print(f"        Output:    {output_path}")

        if output_path.exists() and not overwrite:
            print("        Status:    EXISTS - skipped")
            continue

        if dry_run:
            print("        Status:    DRY RUN")
            converted += 1
            continue

        try:
            output_path.write_bytes(snapshot)
        except OSError as exc:
            print(f"        Status:    ERROR - {exc}")
            continue

        print("        Status:    OK")
        converted += 1

    return converted


def collect_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]

    if not path.is_dir():
        return []

    if recursive:
        return sorted(
            p for p in path.rglob("*")
            if p.is_file() and p.suffix.lower() == ".prg"
        )

    return sorted(
        p for p in path.iterdir()
        if p.is_file() and p.suffix.lower() == ".prg"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract embedded Snes9x save-state snapshots from "
            ".prg handheld emulator save containers."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input .prg file or directory containing .prg files",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory. Default: same directory as source file",
    )

    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively search directories for .prg files",
    )

    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="Overwrite existing .000/.001/etc files",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze files without writing output",
    )

    args = parser.parse_args()

    source = args.input.expanduser().resolve()

    files = collect_files(source, args.recursive)

    if not files:
        print("[ERROR] No input files found.", file=sys.stderr)
        sys.exit(1)

    print("Snes9x PRG Save Converter")
    print("=========================")
    print(f"Input: {source}")
    print(f"Files: {len(files)}")

    total = 0

    for file in files:
        total += convert_file(
            source=file,
            output_dir=args.output,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )

    print()
    print("=========================")

    if args.dry_run:
        print(f"Snapshots detected: {total}")
    else:
        print(f"Snapshots written: {total}")


if __name__ == "__main__":
    main()