"""
Demonstration of file encryption and decryption using FrodoKEM-640-AES with
an older version of liboqs-python that uses KeyEncapsulation instead of KEM.

Command-line usage:
    python frodokem.py <input_file>

This will:
  1) Encrypt <input_file> to <input_file>.enc.
  2) Decrypt <input_file>.enc back to <input_file>.dec.
  3) Print key information to the console.

Dependencies:
    - Python 3.x
    - liboqs-python (older API: KeyEncapsulation)
    - cryptography
"""

import sys
import os
import oqs  # from older liboqs-python, which provides "KeyEncapsulation"
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class FrodoFileEncryptor:
    """
    Encrypts and decrypts files using FrodoKEM-640-AES for the key encapsulation
    and AES-256 in CBC mode for symmetric encryption.
    
    IMPORTANT: This example is specific to an older liboqs-python API:
       - "KeyEncapsulation" is used instead of "KEM"
       - "import_secret_key()" does not exist; we pass 'secret_key' into the constructor
    """

    def generate_key_and_encrypt(self, input_file_path: str, output_file_path: str):
        """
        1) Generates a FrodoKEM key pair (public_key, secret_key).
        2) Encapsulates a shared secret (ciphertext, shared_secret_enc).
        3) Derives an AES key from the shared secret and encrypts the file content.

        Returns a tuple (public_key, secret_key).
        """

        # 1. Instantiate KeyEncapsulation for FrodoKEM-640-AES
        #    (Older API usage)
        with oqs.KeyEncapsulation("FrodoKEM-640-AES") as frodo:
            # Generate keypair
            public_key = frodo.generate_keypair()
            secret_key = frodo.export_secret_key()
            # Encapsulate shared secret
            kem_ciphertext, shared_secret_enc = frodo.encap_secret(public_key)

        # 2. Derive AES-256 key from the shared secret
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM file encryption (older API)",
            backend=default_backend()
        ).derive(shared_secret_enc)

        # 3. Read plaintext file
        with open(input_file_path, "rb") as f_in:
            plaintext = f_in.read()

        # 4. AES-CBC encryption
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # 5. PKCS#7 padding
        padder = padding.PKCS7(128).padder()
        padded_plaintext = padder.update(plaintext) + padder.finalize()
        aes_ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

        # 6. Write output: [4-byte length of KEM ciphertext][KEM ciphertext][IV][AES ciphertext]
        with open(output_file_path, "wb") as f_out:
            f_out.write(len(kem_ciphertext).to_bytes(4, byteorder="big"))
            f_out.write(kem_ciphertext)
            f_out.write(iv)
            f_out.write(aes_ciphertext)

        return public_key, secret_key

    def decrypt_file(self, secret_key: bytes, input_file_path: str, output_file_path: str):
        """
        1) Reads the previously generated KEM ciphertext + IV + AES ciphertext
        2) Uses KeyEncapsulation with the given 'secret_key' to recover the shared secret
        3) Derives the AES key from the shared secret
        4) Decrypts the file content
        """

        # 1. Read the encrypted file
        with open(input_file_path, "rb") as f_in:
            kem_cipher_len = int.from_bytes(f_in.read(4), byteorder="big")
            kem_ciphertext = f_in.read(kem_cipher_len)
            iv = f_in.read(16)
            aes_ciphertext = f_in.read()

        # 2. Decapsulate shared secret
        #    Since the older API lacks "import_secret_key()",
        #    pass the secret key to the constructor
        with oqs.KeyEncapsulation("FrodoKEM-640-AES", secret_key=secret_key) as frodo_dec:
            shared_secret_dec = frodo_dec.decap_secret(kem_ciphertext)

        # 3. Derive the AES key
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM file encryption (older API)",
            backend=default_backend()
        ).derive(shared_secret_dec)

        # 4. Decrypt using AES-CBC
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(aes_ciphertext) + decryptor.finalize()

        # 5. Remove PKCS#7 padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

        # 6. Write the decrypted plaintext
        with open(output_file_path, "wb") as f_out:
            f_out.write(plaintext)


def main():
    """
    Main function that:
        1) Reads the input file path from command-line argument.
        2) Encrypts the input file to <input_file>.enc.
        3) Decrypts <input_file>.enc to <input_file>.dec.
        4) Displays some details about the keys.
    """

    if len(sys.argv) != 2:
        print(f"Usage: {os.path.basename(sys.argv[0])} <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    encrypted_file = input_file + ".enc"
    decrypted_file = input_file + ".dec"

    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' does not exist.")
        sys.exit(1)

    encryptor = FrodoFileEncryptor()

    # 1. Encrypt
    pub_key, sec_key = encryptor.generate_key_and_encrypt(
        input_file_path=input_file,
        output_file_path=encrypted_file
    )

    print(f"Encryption completed: '{input_file}' -> '{encrypted_file}'")
    print(f"Public key length: {len(pub_key)} bytes")
    print(f"Secret key length: {len(sec_key)} bytes")

    # 2. Decrypt
    encryptor.decrypt_file(
        secret_key=sec_key,
        input_file_path=encrypted_file,
        output_file_path=decrypted_file
    )

    print(f"Decryption completed: '{encrypted_file}' -> '{decrypted_file}'")

    # 3. Show known version info from older API
    #    'oqs_python_version' or 'oqs_version' may exist, but not '__version__' or 'version'
    oqs_python_version = getattr(oqs, "oqs_python_version", None)
    oqs_c_version      = getattr(oqs, "oqs_version", None)
    if oqs_python_version:
        print(f"OQS Python binding version (older API): {oqs_python_version()}")
    if oqs_c_version:
        print(f"liboqs C library version (older API): {oqs_c_version()}")

    print("Process complete.")


if __name__ == "__main__":
    main()
