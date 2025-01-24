import oqs
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

class FrodoFileEncryptor:
    """
    This class demonstrates how to:
    1) Generate key material using FrodoKEM and encrypt a file.
    2) Decrypt a file using the secret key obtained from FrodoKEM decapsulation.
    """

    def generate_key_and_encrypt(self, input_file_path: str, output_file_path: str):
        """
        Generates a FrodoKEM key pair, encapsulates a shared secret, then uses
        that secret to symmetrically encrypt the file at input_file_path.
        Writes the ciphertext and the FrodoKEM ciphertext to output_file_path.

        Returns:
            A tuple (public_key, secret_key), which can be used for subsequent decryption.
        """

        # 1. Generate the FrodoKEM key pair
        with oqs.KeyEncapsulation("FrodoKEM-640-AES") as frodo:
            public_key = frodo.generate_keypair()
            secret_key = frodo.export_secret_key()

        # 2. Encapsulate the shared secret with the public key
        with oqs.KeyEncapsulation("FrodoKEM-640-AES") as frodo_enc:
            frodo_enc.import_public_key(public_key)
            frodo_ciphertext, shared_secret_enc = frodo_enc.encapsulate()

        # 3. Derive a 256-bit AES key from the shared secret
        #    The shared secret returned by FrodoKEM is already 16, 24, or 32 bytes long,
        #    depending on the parameter set. We use HKDF here for demonstration.
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM encryption",
            backend=default_backend()
        ).derive(shared_secret_enc)

        # 4. Read the plaintext file
        with open(input_file_path, "rb") as f_in:
            plaintext = f_in.read()

        # 5. Use AES in CBC mode to encrypt
        iv = os.urandom(16)  # 128-bit IV
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # 6. Pad the plaintext to a multiple of AES block size
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()

        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # 7. Write the Frodo ciphertext, IV, and AES ciphertext to the output file
        #    Format: [Length of Frodo ciphertext (4 bytes)] [Frodo ciphertext] [IV] [AES ciphertext]
        with open(output_file_path, "wb") as f_out:
            f_out.write(len(frodo_ciphertext).to_bytes(4, byteorder="big"))
            f_out.write(frodo_ciphertext)
            f_out.write(iv)
            f_out.write(ciphertext)

        return public_key, secret_key

    def decrypt_file(self, secret_key: bytes, input_file_path: str, output_file_path: str):
        """
        Decrypts a file previously encrypted by the generate_key_and_encrypt() method.
        Uses the FrodoKEM secret key to decapsulate the shared secret and then
        symmetrically decrypt the file.

        Arguments:
            secret_key: The secret key exported from the FrodoKEM key generation step.
            input_file_path: Path to the encrypted file.
            output_file_path: Destination for the decrypted plaintext.
        """

        # 1. Read the encrypted file
        with open(input_file_path, "rb") as f_in:
            frodo_ciphertext_len = int.from_bytes(f_in.read(4), byteorder="big")
            frodo_ciphertext = f_in.read(frodo_ciphertext_len)
            iv = f_in.read(16)
            ciphertext = f_in.read()

        # 2. Use FrodoKEM to decapsulate the shared secret
        with oqs.KeyEncapsulation("FrodoKEM-640-AES") as frodo_dec:
            frodo_dec.import_secret_key(secret_key)
            shared_secret_dec = frodo_dec.decapsulate(frodo_ciphertext)

        # 3. Derive the same AES key used for encryption
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM encryption",
            backend=default_backend()
        ).derive(shared_secret_dec)

        # 4. Decrypt using AES in CBC mode
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # 5. Remove padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

        # 6. Write the plaintext to the output file
        with open(output_file_path, "wb") as f_out:
            f_out.write(plaintext)

# Usage:

from frodofilecrypt import FrodoFileEncryptor
import sys

if __name__ == "__main__":
    encryptor = FrodoFileEncryptor()

    pub_key, sec_key = encryptor.generate_key_and_encrypt(
        input_file_path=sys.argv[1],
        output_file_path="encrypted.bin"
    )

    print("Public key:", pub_key)
    print("Secret key:", sec_key)
