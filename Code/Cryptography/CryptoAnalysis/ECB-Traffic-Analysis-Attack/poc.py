# python poc.py sample.bmp sample_enc.bmp

#!/usr/bin/env python3
import argparse
import os
from Crypto.Cipher import AES
import collections

# ANSI color codes for terminal output
COLOR_BLUE = "\033[94m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_MAGENTA = "\033[95m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"

def main():
    parser = argparse.ArgumentParser(
        description="Demonstration of ECB mode vulnerability via conceptual attack (traffic analysis) on a BMP image."
    )
    parser.add_argument("input_file", help="Path to input BMP file")
    parser.add_argument("output_file", nargs="?", default="encrypted.bmp", help="Path to output encrypted BMP file")
    args = parser.parse_args()

    print(f"{COLOR_BLUE}Step 1:{COLOR_RESET} Reading input file: {args.input_file}")
    with open(args.input_file, "rb") as f:
        data = f.read()

    # Assume BMP header is 54 bytes long
    header = data[:54]
    pixel_data = data[54:]
    print(f"{COLOR_BLUE}Step 2:{COLOR_RESET} Separated header (54 bytes) and pixel data ({len(pixel_data)} bytes).")

    # For proper block encryption, only full 16-byte blocks are processed.
    if len(pixel_data) % 16 != 0:
        full_length = (len(pixel_data) // 16) * 16
        to_encrypt = pixel_data[:full_length]
        remainder = pixel_data[full_length:]
        print(f"{COLOR_YELLOW}Note:{COLOR_RESET} Pixel data length is not a multiple of 16 bytes. Encrypting only full blocks ({full_length} bytes).")
    else:
        to_encrypt = pixel_data
        remainder = b""

    # Use a fixed 16-byte key
    key = b"0123456789abcdef"
    cipher = AES.new(key, AES.MODE_ECB)
    print(f"{COLOR_BLUE}Step 3:{COLOR_RESET} Encrypting pixel data using AES in ECB mode.")
    encrypted_pixel_data = cipher.encrypt(to_encrypt)

    # Analysis: Divide the ciphertext into 16-byte blocks and count frequency
    blocks = [encrypted_pixel_data[i:i+16] for i in range(0, len(encrypted_pixel_data), 16)]
    block_counts = collections.Counter(blocks)

    print(f"{COLOR_BLUE}Step 4:{COLOR_RESET} Analyzing ciphertext blocks.")
    repeated_blocks = {block: count for block, count in block_counts.items() if count > 1}

    color_codes = [COLOR_RED, COLOR_GREEN, COLOR_MAGENTA, COLOR_CYAN, COLOR_YELLOW]
    color_mapping = {}
    if repeated_blocks:
        print("Repeated blocks found:")
        color_index = 0
        for block, count in repeated_blocks.items():
            assigned_color = color_codes[color_index % len(color_codes)]
            color_mapping[block] = assigned_color
            print(f"  Block {assigned_color}{block.hex()}{COLOR_RESET} appears {count} times.")
            color_index += 1
    else:
        print("No repeated blocks found.")

    print(f"{COLOR_BLUE}Step 5:{COLOR_RESET} Visualizing ciphertext blocks (each block is 16 bytes in hex):")
    visualization = []
    for block in blocks:
        if block in color_mapping:
            visualization.append(f"{color_mapping[block]}{block.hex()}{COLOR_RESET}")
        else:
            visualization.append(block.hex())
    # Print blocks in lines of 8 blocks for clarity
    for i in range(0, len(visualization), 8):
        print(" ".join(visualization[i:i+8]))

    # Reconstruct the encrypted BMP: keep the header unchanged and append the encrypted pixel data and remainder.
    encrypted_data = header + encrypted_pixel_data + remainder
    with open(args.output_file, "wb") as f:
        f.write(encrypted_data)
    print(f"{COLOR_BLUE}Step 6:{COLOR_RESET} Encrypted BMP saved as: {args.output_file}")

if __name__ == "__main__":
    main()
