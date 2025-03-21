#!/usr/bin/env python3
import random
import math
from tkinter import Tk, Canvas
import galois

def generate_random_prime_power():
    # Define a list of small primes for demonstration.
    primes = [2, 3, 5, 7, 11]
    p = random.choice(primes)
    # Choose an exponent between 1 and 3.
    n = random.randint(1, 3)
    q = p ** n
    return p, n, q

def main():
    # Generate a random prime power q = p^n.
    p, n, q = generate_random_prime_power()
    print(f"Selected GF({q}) with prime {p} and exponent {n}")
    
    # Create the finite field GF(q).
    GF = galois.GF(q)
    
    # Choose a random nonzero multiplier from GF.
    multiplier = GF(random.randint(1, q - 1))
    print(f"Selected multiplier: {int(multiplier)}")
    
    # Setup tkinter window and canvas.
    canvas_size = 600  # Canvas dimensions in pixels.
    margin = 50
    radius = (canvas_size - 2 * margin) / 2
    center = (canvas_size / 2, canvas_size / 2)
    
    root = Tk()
    root.title(f"GF({q}) Multiplication Circle with Factor {int(multiplier)}")
    canvas = Canvas(root, width=canvas_size, height=canvas_size, bg="white")
    canvas.pack()
    
    # Draw the outer circle.
    canvas.create_oval(center[0] - radius, center[1] - radius,
                       center[0] + radius, center[1] + radius,
                       outline="black")
    
    # Calculate positions of q equally spaced points on the circle.
    points = []
    for i in range(q):
        angle = 2 * math.pi * i / q
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append((x, y))
        # Mark each point with a small filled circle.
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="black")
    
    # Draw lines according to field multiplication.
    for i in range(q):
        # Multiply the field element corresponding to index i by the multiplier.
        j = int(multiplier * GF(i))
        start = points[i]
        end = points[j]
        canvas.create_line(start[0], start[1], end[0], end[1], fill="blue")
    
    root.mainloop()

if __name__ == "__main__":
    main()
