import sys
import os
from cryptography.hazmat.primitives.asymmetric import CRYSTALS_Kyber

class CRYSTALS_Kyber_Encryption:
    def __init__(self, key):
        self.key = key

    def encrypt_file(self, input_file, output_file):
        with open(input_file, 'rb') as file:
            plaintext = file.read()
        ciphertext = self.key.encrypt(plaintext)
        with open(output_file, 'wb') as file:
            file.write(ciphertext)

    def decrypt_file(self, input_file, output_file):
        with open(input_file, 'rb') as file:
            ciphertext = file.read()
        plaintext = self.key.decrypt(ciphertext)
        with open(output_file, 'wb') as file:
            file.write(plaintext)

def main():
    if len(sys.argv) != 5:
        print("Usage: python script.py <input_file> <output_file> <decrypted_file>")
        return

    input_file = sys.argv[1]
    output_file = 'output'
    decrypted_file = 'decrypted.txt'

    key = CRYSTALS_Kyber.generate_key()
    print("Generated Key:", key)

    encryptor = CRYSTALS_Kyber_Encryption(key)
    encryptor.encrypt_file(input_file, output_file)

    encryptor.decrypt_file(output_file, decrypted_file)

    os.remove(output_file)

if __name__ == "__main__":
    main()
