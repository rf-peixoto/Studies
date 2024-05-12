import random, sys
from collections import defaultdict, Counter
from colorama import Fore, Style, init

def load_tokens(file_path):
    with open(file_path, 'r') as file:
        tokens = [line.strip() for line in file.readlines()]
    return tokens

def build_frequency_model(tokens):
    """Builds a frequency model based on bigrams for character-based tokens."""
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

def generate_predicted_token(model, tokens):
    """Generates a new token based on the frequency model or numeric sequence."""
    # Check for numeric sequence
    if all(token.isdigit() for token in tokens):
        numbers = sorted(int(token) for token in tokens)
        if numbers and all(numbers[i] + 1 == numbers[i + 1] for i in range(len(numbers) - 1)):
            return str(numbers[-1] + 1)
    
    # Fallback to character-based prediction if not purely sequential
    token = []
    current_char = '^'
    while True:
        next_char = predict_next_char(model, current_char)
        if next_char == '$':
            break
        if current_char != '^':
            token.append(next_char)
        current_char = next_char
    return ''.join(token)

# Initialize colorama
init()

# Load tokens
tokens = load_tokens(sys.argv[1])

# Build model and generate prediction
model = build_frequency_model(tokens)
predicted_token = generate_predicted_token(model, tokens)
print(Fore.BLUE + "Predicted Token: " + Fore.GREEN + predicted_token + Style.RESET_ALL)
