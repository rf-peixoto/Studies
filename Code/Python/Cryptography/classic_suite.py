import os
import random
import string
from colorama import init, Fore, Style
from datetime import datetime

# Initialize Colorama for colorful CLI output
init(autoreset=True)

# Helper function to load text data from file or user input
def load_text(input_mode):
    if input_mode.lower() == 'f':
        filename = input(Fore.GREEN + "Enter the file path: " + Fore.RESET)
        if not os.path.exists(filename):
            print(Fore.RED + "File does not exist.")
            return None
        with open(filename, 'r') as file:
            return file.read()
    else:
        return input(Fore.GREEN + "Enter the text: " + Fore.RESET)

# Function to sanitize text by removing non-alphabetic characters
def sanitize_text(text):
    return ''.join(char for char in text if char.isalpha())

# Helper function to generate a random key where applicable
def generate_key(cipher_choice, text):
    if cipher_choice == "1":  # Caesar's Cipher
        return random.randint(1, 25)
    elif cipher_choice == "3":  # Rail Fence Cipher
        return random.randint(2, len(text) // 2)
    elif cipher_choice in ["4", "5", "6"]:  # Vigenère, One-Time Pad, Simple Substitution
        return ''.join(random.choice(string.ascii_lowercase) for _ in range(len(text)))

# Cipher functions
def caesar_cipher(text, key, decrypt=False):
    key = int(key)
    result = ""
    shift = -key if decrypt else key
    for char in text:
        if char.isalpha():
            start = ord('a') if char.islower() else ord('A')
            result += chr((ord(char) - start + shift) % 26 + start)
        else:
            result += char
    return result

def atbash_cipher(text, _=None, decrypt=False):
    result = ""
    for char in text:
        if char.isalpha():
            start = ord('a') if char.islower() else ord('A')
            result += chr((ord('z') + ord('a') - ord(char)) if char.islower() else (ord('Z') + ord('A') - ord(char)))
        else:
            result += char
    return result

def rail_fence_cipher(text, key, decrypt=False):
    key = int(key)
    if key <= 1:
        return text
    if decrypt:
        return decrypt_rail_fence(text, key)
    else:
        return encrypt_rail_fence(text, key)

def encrypt_rail_fence(text, key):
    rail = ['' for _ in range(key)]
    row, step = 0, 1
    for char in text:
        rail[row] += char
        if row == 0:
            step = 1
        elif row == key - 1:
            step = -1
        row += step
    return ''.join(rail)

def decrypt_rail_fence(text, key):
    rail_len = [0] * key
    idx = 0
    row, step = 0, 1
    for char in text:
        rail_len[row] += 1
        if row == 0:
            step = 1
        elif row == key - 1:
            step = -1
        row += step

    rails = ['' for _ in range(key)]
    pos = 0
    for i in range(key):
        rails[i] = text[pos:pos + rail_len[i]]
        pos += rail_len[i]

    result = []
    row, step = 0, 1
    for _ in text:
        result.append(rails[row][0])
        rails[row] = rails[row][1:]
        if row == 0:
            step = 1
        elif row == key - 1:
            step = -1
        row += step
    return ''.join(result)

def vigenere_cipher(text, key, decrypt=False):
    result = []
    key = key.lower()
    key_len = len(key)
    key_indices = [ord(i) - ord('a') for i in key]
    for i in range(len(text)):
        if text[i].isalpha():
            offset = ord('a') if text[i].islower() else ord('A')
            key_index = key_indices[i % key_len]
            if decrypt:
                new_char = chr((ord(text[i]) - offset - key_index) % 26 + offset)
            else:
                new_char = chr((ord(text[i]) - offset + key_index) % 26 + offset)
            result.append(new_char)
        else:
            result.append(text[i])
    return ''.join(result)

def one_time_pad(text, key, decrypt=False):
    return vigenere_cipher(text, key, decrypt)  # OTP is essentially a Vigenère with a unique random key

def simple_substitution_cipher(text, key, decrypt=False):
    alphabet = string.ascii_lowercase
    key = ''.join(sorted(set(key), key=key.index))  # Ensure key is deduplicated but preserves order
    key_mapping = dict(zip(alphabet, key)) if not decrypt else dict(zip(key, alphabet))
    result = []
    for char in text:
        if char.lower() in key_mapping:
            new_char = key_mapping[char.lower()]
            if char.isupper():
                new_char = new_char.upper()
            result.append(new_char)
        else:
            result.append(char)
    return ''.join(result)

# Main function
def main():
    print(Fore.MAGENTA + Style.BRIGHT + "[Welcome to the Classic Cipher Suite]")
    ciphers = {
        "1": ("Caesars Cipher", caesar_cipher),
        "2": ("Atbash Cipher", atbash_cipher),
        "3": ("Rail Fence Cipher", rail_fence_cipher),
        "4": ("Vigenere Cipher", vigenere_cipher),
        "5": ("One-Time Pad", one_time_pad),
        "6": ("Simple Substitution Cipher", simple_substitution_cipher)
    }

    for key, (name, _) in ciphers.items():
        print(f"{Fore.CYAN}{key}. {name}")
    cipher_choice = input(Fore.GREEN + "Choose a cipher (number): " + Fore.RESET)

    if cipher_choice not in ciphers:
        print(Fore.RED + "Invalid cipher choice.")
        return

    action = input(Fore.GREEN + "Do you want to " + Fore.RESET  + "[e]" + Fore.GREEN  + "ncrypt or " + Fore.RESET  + "[d]" + Fore.GREEN  +"ecrypt? " + Fore.RESET)
    if action.lower() not in ['e', 'd']:
        print(Fore.RED + "Invalid action choice.")
        return

    input_mode = input(Fore.GREEN + "Input from " + Fore.RESET + "[t]" + Fore.GREEN + "ext or " + Fore.RESET +"[f]" + Fore.GREEN + "ile? " + Fore.RESET)
    data = load_text(input_mode)
    if data is None:
        return

    # Sanitize data by removing spaces and special characters
    sanitized_data = sanitize_text(data)

    if action == 'e' and cipher_choice != "2":  # Atbash does not require a key
        key_choice = input(Fore.GREEN + "Generate a " + Fore.RESET + "[r]" + Fore.GREEN + "andom key or use your " + Fore.RESET + "[o]" + Fore.GREEN + "wn? " + Fore.RESET)
        if key_choice == 'r':
            key = generate_key(cipher_choice, sanitized_data)
            print(Fore.MAGENTA + "Generated key: " + Fore.RESET + f"{key}")
        else:
            key = input(Fore.GREEN + "Enter your key: " + Fore.RESET)
    elif action == 'd' and cipher_choice != "2":
        key = input(Fore.GREEN + "Enter the key used: " + Fore.RESET)
    else:
        key = None  # Atbash does not use a key

    _, cipher_func = ciphers[cipher_choice]
    result = cipher_func(sanitized_data, key, decrypt=(action == 'd'))

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    cipher_name = ciphers[cipher_choice][0].replace(' ', '_')
    output_file = f"result_{cipher_name}_{timestamp}.txt"
    with open(output_file, 'w') as file:
        file.write(result)

    print(Fore.GREEN + "Operation completed. Result saved to " + Fore.RESET + f"{output_file}")

if __name__ == "__main__":
    main()

