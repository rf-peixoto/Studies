import re, sys
from collections import Counter
import numpy as np
from colorama import Fore, Style, init

def read_file(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            if len(lines) < 200:
                raise ValueError("The file must contain at least 200 lines.")
            return [line.strip() for line in lines]
    except FileNotFoundError:
        print(Fore.RED + "File not found. Please check the path and try again." + Style.RESET_ALL)
    except ValueError as ve:
        print(Fore.RED + str(ve) + Style.RESET_ALL)

def shannon_entropy(data):
    if not data:
        return 0
    probabilities = [n_x / len(data) for x, n_x in Counter(data).items()]
    entropy = -sum(p * np.log2(p) for p in probabilities if p > 0)
    return entropy

def detect_patterns(tokens):
    repeats = [token for token, count in Counter(tokens).items() if count > 1]
    sequences = []
    for i in range(len(tokens) - 1):
        if tokens[i].isdigit() and tokens[i+1].isdigit():
            if int(tokens[i+1]) == int(tokens[i]) + 1:
                sequences.append((tokens[i], tokens[i+1]))
    token_length = np.array([len(token) for token in tokens])
    length_entropy = -np.sum((np.unique(token_length, return_counts=True)[1] / len(token_length)) * np.log2(np.unique(token_length, return_counts=True)[1] / len(token_length)))
    all_characters = ''.join(tokens)
    char_entropy = shannon_entropy(all_characters)
    return repeats, sequences, length_entropy, char_entropy

def draw_graph(label, value, max_value=10, entropy=True):
    width = 50  # width of the graph bar
    scaled_value = int((value / max_value) * width)
    if entropy:
        color = Fore.GREEN if value > 7 else (Fore.YELLOW if value > 4 else Fore.RED)
    else:
        color = Fore.GREEN if value < 20 else (Fore.YELLOW if value < 50 else Fore.RED)
    return f"{label}" + color + "█" * scaled_value + Style.RESET_ALL + f"({value:.2f})"

def analyze_tokens(file_path):
    tokens = read_file(file_path)
    if tokens:
        repeats, sequences, length_entropy, char_entropy = detect_patterns(tokens)
        repeat_percentage = (len(repeats) / len(tokens)) * 100
        print(Fore.CYAN + "Analysis Results:" + Style.RESET_ALL)
        print("Repeated Tokens:\t\t" + (Fore.YELLOW + f"{len(repeats)} ({repeat_percentage:.2f}%)" + Style.RESET_ALL if repeats else "None"))
        print("Sequential Tokens:\t\t" + (Fore.YELLOW + str(sequences) + Style.RESET_ALL if sequences else "None"))
        print(draw_graph("Entropy of Token Lengths\t", length_entropy))
        print(draw_graph("Shannon Entropy of Characters\t", char_entropy, max_value=8))
        print(draw_graph("Repeated Tokens Percentage\t", repeat_percentage, max_value=100, entropy=False))

init()
# Replace 'path_to_tokens_file.txt' with the actual path to your token file
analyze_tokens(sys.argv[1])
