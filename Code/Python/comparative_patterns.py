import numpy as np
from opensimplex import OpenSimplex
import matplotlib.pyplot as plt
from PIL import Image

def string_to_seed(input_string):
    """Convert a string to a numeric seed."""
    return sum(ord(char) for char in input_string)

def generate_perlin_noise(width, height, seed):
    """Generate a width x height Perlin noise image from a seed."""
    tmp = OpenSimplex(seed)
    scale = 100.0  # Scale affects the 'zoom' of the noise pattern
    noise_img = np.zeros((height, width))
    
    for i in range(height):
        for j in range(width):
            value = tmp.noise2d(i / scale, j / scale)
            noise_img[i][j] = (value + 1) / 2  # Normalize value to [0, 1]
    return noise_img

def highlight_differences(img1, img2, threshold=0.1):
    """Highlight differences between two images with a given threshold."""
    height, width = img1.shape
    result_img = np.zeros((height, width, 3), dtype=np.uint8)
    
    for i in range(height):
        for j in range(width):
            if abs(img1[i][j] - img2[i][j]) > threshold:
                result_img[i][j] = [255, 0, 0]  # Red color for differences
            else:
                mean_val = int((img1[i][j] + img2[i][j]) / 2 * 255)
                result_img[i][j] = [mean_val, mean_val, mean_val]  # Grayscale for no difference
    
    return result_img

# Example usage:
seed1 = string_to_seed("hello")
seed2 = string_to_seed("world")

perlin1 = generate_perlin_noise(256, 256, seed1)
perlin2 = generate_perlin_noise(256, 256, seed2)

difference_img = highlight_differences(perlin1, perlin2)

# Plotting the images using matplotlib
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Display each image with axes
titles = ["Perlin Noise for 'hello'", "Perlin Noise for 'world'", "Differences Highlighted (Red)"]
cmaps = ['gray', 'gray', None]  # Using None for the third image to use RGB

for i, img in enumerate([perlin1, perlin2, difference_img]):
    ax = axes[i]
    if i < 2:
        cax = ax.imshow(img, cmap=cmaps[i], interpolation='nearest')
        fig.colorbar(cax, ax=ax, orientation='vertical')
    else:
        ax.imshow(img)
        ax.set_title(titles[i] + "\nRed areas show differences above threshold")
    
    ax.set_xticks(np.arange(-0.5, img.shape[1], 16), minor=True)
    ax.set_yticks(np.arange(-0.5, img.shape[0], 16), minor=True)
    ax.grid(which='minor', color='w', linestyle='-', linewidth=0.5)
    ax.tick_params(which='minor', size=0)
    ax.set_xlabel('X Coordinate')
    ax.set_ylabel('Y Coordinate')
    ax.set_title(titles[i])

plt.tight_layout()
plt.show()
