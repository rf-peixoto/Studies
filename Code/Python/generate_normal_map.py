#pip install pillow numpy

from PIL import Image
import numpy as np

def generate_normal_map(texture_path, normal_map_path, strength=1.0):
    # Load the texture image
    img = Image.open(texture_path).convert('L')
    img_array = np.array(img)

    # Calculate gradients
    dx, dy = np.gradient(img_array)
    dx = dx * strength / 255.0
    dy = dy * strength / 255.0

    # Create the normal map
    height, width = img_array.shape
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
    normal_img.save(normal_map_path)

# Example usage
texture_path = 'texture.png'
normal_map_path = 'normal_map.png'
generate_normal_map(texture_path, normal_map_path)
