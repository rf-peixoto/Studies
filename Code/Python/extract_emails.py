#!/usr/bin/env python3
"""
email_extractor.py
Extract all email addresses from a text file.

Usage:
    python email_extractor.py input.txt
    python email_extractor.py input.txt -o emails.txt
"""

import re
import sys
import argparse
from pathlib import Path


EMAIL_REGEX = re.compile(
    r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'
)


def extract_emails(file_path: Path) -> list[str]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[ERROR] Could not read file: {e}")
        sys.exit(1)

    emails = EMAIL_REGEX.findall(content)

    # Remove duplicates while preserving order
    unique_emails = list(dict.fromkeys(email.lower() for email in emails))

    return unique_emails


def save_output(emails: list[str], output_file: Path):
    try:
        output_file.write_text("\n".join(emails), encoding="utf-8")
        print(f"[OK] Saved {len(emails)} unique emails to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Could not write output file: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Extract all email addresses from a text file"
    )
    parser.add_argument("input_file", help="Input text file")
    parser.add_argument(
        "-o",
        "--output",
        default="emails_extracted.txt",
        help="Output file (default: emails_extracted.txt)"
    )

    args = parser.parse_args()

    input_path = Path(args.input_file)

    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        sys.exit(1)

    emails = extract_emails(input_path)

    if not emails:
        print("[INFO] No email addresses found.")
        return

    print(f"[OK] Found {len(emails)} unique email(s)")
    save_output(emails, Path(args.output))


if __name__ == "__main__":
    main()