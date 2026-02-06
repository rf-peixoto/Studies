#!/usr/bin/env python3
import sys

def encode(text: str) -> str:
    b = text.encode("utf-8")
    out = []
    for byte in b:
        # 8 bits MSB->LSB
        for i in range(7, -1, -1):
            out.append("K" if (byte >> i) & 1 else "k")
    return "".join(out)

def decode(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if any(c not in "kK" for c in s):
        raise ValueError("Encoded text must contain only 'k' and 'K'.")
    if len(s) % 8 != 0:
        raise ValueError("Invalid length: must be a multiple of 8 (one byte = 8 chars).")

    data = bytearray()
    for i in range(0, len(s), 8):
        byte = 0
        chunk = s[i:i+8]
        for c in chunk:
            byte = (byte << 1) | (1 if c == "K" else 0)
        data.append(byte)

    return data.decode("utf-8")

def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: laugh.py -e TEXT | -d KSTRING")

    option = sys.argv[1].lower()
    data = sys.argv[2]

    if option == "-e":
        print(encode(data))
    elif option == "-d":
        print(decode(data))
    else:
        raise SystemExit("Option must be -e or -d")

if __name__ == "__main__":
    main()
