import os
import random
import argparse

def sanitize_text(text):
    """Sanitize the input text by removing non-alphabetic characters and converting to uppercase."""
    return ''.join(filter(str.isalpha, text)).upper()

def generate_key(length):
    """Generate a random key of a given length using uppercase letters."""
    return ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(length))

def encrypt(plaintext, key):
    """Encrypt the plaintext using the one-time pad."""
    ciphertext = []
    for p, k in zip(plaintext, key):
        encrypted_char = (ord(p) + ord(k) - 2 * ord('A')) % 26 + ord('A')
        ciphertext.append(chr(encrypted_char))
    return ''.join(ciphertext)

def decrypt(ciphertext, key):
    """Decrypt the ciphertext using the one-time pad."""
    plaintext = []
    for c, k in zip(ciphertext, key):
        decrypted_char = (ord(c) - ord(k)) % 26 + ord('A')
        plaintext.append(chr(decrypted_char))
    return ''.join(plaintext)

def main():
    parser = argparse.ArgumentParser(description="Encrypt or Decrypt a file using the one-time pad cipher.")
    parser.add_argument("mode", choices=["encrypt", "decrypt"], help="Choose 'encrypt' or 'decrypt'")
    parser.add_argument("filename", help="The name of the file to process")
    args = parser.parse_args()
    
    with open(args.filename, 'r') as file:
        text = file.read()
    
    if args.mode == "encrypt":
        sanitized_text = sanitize_text(text)
        key = generate_key(len(sanitized_text))
        encrypted_text = encrypt(sanitized_text, key)
        print("Encrypted text:", encrypted_text)
        print("Encryption key (save this to decrypt):", key)
    elif args.mode == "decrypt":
        ciphertext = text.strip()
        key = input("Enter the decryption key: ")
        decrypted_text = decrypt(ciphertext, key)
        print("Decrypted text:", decrypted_text)

if __name__ == "__main__":
    main()
