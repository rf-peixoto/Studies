#!/usr/bin/env python3
"""
Utility to analyze and process text files by line length.

Features:
  --max               Report longest line length and its line number(s).
  --stats             Report count, min, max, mean, median of line lengths.
  --sort {asc,desc}   Sort lines by length (ascending or descending).
  --remove-longer N   Remove lines longer than N characters.
  --remove-shorter N  Remove lines shorter than N characters.
  --dedup             Remove duplicate lines (first occurrence kept).
  -o, --output FILE   Write resulting lines to FILE (defaults to stdout).

Usage examples:
  # Show max length and line number in file.txt
  python3 line_tool.py file.txt --max

  # Remove lines >64 chars, dedupe, sort desc, write to out.txt
  python3 line_tool.py file1.txt file2.txt \
    --remove-longer 64 --dedup --sort desc -o out.txt

  # Stats on stdin
  cat file.txt | python3 line_tool.py --stats
"""
import sys
import argparse
import statistics

def parse_args():
    parser = argparse.ArgumentParser(
        description="Process lines by length."
    )
    parser.add_argument(
        'files', nargs='*',
        help='Input file(s). Reads from stdin if none specified.'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file. Defaults to stdout.'
    )
    parser.add_argument(
        '--max', action='store_true',
        help='Show max line length and line number(s).'
    )
    parser.add_argument(
        '--stats', action='store_true',
        help='Show count, min, max, mean, median of line lengths.'
    )
    parser.add_argument(
        '--sort', choices=['asc', 'desc'],
        help='Sort lines by length (asc or desc).'
    )
    parser.add_argument(
        '--remove-longer', type=int, metavar='N',
        help='Remove lines longer than N characters.'
    )
    parser.add_argument(
        '--remove-shorter', type=int, metavar='N',
        help='Remove lines shorter than N characters.'
    )
    parser.add_argument(
        '--dedup', action='store_true',
        help='Remove duplicate lines, preserving first occurrence.'
    )
    return parser.parse_args()

def read_lines(files):
    if not files:
        return [line.rstrip('\n') for line in sys.stdin]
    all_lines = []
    for fname in files:
        with open(fname, 'r', encoding='utf-8') as f:
            all_lines.extend(line.rstrip('\n') for line in f)
    return all_lines

def write_lines(lines, output_path):
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            for l in lines:
                f.write(l + '\n')
    else:
        for l in lines:
            print(l)

def main():
    args = parse_args()
    lines = read_lines(args.files)

    # Removal filters
    if args.remove_longer is not None:
        lines = [l for l in lines if len(l) <= args.remove_longer]
    if args.remove_shorter is not None:
        lines = [l for l in lines if len(l) >= args.remove_shorter]

    # Deduplication
    if args.dedup:
        seen = set()
        uniq = []
        for l in lines:
            if l not in seen:
                seen.add(l)
                uniq.append(l)
        lines = uniq

    # Sorting
    if args.sort:
        reverse = (args.sort == 'desc')
        lines = sorted(lines, key=len, reverse=reverse)

    # Compute statistics on the resulting set of lines
    lengths = [len(l) for l in lines]
    if lengths:
        if args.max:
            max_len = max(lengths)
            line_nums = [i+1 for i, l in enumerate(lines) if len(l) == max_len]
            print(
                f"Max line length: {max_len}, "
                f"line number(s): {', '.join(map(str, line_nums))}",
                file=sys.stderr
            )
        if args.stats:
            min_len = min(lengths)
            mean_len = statistics.mean(lengths)
            median_len = statistics.median(lengths)
            print(
                f"Line count: {len(lengths)}; "
                f"min: {min_len}; max: {max_len}; "
                f"mean: {mean_len:.2f}; median: {median_len:.2f}",
                file=sys.stderr
            )
    else:
        if args.max or args.stats:
            print("No lines available for analysis.", file=sys.stderr)

    # Output processed lines
    write_lines(lines, args.output)

if __name__ == '__main__':
    main()
