import re, sys
from collections import Counter
import numpy as np

def read_file(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            if len(lines) < 200:
                raise ValueError("The file must contain at least 200 lines.")
            return [line.strip() for line in lines]
    except FileNotFoundError:
        print("File not found. Please check the path and try again.")
    except ValueError as ve:
        print(ve)

def detect_patterns(tokens):
    # Check for direct repeats
    repeats = [token for token, count in Counter(tokens).items() if count > 1]
    
    # Check for sequential patterns (e.g., numerical increments)
    sequences = []
    for i in range(len(tokens) - 1):
        if tokens[i].isdigit() and tokens[i+1].isdigit():
            if int(tokens[i+1]) == int(tokens[i]) + 1:
                sequences.append((tokens[i], tokens[i+1]))
    
    # Statistical Analysis (e.g., entropy)
    token_length = np.array([len(token) for token in tokens])
    entropy = -np.sum((np.unique(token_length, return_counts=True)[1] / len(token_length)) * np.log2(np.unique(token_length, return_counts=True)[1] / len(token_length)))

    return {
        "repeated_tokens": repeats,
        "sequential_tokens": sequences,
        "entropy": entropy
    }

def analyze_tokens(file_path):
    tokens = read_file(file_path)
    if tokens:
        patterns = detect_patterns(tokens)
        print("Analysis Results:")
        print(f"Repeated Tokens: {patterns['repeated_tokens']}")
        print(f"Sequential Tokens: {patterns['sequential_tokens']}")
        print(f"Entropy of Token Lengths: {patterns['entropy']}")

# Replace 'path_to_tokens_file.txt' with the actual path to your token file
analyze_tokens(sys.argv[1])
