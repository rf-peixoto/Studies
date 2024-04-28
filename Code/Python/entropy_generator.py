import os
import numpy as np

def write_binary_file(filename, data):
    """Write binary data to a file."""
    with open(filename, "wb") as file:
        file.write(data)

def create_uniform_data(size):
    """Create binary data where all bytes are the same (low entropy)."""
    return bytes([0x55] * size)  # Byte 0x55 repeated

def create_random_data(size):
    """Create random binary data (high entropy)."""
    return os.urandom(size)

def create_mixed_data(size, block_size):
    """Create binary data with alternating blocks of uniform and random data."""
    data = bytearray()
    for _ in range(0, size, block_size * 2):
        data.extend([0x55] * block_size)  # Low entropy block
        data.extend(os.urandom(block_size))  # High entropy block
    return bytes(data)

# File sizes and block size
size = 1024 * 1024  # 1 MB
block_size = 256  # Block size for mixed entropy sections

# Create files
write_binary_file("low_entropy.bin", create_uniform_data(size))
write_binary_file("high_entropy.bin", create_random_data(size))
write_binary_file("mixed_entropy.bin", create_mixed_data(size, block_size))

print("Test files created: low_entropy.bin, high_entropy.bin, mixed_entropy.bin")
