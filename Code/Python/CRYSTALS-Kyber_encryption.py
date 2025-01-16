#pip install python-oqs cryptography
import os
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import oqs


class KyberFileEncryptor:
    """
    Demonstrates file encryption and decryption using a CRYSTALS-Kyber KEM
    (provided by python-oqs) alongside a symmetric cipher (AES).
    """

    def __init__(self, kyber_variant: str = "Kyber512"):
        """
        Initializes the KyberFileEncryptor with a specified CRYSTALS-Kyber variant.
        Supported variants can include 'Kyber512', 'Kyber768', 'Kyber1024'.
        """
        self.kyber_variant = kyber_variant
        # Generate new keys on initialization
        self.public_key, self.private_key = self.generate_keys()

    def generate_keys(self):
        """
        Generates and returns a new public-private key pair for the CRYSTALS-Kyber variant.
        """
        kem = oqs.KeyEncapsulation(self.kyber_variant)
        public_key = kem.generate_keypair()
        private_key = kem.export_secret_key()
        return public_key, private_key

    def encrypt_file(self, input_file_path: str, output_file_path: str):
        """
        Encrypts the file at 'input_file_path' using a shared secret derived from
        the CRYSTALS-Kyber KEM, then saves the ciphertext (KEM ciphertext + AES ciphertext)
        to 'output_file_path'.
        """
        # Encapsulate a shared secret using the stored public key
        kem_obj = oqs.KeyEncapsulation(self.kyber_variant)
        kem_ciphertext, shared_secret = kem_obj.encap_secret(self.public_key)

        # Derive an AES key from the shared secret
        # In production, consider a robust KDF instead of a direct slice.
        # AES-256 requires 32 bytes.
        aes_key = shared_secret[:32]

        # Encrypt the file contents using AES in CBC mode
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # Read input file data
        with open(input_file_path, "rb") as f_in:
            plaintext_data = f_in.read()

        # Pad data for AES block size
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext_data) + padder.finalize()

        # Perform AES encryption
        aes_ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # Write output: 
        # [KEM Ciphertext Length (4 bytes)] + [KEM Ciphertext] + [IV] + [AES Ciphertext]
        with open(output_file_path, "wb") as f_out:
            # Write length of the KEM ciphertext for parsing during decryption
            f_out.write(struct.pack(">I", len(kem_ciphertext)))
            f_out.write(kem_ciphertext)
            f_out.write(iv)
            f_out.write(aes_ciphertext)

    def decrypt_file(self, input_file_path: str, output_file_path: str):
        """
        Decrypts the file at 'input_file_path' (which must contain the KEM ciphertext
        and AES ciphertext) using the CRYSTALS-Kyber KEM private key and saves the
        decrypted data to 'output_file_path'.
        """
        with open(input_file_path, "rb") as f_in:
            # Read the first 4 bytes for the KEM ciphertext length
            kem_ciphertext_length_data = f_in.read(4)
            kem_ciphertext_length = struct.unpack(">I", kem_ciphertext_length_data)[0]

            # Read the KEM ciphertext
            kem_ciphertext = f_in.read(kem_ciphertext_length)

            # Read the IV (16 bytes)
            iv = f_in.read(16)

            # Remaining data is AES ciphertext
            aes_ciphertext = f_in.read()

        # Create a new KEM object and import our private key
        kem_obj = oqs.KeyEncapsulation(self.kyber_variant)
        kem_obj.import_secret_key(self.private_key)

        # Decapsulate the shared secret
        shared_secret = kem_obj.decap_secret(kem_ciphertext)

        # Derive the AES key from the shared secret
        aes_key = shared_secret[:32]

        # Decrypt using AES in CBC mode
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded_data = decryptor.update(aes_ciphertext) + decryptor.finalize()

        # Remove AES padding
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()

        # Write the decrypted data to the output file
        with open(output_file_path, "wb") as f_out:
            f_out.write(decrypted_data)


# Example usage (not part of the class itself):
# 
# encryptor = KyberFileEncryptor("Kyber512")
# encryptor.encrypt_file("plain_input.bin", "encrypted_output.bin")
# encryptor.decrypt_file("encrypted_output.bin", "decrypted_output.bin")
