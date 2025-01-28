#!/usr/bin/env python3

"""
Demonstration of file encryption/decryption using FrodoKEM with liboqs-python
(older API with KeyEncapsulation). Supports different FrodoKEM parameter sets,
such as FrodoKEM-640-AES and FrodoKEM-1344-AES.

Usage:
    python frodokem.py <input_file> [kem_name]

Examples:
    1) Default to FrodoKEM-640-AES:
       python frodokem.py myfile.txt

    2) Specify FrodoKEM-1344-AES:
       python frodokem.py myfile.txt FrodoKEM-1344-AES

This script:
    1) Encrypts <input_file> to <input_file>.enc using the specified (or default) KEM.
    2) Decrypts <input_file>.enc back to <input_file>.dec.
"""

import sys
import os
import oqs  # liboqs-python (older version with KeyEncapsulation)
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class FrodoFileEncryptor:
    """
    Encrypts and decrypts files using a specified FrodoKEM parameter set
    (e.g., FrodoKEM-640-AES or FrodoKEM-1344-AES) for key encapsulation.
    AES-256-CBC is used for symmetric file encryption.

    This is compatible with the older liboqs-python API, which requires:
      - KeyEncapsulation instead of KEM
      - Passing secret_key in the constructor when decapsulating
    """

    def __init__(self, kem_name: str = "FrodoKEM-640-AES"):
        self.kem_name = kem_name

    def generate_key_and_encrypt(self, input_file_path: str, output_file_path: str):
        """
        Generates a key pair for the chosen FrodoKEM variant, encapsulates
        a shared secret, and encrypts the file at 'input_file_path'.

        Returns (public_key, secret_key).
        """

        # 1. Create KeyEncapsulation object for the chosen KEM
        with oqs.KeyEncapsulation(self.kem_name) as frodo:
            public_key = frodo.generate_keypair()
            secret_key = frodo.export_secret_key()
            # Encapsulate shared secret
            kem_ciphertext, shared_secret_enc = frodo.encap_secret(public_key)

        # 2. Derive a 256-bit AES key from the KEM's shared secret
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM file encryption (older API)",
            backend=default_backend()
        ).derive(shared_secret_enc)

        # 3. Read file contents
        with open(input_file_path, "rb") as f_in:
            plaintext = f_in.read()

        # 4. Encrypt with AES-CBC
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # 5. PKCS#7 padding
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        aes_ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # 6. Write to output:
        #   [4 bytes KEM ciphertext length][KEM ciphertext][16-byte IV][AES ciphertext]
        with open(output_file_path, "wb") as f_out:
            f_out.write(len(kem_ciphertext).to_bytes(4, byteorder="big"))
            f_out.write(kem_ciphertext)
            f_out.write(iv)
            f_out.write(aes_ciphertext)

        return public_key, secret_key

    def decrypt_file(self, secret_key: bytes, input_file_path: str, output_file_path: str):
        """
        Decrypts the file using the KEM parameter set provided at initialization.
        Requires the secret_key from generate_key_and_encrypt().
        """

        # 1. Read encrypted data
        with open(input_file_path, "rb") as f_in:
            kem_cipher_len = int.from_bytes(f_in.read(4), byteorder="big")
            kem_ciphertext = f_in.read(kem_cipher_len)
            iv = f_in.read(16)
            aes_ciphertext = f_in.read()

        # 2. Decapsulate the shared secret
        #    (Older API: pass 'secret_key' to the constructor)
        with oqs.KeyEncapsulation(self.kem_name, secret_key=secret_key) as frodo_dec:
            shared_secret_dec = frodo_dec.decap_secret(kem_ciphertext)

        # 3. Derive the same AES-256 key
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM file encryption (older API)",
            backend=default_backend()
        ).derive(shared_secret_dec)

        # 4. Decrypt with AES-CBC
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(aes_ciphertext) + decryptor.finalize()

        # 5. Remove PKCS#7 padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

        # 6. Write the plaintext to file
        with open(output_file_path, "wb") as f_out:
            f_out.write(plaintext)


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        script_name = os.path.basename(sys.argv[0])
        print(f"Usage: {script_name} <input_file> [kem_name]")
        print("Example KEM names: FrodoKEM-640-AES, FrodoKEM-1344-AES, etc.")
        sys.exit(1)

    input_file = sys.argv[1]
    # Default to FrodoKEM-640-AES if no second argument is given
    kem_name = sys.argv[2] if len(sys.argv) == 3 else "FrodoKEM-640-AES"

    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' does not exist.")
        sys.exit(1)

    encryptor = FrodoFileEncryptor(kem_name=kem_name)

    encrypted_file = input_file + ".enc"
    decrypted_file = input_file + ".dec"

    # 1. Encrypt
    pub_key, sec_key = encryptor.generate_key_and_encrypt(
        input_file_path=input_file,
        output_file_path=encrypted_file
    )
    print(f"Encryption completed using {kem_name}: '{input_file}' -> '{encrypted_file}'")
    print(f"Public key length: {len(pub_key)} bytes")
    print(f"Secret key length: {len(sec_key)} bytes")

    # 2. Decrypt
    encryptor.decrypt_file(
        secret_key=sec_key,
        input_file_path=encrypted_file,
        output_file_path=decrypted_file
    )
    print(f"Decryption completed: '{encrypted_file}' -> '{decrypted_file}'")

    # Show version info if available (older API does not have __version__)
    oqs_python_version = getattr(oqs, "oqs_python_version", None)
    oqs_c_version = getattr(oqs, "oqs_version", None)
    if oqs_python_version:
        print(f"OQS Python binding version: {oqs_python_version()}")
    if oqs_c_version:
        print(f"liboqs C library version: {oqs_c_version()}")


if __name__ == "__main__":
    main()
