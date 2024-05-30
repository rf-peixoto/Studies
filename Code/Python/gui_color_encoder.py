import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import PhotoImage
from PIL import Image, ImageTk
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

def generate_image_from_string(input_string, palette_scale, max_chars):
    """Generate an image from a given string."""
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
    return image

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

    stats = f"Number of colors used: {len(colors)}\n"
    stats += f"File size: {file_size} bytes\n"
    stats += f"Image dimensions: {image.size}\n"

    messagebox.showinfo("Image Statistics", stats)

def encode_action():
    input_string = input_text.get("1.0", tk.END).strip()
    if not input_string:
        messagebox.showerror("Error", "Please enter a string to encode.")
        return
    palette_scale = palette_var.get()
    try:
        max_chars = int(max_chars_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid number for max characters.")
        return
    image = generate_image_from_string(input_string, palette_scale, max_chars)
    img_tk = ImageTk.PhotoImage(image)
    img_label.config(image=img_tk)
    img_label.image = img_tk
    messagebox.showinfo("Success", "String encoded and image saved as 'encoded_image.png'.")
    print_image_stats('encoded_image.png')

def decode_action():
    image_path = filedialog.askopenfilename(title="Select Image File", filetypes=[("PNG files", "*.png")])
    if not image_path:
        return
    decoded_string = decode_image_to_string(image_path)
    if decoded_string is not None:
        messagebox.showinfo("Decoded String", decoded_string)
    else:
        messagebox.showerror("Error", "Failed to decode the image.")

def import_image_action():
    image_path = filedialog.askopenfilename(title="Select Image File", filetypes=[("PNG files", "*.png")])
    if not image_path:
        return
    image = Image.open(image_path)
    img_tk = ImageTk.PhotoImage(image)
    img_label.config(image=img_tk)
    img_label.image = img_tk

# Set up the main application window
app = tk.Tk()
app.title("Image tEncoder")

# Input frame
input_frame = tk.Frame(app)
input_frame.pack(pady=10)

input_label = tk.Label(input_frame, text="Enter text to encode:")
input_label.pack(side=tk.LEFT)
input_text = tk.Text(input_frame, height=4, width=50)
input_text.pack(side=tk.LEFT)

# Palette selection
palette_frame = tk.Frame(app)
palette_frame.pack(pady=10)

palette_label = tk.Label(palette_frame, text="Select color scale:")
palette_label.pack(side=tk.LEFT)
palette_var = tk.StringVar(value="grayscale")
palette_options = ["grayscale", "redscale", "greenscale", "bluescale"]
palette_menu = tk.OptionMenu(palette_frame, palette_var, *palette_options)
palette_menu.pack(side=tk.LEFT)

# Max characters input
max_chars_frame = tk.Frame(app)
max_chars_frame.pack(pady=10)

max_chars_label = tk.Label(max_chars_frame, text="Max characters:")
max_chars_label.pack(side=tk.LEFT)
max_chars_entry = tk.Entry(max_chars_frame)
max_chars_entry.insert(0, "256")
max_chars_entry.pack(side=tk.LEFT)

# Buttons
button_frame = tk.Frame(app)
button_frame.pack(pady=20)

encode_button = tk.Button(button_frame, text="Encode", command=encode_action)
encode_button.pack(side=tk.LEFT, padx=10)

decode_button = tk.Button(button_frame, text="Decode", command=decode_action)
decode_button.pack(side=tk.LEFT, padx=10)

import_button = tk.Button(button_frame, text="Import Image", command=import_image_action)
import_button.pack(side=tk.LEFT, padx=10)

# Image display
img_label = tk.Label(app)
img_label.pack(pady=10)

# Run the application
app.mainloop()
