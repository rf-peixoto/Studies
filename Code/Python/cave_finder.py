import argparse
import re
import colorama
from colorama import Fore, Style

def main():
    colorama.init(autoreset=True)
    parser = argparse.ArgumentParser(description="Scan a file for code caves (empty spaces).")
    parser.add_argument("file", help="Path to the file to scan.")
    parser.add_argument("min_size", type=int, help="Minimum size (in bytes) to consider as a code cave.")
    args = parser.parse_args()
    
    try:
        with open(args.file, "rb") as f:
            data = f.read()
    except Exception as e:
        print(Fore.RED + "Error reading file: " + str(e))
        return

    # Construct a regex pattern to match sequences of null bytes of at least min_size length.
    pattern = re.compile(b"\x00{" + str(args.min_size).encode() + b",}")
    matches = list(pattern.finditer(data))
    
    if matches:
        print(Fore.GREEN + f"Found {len(matches)} code cave(s) in the file.")
        for idx, match in enumerate(matches, 1):
            start = match.start()
            size = len(match.group())
            print(Fore.CYAN + f"Code Cave {idx}: Start Address: 0x{start:08X}, Size: {size} bytes")
    else:
        print(Fore.YELLOW + "No code caves found.")

if __name__ == "__main__":
    main()
