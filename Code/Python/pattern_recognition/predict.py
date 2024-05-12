import random, sys
from collections import defaultdict, Counter
from colorama import Fore, Style, init

def load_tokens(file_path):
    with open(file_path, 'r') as file:
        tokens = [line.strip() for line in file.readlines()]
    return tokens

def build_frequency_model(tokens):
    """Builds a frequency model based on bigrams."""
    model = defaultdict(Counter)
    for token in tokens:
        prev = '^'  # Start of token marker
        for char in token:
            model[prev][char] += 1
            prev = char
        model[prev]['$'] += 1  # End of token marker
    return model

def predict_next_char(model, current_char):
    """Predicts the next character based on the current character using weighted random choice."""
    if current_char in model and model[current_char]:
        choices, weights = zip(*model[current_char].items())
        return random.choices(choices, weights=weights)[0]
    return '$'  # End of token marker if no valid next character

def generate_predicted_token(model):
    """Generates a new token based on the frequency model."""
    token = []
    current_char = '^'
    while True:
        next_char = predict_next_char(model, current_char)
        if next_char == '$':  # Stop at end of token marker
            break
        if current_char != '^':  # Avoid adding the start marker to the token
            token.append(next_char)
        current_char = next_char
    return ''.join(token)

# Initialize colorama
init()

# Load tokens and build model
tokens = load_tokens(sys.argv[1])
model = build_frequency_model(tokens)

# Generate a predicted token
predicted_token = generate_predicted_token(model)
print(Fore.BLUE + "Predicted Token: " + Fore.GREEN + predicted_token + Style.RESET_ALL)
