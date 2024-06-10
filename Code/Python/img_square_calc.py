from PIL import Image
import sys

def total_squares(width, height):
    total = 0
    details = []
    max_square_size = min(width, height)
    
    for k in range(2, max_square_size + 1):
        squares_in_width = width - k + 1
        squares_in_height = height - k + 1
        count = squares_in_width * squares_in_height
        details.append((k, count))
        total += count
    
    return total, details

def calculate_squares(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
        
        total, details = total_squares(width, height)
        print(f"Image Dimensions: {width} x {height}")
        print(f"Total Number of Squares: {total}\n")
        print("Details:")
        for size, count in details:
            print(f"  {size} x {size} squares: {count}")
        return total, details

# Example usage
image_path = sys.argv[1]
calculate_squares(image_path)
