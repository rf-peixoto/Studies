"""
FrodoKEM file encryption script using the older liboqs-python API (KeyEncapsulation).
Requires:
    - Python 3.x
    - liboqs-python (older version that uses KeyEncapsulation) 
    - cryptography
"""

import os
import sys
import oqs  # from liboqs-python (older version using KeyEncapsulation)
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

class FrodoFileEncryptor:
    """
    This class encrypts and decrypts files using FrodoKEM-640-AES for
    key encapsulation and AES-256-CBC for symmetric encryption.
    Note: Uses the older KeyEncapsulation class from liboqs-python.
    """

    def generate_key_and_encrypt(self, input_file_path: str, output_file_path: str):
        """
        Generates a FrodoKEM key pair, encapsulates a shared secret, and
        uses that secret to symmetrically encrypt the file at 'input_file_path'.

        Args:
            input_file_path (str): Path to the plaintext file
            output_file_path (str): Path to store the encrypted file

        Returns:
            A tuple (public_key, secret_key) that can be used for decryption.

        Note: The library uses the older 'KeyEncapsulation' class instead of 'KEM'.
              The functions are 'encap_secret()' and 'decap_secret()'.
        """

        # 1. Create the KeyEncapsulation object for FrodoKEM-640-AES
        #    (Older API uses KeyEncapsulation rather than KEM)
        with oqs.KeyEncapsulation("FrodoKEM-640-AES") as frodo:
            # Generate a key pair (public key and in-memory secret key)
            public_key = frodo.generate_keypair()
            secret_key = frodo.export_secret_key()

            # Encapsulate the shared secret (produces kem_ciphertext + shared_secret)
            frodo_ciphertext, shared_secret_enc = frodo.encap_secret(public_key)

        # 2. Derive an AES-256 key from the shared secret
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM file encryption (older API)",
            backend=default_backend()
        ).derive(shared_secret_enc)

        # 3. Read the plaintext from disk
        with open(input_file_path, "rb") as file_in:
            plaintext = file_in.read()

        # 4. Encrypt using AES in CBC mode
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # 5. Pad the plaintext (PKCS#7) to match block size
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # 6. Write the output in the format:
        #    [4 bytes: length of Frodo ciphertext]
        #    [Frodo ciphertext (kem_ciphertext)]
        #    [AES IV (16 bytes)]
        #    [AES ciphertext]
        with open(output_file_path, "wb") as file_out:
            file_out.write(len(frodo_ciphertext).to_bytes(4, byteorder="big"))
            file_out.write(frodo_ciphertext)
            file_out.write(iv)
            file_out.write(ciphertext)

        # Return the public and secret keys so you may store or transmit them
        return public_key, secret_key

    def decrypt_file(self, secret_key: bytes, input_file_path: str, output_file_path: str):
    """
    Decrypts a file encrypted by 'generate_key_and_encrypt', using FrodoKEM-640-AES.

    Args:
        secret_key (bytes): Secret key from the FrodoKEM key generation step.
        input_file_path (str): Path to the encrypted file.
        output_file_path (str): Path to write the decrypted plaintext.
    """

    # 1. Read the encrypted data
    with open(input_file_path, "rb") as file_in:
        frodo_cipher_len = int.from_bytes(file_in.read(4), byteorder="big")
        frodo_ciphertext = file_in.read(frodo_cipher_len)
        iv = file_in.read(16)
        ciphertext = file_in.read()

    # 2. Create KeyEncapsulation with the secret key passed to the constructor
    with oqs.KeyEncapsulation("FrodoKEM-640-AES", secret_key=secret_key) as frodo_dec:
        # Decapsulate the shared secret
        shared_secret_dec = frodo_dec.decap_secret(frodo_ciphertext)

    # 3. Derive the AES-256 key from the shared secret
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
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # 5. Remove PKCS#7 padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    # 6. Write the decrypted data to output_file_path
    with open(output_file_path, "wb") as file_out:
        file_out.write(plaintext)


def main():
    """
    Example usage of the FrodoFileEncryptor class.
    Demonstrates encrypting and then decrypting a file with FrodoKEM-640-AES.
    """

    # Instantiate the encryptor class
    encryptor = FrodoFileEncryptor()

    # Sample file paths (adjust as needed)
    input_file = sys.argv[1]
    encrypted_file = "example_encrypted.bin"
    decrypted_file = "example_decrypted.txt"

    # Generate keys and encrypt
    pub_key, sec_key = encryptor.generate_key_and_encrypt(
        input_file_path=input_file,
        output_file_path=encrypted_file
    )

    # (Optional) Show that the older library does not have '__version__'
    # but does have 'oqs_python_version' and 'oqs_version'
    print("Public key length:", len(pub_key))
    print("Secret key length:", len(sec_key))
    print("OQS Python binding version attribute (older):", getattr(oqs, 'oqs_python_version', 'Not present'))
    print("liboqs C library version attribute (older):", getattr(oqs, 'oqs_version', 'Not present'))

    # Decrypt
    encryptor.decrypt_file(
        secret_key=sec_key,
        input_file_path=encrypted_file,
        output_file_path=decrypted_file
    )

    print("Decryption complete. Check example_decrypted.txt for output.")

if __name__ == "__main__":
    main()
