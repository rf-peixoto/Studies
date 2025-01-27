import os

# The following import uses liboqs-python (installed from https://github.com/open-quantum-safe/liboqs-python)
import oqs

# For symmetric encryption
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

class FrodoKEMFileEncryptor:
    """
    Demonstrates generating key material with FrodoKEM, and using that key
    to symmetrically encrypt/decrypt a file.
    """

    def generate_key_and_encrypt(self, input_file_path: str, output_file_path: str):
        """
        1) Generates a FrodoKEM key pair and encapsulates a shared secret.
        2) Uses the shared secret to encrypt the contents of input_file_path
           via AES in CBC mode.
        3) Writes the ciphertext to output_file_path, together with the
           FrodoKEM ciphertext and IV.
        
        Returns:
            public_key: Byte string of the FrodoKEM public key
            secret_key: Byte string of the FrodoKEM secret key
        """

        # 1. Instantiate and generate key pair
        with oqs.KEM("FrodoKEM-640-AES") as frodo:
            public_key = frodo.generate_keypair()
            secret_key = frodo.export_secret_key()

            # 2. Encapsulate the shared secret
            frodo_ciphertext, shared_secret_enc = frodo.encap_secret(public_key)

        # 3. Derive a 256-bit key (AES key) from the shared secret
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM encryption",
            backend=default_backend()
        ).derive(shared_secret_enc)

        # 4. Read plaintext from file
        with open(input_file_path, "rb") as f_in:
            plaintext = f_in.read()

        # 5. Encrypt using AES-CBC
        iv = os.urandom(16)  # Initialization vector
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # 6. PKCS#7 padding
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()

        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # 7. Write to output file:
        #    [4 bytes: length of FrodoKEM ciphertext] [FrodoKEM ciphertext] [IV] [AES ciphertext]
        with open(output_file_path, "wb") as f_out:
            f_out.write(len(frodo_ciphertext).to_bytes(4, byteorder="big"))
            f_out.write(frodo_ciphertext)
            f_out.write(iv)
            f_out.write(ciphertext)

        return public_key, secret_key

    def decrypt_file(self, secret_key: bytes, input_file_path: str, output_file_path: str):
        """
        Decrypts a file previously encrypted by this class's generate_key_and_encrypt method,
        using the FrodoKEM secret key to decapsulate the shared secret and then AES-CBC
        for symmetric decryption.

        Args:
            secret_key (bytes): FrodoKEM secret key
            input_file_path (str): Path to the encrypted file
            output_file_path (str): Destination for the decrypted plaintext
        """

        # 1. Read the file content
        with open(input_file_path, "rb") as f_in:
            frodo_ciphertext_len = int.from_bytes(f_in.read(4), byteorder="big")
            frodo_ciphertext = f_in.read(frodo_ciphertext_len)
            iv = f_in.read(16)
            ciphertext = f_in.read()

        # 2. Decapsulate the shared secret using the secret key
        with oqs.KEM("FrodoKEM-640-AES") as frodo_dec:
            frodo_dec.import_secret_key(secret_key)
            shared_secret_dec = frodo_dec.decap_secret(frodo_ciphertext)

        # 3. Derive the same AES key
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"FrodoKEM encryption",
            backend=default_backend()
        ).derive(shared_secret_dec)

        # 4. Decrypt using AES-CBC
        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # 5. Remove PKCS#7 padding
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

        # 6. Save the decrypted plaintext
        with open(output_file_path, "wb") as f_out:
            f_out.write(plaintext)

# Usage example:
import sys
def main():
    encryptor = FrodoKEMFileEncryptor()

    # Encrypt
    public_key, secret_key = encryptor.generate_key_and_encrypt(
        input_file_path=sys.argv[1],
        output_file_path="test_encrypted.bin"
    )

    # (Optional) Display keys
    print("Public key:", public_key)
    print("Secret key:", secret_key)

    # Decrypt
    encryptor.decrypt_file(
        secret_key=secret_key,
        input_file_path="test_encrypted.bin",
        output_file_path="test_decrypted.txt"
    )
    print("Decryption completed.")

if __name__ == "__main__":
    main()
