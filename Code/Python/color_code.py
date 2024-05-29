# pip install pillow numpy

from PIL import Image
import numpy as np

def char_to_index(char):
    """Convert a character to a palette index."""
    return ord(char)

def index_to_char(index):
    """Convert a palette index to a character."""
    return chr(index)

def generate_image_from_string(input_string):
    """Generate an image from a given string."""
    max_chars = 256
    num_chars = min(len(input_string), max_chars)
    img_size = int(np.ceil(np.sqrt(num_chars)))

    image = Image.new('P', (img_size, img_size))
    palette = [i for i in range(256)] * 3  # Create a grayscale palette
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

if __name__ == '__main__':
    mode = input("Enter 'encode' to encode a string or 'decode' to decode an image: ").strip().lower()

    if mode == 'encode':
        input_string = input("Enter a string to encode: ").strip()
        generate_image_from_string(input_string)
    elif mode == 'decode':
        image_path = input("Enter the path to the image to decode: ").strip()
        decoded_string = decode_image_to_string(image_path)
        if decoded_string:
            print("Decoded string:", decoded_string)
    else:
        print("Invalid mode selected.")
