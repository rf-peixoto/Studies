#pip install pillow numpy

import argparse
from PIL import Image, ImageFilter
import numpy as np
import os

def generate_normal_map(texture_path, normal_map_path, strength=1.0, scale=1.0, blur_radius=1, side_by_side=False):
    # Load the texture image
    img = Image.open(texture_path).convert('RGB')
    
    # Convert image to grayscale for normal map generation
    img_gray = img.convert('L')
    
    # Apply Gaussian smoothing to reduce noise
    img_gray = img_gray.filter(ImageFilter.GaussianBlur(blur_radius))
    img_array = np.array(img_gray, dtype=np.float32)
    
    # Calculate gradients using Sobel operator
    sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    sobel_y = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32)
    
    dx = np.zeros_like(img_array)
    dy = np.zeros_like(img_array)
    
    height, width = img_array.shape
    for y in range(1, height-1):
        for x in range(1, width-1):
            dx[y, x] = np.sum(img_array[y-1:y+2, x-1:x+2] * sobel_x)
            dy[y, x] = np.sum(img_array[y-1:y+2, x-1:x+2] * sobel_y)
    
    # Adjust gradients with strength and scale
    dx *= strength / 255.0 * scale
    dy *= strength / 255.0 * scale
    
    # Create the normal map
    normal_map = np.zeros((height, width, 3), dtype=np.float32)
    normal_map[:, :, 0] = dx
    normal_map[:, :, 1] = dy
    normal_map[:, :, 2] = 1.0
    
    # Normalize the normal map
    norm = np.sqrt(np.sum(normal_map ** 2, axis=2))
    normal_map[:, :, 0] /= norm
    normal_map[:, :, 1] /= norm
    normal_map[:, :, 2] /= norm
    
    # Convert to RGB values
    normal_map = (normal_map * 0.5 + 0.5) * 255.0
    normal_map = normal_map.astype(np.uint8)
    
    # Save the normal map as a PNG image
    normal_img = Image.fromarray(normal_map)
    
    if side_by_side:
        # Create a new image that is double the width of the original
        combined_img = Image.new('RGB', (width * 2, height))
        combined_img.paste(img, (0, 0))
        combined_img.paste(normal_img, (width, 0))
        combined_img.save(normal_map_path)
    else:
        normal_img.save(normal_map_path)

def batch_process(input_dir, output_dir, strength, scale, blur_radius, side_by_side):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for filename in os.listdir(input_dir):
        if filename.endswith(".png") or filename.endswith(".jpg"):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, f"normal_{filename}")
            generate_normal_map(input_path, output_path, strength, scale, blur_radius, side_by_side)
            print(f"Processed {filename}")

def main():
    parser = argparse.ArgumentParser(description="Generate normal maps from texture images.")
    parser.add_argument("input", help="Input texture image or directory containing images")
    parser.add_argument("output", help="Output normal map image or directory for output images")
    parser.add_argument("--strength", type=float, default=1.0, help="Strength of the normal map")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale of the normal map")
    parser.add_argument("--blur", type=float, default=1.0, help="Gaussian blur radius")
    parser.add_argument("--batch", action='store_true', help="Batch process all images in the input directory")
    parser.add_argument("-s", "--side_by_side", action='store_true', help="Generate a single output with original texture and normal map side by side")
    
    args = parser.parse_args()

    if args.batch:
        batch_process(args.input, args.output, args.strength, args.scale, args.blur, args.side_by_side)
    else:
        generate_normal_map(args.input, args.output, args.strength, args.scale, args.blur, args.side_by_side)

if __name__ == "__main__":
    main()
