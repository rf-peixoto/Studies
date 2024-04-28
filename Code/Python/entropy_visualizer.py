import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import entropy
from matplotlib import cm

def read_binary(file_path):
    with open(file_path, "rb") as file:
        return bytearray(file.read())

def plot_entropy(data, block_size=256, cmap_choice='viridis'):
    n_blocks = len(data) // block_size
    entropy_values = [entropy(np.histogram(data[i * block_size:(i + 1) * block_size], bins=256)[0]) for i in range(n_blocks)]
    
    # Create a meshgrid for the x and y coordinates
    x = np.arange(n_blocks) * block_size  # x-axis showing actual byte offsets of blocks
    y = np.arange(block_size)             # y-axis showing byte positions within each block
    X, Y = np.meshgrid(x, y)
    
    # Create Z values for the surface plot
    Z = np.zeros(X.shape)
    for i in range(n_blocks):
        Z[:, i] = entropy_values[i]

    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection='3d')
    cmap = getattr(cm, cmap_choice, cm.viridis)  # Use a color map based on the choice
    surf = ax.plot_surface(X, Y, Z, cmap=cmap, edgecolor='none')
    fig.colorbar(surf)
    ax.set_title('Entropy Visualization')
    ax.set_xlabel('Byte Offset of Block Start')
    ax.set_ylabel('Byte Position in Block')
    ax.set_zlabel('Entropy')
    plt.show()

# Usage
binary_data = read_binary(sys.argv[1])
plot_entropy(binary_data, cmap_choice='inferno')
