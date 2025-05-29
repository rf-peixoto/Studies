#!/usr/bin/env python3

import argparse
import sys

# Hardcoded list of keywords to search for.
KEYWORDS = [
    "keyword",
    # Add or remove keywords as required.
]

def extract_lines(input_path, output_path, keywords, case_sensitive=False):
    """
    Read input_path line by line. If any keyword is found in a line,
    write that line to output_path. Matching may be case-insensitive.
    """
    total_lines = 0
    matched_lines = 0

    try:
        with open(input_path, 'r', encoding='utf-8') as infile, \
             open(output_path, 'w', encoding='utf-8') as outfile:
            for line in infile:
                total_lines += 1
                target = line if case_sensitive else line.lower()
                for kw in keywords:
                    key = kw if case_sensitive else kw.lower()
                    if key in target:
                        outfile.write(line)
                        matched_lines += 1
                        break
    except FileNotFoundError as e:
        sys.exit(f"Error: {e}")
    except IOError as e:
        sys.exit(f"I/O error: {e}")

    # Summary report
    print(f"Scanned {total_lines} lines; found {matched_lines} matching lines.")
    print(f"Output written to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract lines containing specified hardcoded keywords from a text file."
    )
    parser.add_argument(
        "input_file",
        help="Path to the source text file."
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default="extracted_lines.txt",
        help="Path to the destination file for extracted lines (default: extracted_lines.txt)."
    )
    parser.add_argument(
        "-c", "--case-sensitive",
        action="store_true",
        help="Enable case-sensitive keyword matching."
    )
    args = parser.parse_args()

    extract_lines(
        args.input_file,
        args.output_file,
        KEYWORDS,
        case_sensitive=args.case_sensitive
    )
