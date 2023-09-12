#!/usr/bin/env python3
import argparse
from bitstring import BitArray

def file_to_binary(filename):
    with open(filename, 'rb') as f:
        binary_data = f.read()
    return binary_data

def encode_data(data):
    encoded_data = ""
    for bit in data.bin:
        if bit == '0':
            encoded_data += "\u200B"  # Zero-width space
        else:
            encoded_data += "\u200C"  # Zero-width non-joiner
    return encoded_data

def decode_data(encoded_text):
    binary_data = ""
    for char in encoded_text:
        if char == "\u200B":
            binary_data += "0"
        elif char == "\u200C":
            binary_data += "1"
    return BitArray(bin=binary_data).bytes

def main():
    parser = argparse.ArgumentParser(description='Encode and decode files using zero-width characters.')
    parser.add_argument('action', choices=['encode', 'decode'], help='Choose whether to encode or decode a file.')
    parser.add_argument('input_file', help='Input file for encoding or decoding.')
    parser.add_argument('output_file', help='Output file for encoding or decoding.')

    args = parser.parse_args()

    if args.action == 'encode':
        binary_data = file_to_binary(args.input_file)
        encoded_text = encode_data(binary_data)
        with open(args.output_file, 'w') as f:
            f.write(encoded_text)
        print(f'File "{args.input_file}" encoded and saved as "{args.output_file}".')

    elif args.action == 'decode':
        with open(args.input_file, 'r') as f:
            encoded_text = f.read()
        decoded_data = decode_data(encoded_text)
        with open(args.output_file, 'wb') as f:
            f.write(decoded_data)
        print(f'File "{args.input_file}" decoded and saved as "{args.output_file}".')

if __name__ == '__main__':
    main()
