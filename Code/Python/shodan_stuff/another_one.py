#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

def load_json_objects(path: Path):
    """
    Supports:
    - A JSON array
    - JSON Lines (one object per line)
    """
    with path.open("r", encoding="utf-8") as f:
        content = f.read().strip()

    # Try full JSON first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        else:
            raise ValueError("Unsupported JSON structure")
    except json.JSONDecodeError:
        # Fallback to JSON Lines
        objects = []
        for lineno, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {lineno}") from e
        return objects

def main():
    parser = argparse.ArgumentParser(description="Extract domains and IPs from JSON")
    parser.add_argument("input", nargs="?", default="parsed.json", help="Input JSON file")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    parser.add_argument("--domains-out", default="domains.txt")
    parser.add_argument("--ips-out", default="ips.txt")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    objects = load_json_objects(input_path)

    domains = set()
    ips = set()

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        domain = obj.get("domain")
        ip = obj.get("ip")

        if isinstance(domain, str) and domain:
            domains.add(domain)

        if isinstance(ip, str) and ip:
            ips.add(ip)

    (out_dir / args.domains_out).write_text(
        "\n".join(sorted(domains)) + ("\n" if domains else ""),
        encoding="utf-8"
    )

    (out_dir / args.ips_out).write_text(
        "\n".join(sorted(ips)) + ("\n" if ips else ""),
        encoding="utf-8"
    )

if __name__ == "__main__":
    main()
