# pip install pillow numpy
import argparse
from PIL import Image
import numpy as np
import os

def char_to_index(char):
    """Convert a character to a palette index."""
    return ord(char)

def index_to_char(index):
    """Convert a palette index to a character."""
    return chr(index)

def generate_palette(scale):
    """Generate a palette based on the chosen color scale."""
    if scale == 'grayscale':
        return [i for i in range(256)] * 3
    elif scale == 'redscale':
        return [i if j == 0 else 0 for i in range(256) for j in range(3)]
    elif scale == 'greenscale':
        return [i if j == 1 else 0 for i in range(256) for j in range(3)]
    elif scale == 'bluescale':
        return [i if j == 2 else 0 for i in range(256) for j in range(3)]
    else:
        raise ValueError("Unsupported color scale. Choose from 'grayscale', 'redscale', 'greenscale', 'bluescale'.")

def generate_image_from_string(input_string, palette_scale):
    """Generate an image from a given string."""
    max_chars = 256
    num_chars = min(len(input_string), max_chars)
    img_size = int(np.ceil(np.sqrt(num_chars)))

    image = Image.new('P', (img_size, img_size))
    palette = generate_palette(palette_scale)
    image.putpalette(palette)
    pixels = image.load()

    for i, char in enumerate(input_string[:max_chars]):
        x = i % img_size
        y = i // img_size
        if x >= img_size or y >= img_size:
            break
        index = char_to_index(char)
        pixels[x, y] = index

    image.save('encoded_image.png', optimize=True)
    print("Image saved as 'encoded_image.png'")
    print_image_stats('encoded_image.png')

def decode_image_to_string(image_path):
    """Decode an image to retrieve the string."""
    try:
        image = Image.open(image_path)
    except IOError:
        print("Error: Unable to open image file.")
        return None
    
    pixels = image.load()
    img_size = image.size[0]

    decoded_chars = []
    for y in range(img_size):
        for x in range(img_size):
            index = pixels[x, y]
            decoded_chars.append(index_to_char(index))

    decoded_string = ''.join(decoded_chars).rstrip('\x00')
    return decoded_string

def print_image_stats(image_path):
    """Print statistics about the image."""
    image = Image.open(image_path)
    colors = image.getcolors()
    file_size = os.path.getsize(image_path)

    print(f"Number of colors used: {len(colors)}")
    print(f"File size: {file_size} bytes")
    print(f"Image dimensions: {image.size}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Encode or decode a string to/from an image.")
    parser.add_argument('-e', '--encode', help="Encode a string to an image.", action='store_true')
    parser.add_argument('-d', '--decode', help="Decode an image to a string.", action='store_true')
    parser.add_argument('-s', '--string', help="The string to encode.")
    parser.add_argument('-p', '--path', help="The path to the image file.")
    parser.add_argument('-c', '--color', help="The color scale for encoding. Options: 'grayscale', 'redscale', 'greenscale', 'bluescale'.", default='grayscale')

    args = parser.parse_args()

    if args.encode:
        if not args.string:
            print("Please provide a string to encode using -s or --string.")
        else:
            generate_image_from_string(args.string, args.color)
    elif args.decode:
        if not args.path:
            print("Please provide the path to the image to decode using -p or --path.")
        else:
            decoded_string = decode_image_to_string(args.path)
            if decoded_string:
                print("Decoded string:", decoded_string)
    else:
        print("Please provide either -e/--encode to encode or -d/--decode to decode.")
