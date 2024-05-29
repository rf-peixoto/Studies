# pip install pillow numpy

from PIL import Image
import numpy as np

def char_to_rgb(char):
    """Convert a character to an RGB color."""
    ascii_val = ord(char)
    return (ascii_val, ascii_val, ascii_val)

def rgb_to_char(rgb):
    """Convert an RGB color to a character."""
    return chr(rgb[0])

def generate_image_from_string(input_string):
    """Generate an image from a given string."""
    max_chars = 4096
    char_size = 8
    num_chars = min(len(input_string), max_chars)
    img_size = int(np.ceil(np.sqrt(num_chars)))

    image = Image.new('RGB', (img_size * char_size, img_size * char_size))
    pixels = image.load()

    for i, char in enumerate(input_string[:max_chars]):
        x = (i % img_size) * char_size
        y = (i // img_size) * char_size
        color = char_to_rgb(char)

        for dx in range(char_size):
            for dy in range(char_size):
                pixels[x + dx, y + dy] = color

    image.save('encoded_image.png')
    print("Image saved as 'encoded_image.png'")

def decode_image_to_string(image_path):
    """Decode an image to retrieve the string."""
    try:
        image = Image.open(image_path)
    except IOError:
        print("Error: Unable to open image file.")
        return None
    
    pixels = image.load()
    char_size = 8
    img_size = image.size[0] // char_size

    decoded_chars = []
    for y in range(img_size):
        for x in range(img_size):
            color = pixels[x * char_size, y * char_size]
            decoded_chars.append(rgb_to_char(color))

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
