import argparse
import logging
import math
import os
import struct
import sys

from PIL import Image

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def generate_palette(scale: str) -> list[int]:
    """
    Generate a 256-color palette for the given color scale.
    Supported scales: 'grayscale', 'redscale', 'greenscale', 'bluescale',
    'yellowscale', 'purplescale', 'cyanscale'.
    """
    palette: list[int] = []
    for i in range(256):
        if scale == 'grayscale':
            r = g = b = i
        elif scale == 'redscale':
            r, g, b = i, 0, 0
        elif scale == 'greenscale':
            r, g, b = 0, i, 0
        elif scale == 'bluescale':
            r, g, b = 0, 0, i
        elif scale == 'yellowscale':
            r, g, b = i, i, 0
        elif scale == 'purplescale':
            r, g, b = i, 0, i
        elif scale == 'cyanscale':
            r, g, b = 0, i, i
        else:
            raise ValueError(f"Unsupported color scale: {scale}")
        palette.extend([r, g, b])
    return palette


def encode_to_image(data: bytes, scale: str) -> Image.Image:
    """
    Encode a byte sequence into a square palette-based PNG image,
    prefixing the data with a 4-byte big-endian length header.
    """
    # Prepend length header
    length = len(data)
    header = struct.pack(">I", length)
    full_data = header + data

    # Determine image dimensions
    num_pixels = len(full_data)
    size = math.ceil(math.sqrt(num_pixels))
    total_pixels = size * size

    # Pad with zero bytes
    padded = full_data + b'\x00' * (total_pixels - num_pixels)

    # Create image
    img = Image.new('P', (size, size))
    img.putpalette(generate_palette(scale))
    img.putdata(list(padded))
    return img


def decode_from_image(img_path: str) -> str:
    """
    Decode text from a palette-based PNG with a 4-byte length header.
    Returns the decoded UTF-8 string.
    """
    if not os.path.isfile(img_path):
        raise FileNotFoundError(f"No such file: {img_path}")

    img = Image.open(img_path)
    if img.mode != 'P':
        raise ValueError("Image mode must be 'P' (palette-indexed)")

    pixels = list(img.getdata())
    if len(pixels) < 4:
        raise ValueError("Image too small to contain length header")

    # Read length header
    header_bytes = bytes(pixels[:4])
    length = struct.unpack(">I", header_bytes)[0]
    if length < 0 or length > len(pixels) - 4:
        raise ValueError("Invalid length header or corrupted image")

    # Extract and decode data
    data_bytes = bytes(pixels[4:4 + length])
    try:
        return data_bytes.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ValueError(f"UTF-8 decode error: {e}")


def parse_args() -> argparse.Namespace:
    """
    Parse and validate command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Encode text to PNG or decode text from PNG."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-e', '--encode',
        action='store_true',
        help="Encode input text to an image."
    )
    group.add_argument(
        '-d', '--decode',
        action='store_true',
        help="Decode text from an image."
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help="Input file (text when encoding, PNG when decoding)."
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help="Output file (PNG when encoding, text when decoding)."
    )
    parser.add_argument(
        '-c', '--color',
        choices=[
            'grayscale', 'redscale', 'greenscale', 'bluescale',
            'yellowscale', 'purplescale', 'cyanscale'
        ],
        default='grayscale',
        help=(
            "Color scale to use when encoding. "
            "Options: grayscale, redscale, greenscale, bluescale, "
            "yellowscale, purplescale, cyanscale."
        )
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.encode:
            with open(args.input, 'r', encoding='utf-8') as f:
                text = f.read()
            data = text.encode('utf-8')
            img = encode_to_image(data, args.color)
            img.save(args.output, optimize=True)
            logging.info(f"Encoded {len(data)} bytes into image '{args.output}'.")
        else:
            decoded = decode_from_image(args.input)
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(decoded)
            logging.info(f"Decoded text written to '{args.output}'.")
    except Exception as e:
        logging.error(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
