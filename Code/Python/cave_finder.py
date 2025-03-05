import argparse
import mmap
import re
import math
import sys
import csv
import colorama
from colorama import Fore, Style

def print_progress(progress):
    sys.stdout.write(f"\rScanning: {progress:.2f}%")
    sys.stdout.flush()

def main():
    colorama.init(autoreset=True)
    parser = argparse.ArgumentParser(description="Scan a file for code caves (empty spaces).")
    parser.add_argument("file", help="Path to the file to scan.")
    parser.add_argument("min_size", type=int, help="Minimum size (in bytes) to consider as a code cave.")
    parser.add_argument("--pattern", default="00", help="Byte pattern in hex to search for (default: 00).")
    parser.add_argument("--export", help="Optional CSV file to export results.")
    args = parser.parse_args()
    
    try:
        with open(args.file, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except Exception as e:
        print(Fore.RED + "Error reading file: " + str(e))
        return

    total_size = len(mm)
    # Convert the provided hex pattern into bytes.
    try:
        pattern_bytes = bytes.fromhex(args.pattern)
    except Exception as e:
        print(Fore.RED + "Invalid hex pattern: " + str(e))
        return

    # Calculate how many times the pattern must repeat to meet or exceed the minimum size.
    occurrences = (args.min_size + len(pattern_bytes) - 1) // len(pattern_bytes)
    # Build the regex pattern: it matches a non-capturing group of the given pattern repeated at least 'occurrences' times.
    regex_pattern = b"(?:%s){%d,}" % (re.escape(pattern_bytes), occurrences)
    try:
        compiled_pattern = re.compile(regex_pattern)
    except Exception as e:
        print(Fore.RED + "Error compiling regex pattern: " + str(e))
        mm.close()
        return

    matches = []
    pos = 0
    last_progress = -1
    # Iteratively search for code caves and update progress based on the current match's starting position.
    while pos < total_size:
        match = compiled_pattern.search(mm, pos)
        if not match:
            break
        matches.append(match)
        pos = match.start() + 1  # Advance by one to search for further matches.
        progress = (match.start() / total_size) * 100
        if progress - last_progress >= 1:
            print_progress(progress)
            last_progress = progress

    # Ensure the progress reaches 100%
    print_progress(100)
    print()  # Newline after progress

    if matches:
        print(Fore.GREEN + f"Found {len(matches)} code cave(s) in the file.")
        for idx, match in enumerate(matches, 1):
            start = match.start()
            end = match.end() - 1
            size = match.end() - match.start()
            print(Fore.CYAN + f"Code Cave {idx}: Start Address: 0x{start:08X}, End Address: 0x{end:08X}, Size: {size} bytes")
    else:
        print(Fore.YELLOW + "No code caves found.")
    
    # Optional CSV export of results.
    if args.export:
        try:
            with open(args.export, "w", newline="") as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(["Index", "Start Address", "End Address", "Size"])
                for idx, match in enumerate(matches, 1):
                    start = match.start()
                    end = match.end() - 1
                    size = match.end() - match.start()
                    csv_writer.writerow([idx, f"0x{start:08X}", f"0x{end:08X}", size])
            print(Fore.GREEN + f"Results exported to {args.export}.")
        except Exception as e:
            print(Fore.RED + "Error exporting results: " + str(e))
    
    mm.close()

if __name__ == "__main__":
    main()
