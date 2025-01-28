import os
import sys
from oqs import KeyEncapsulation
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

class FrodoKEMHandler:
    def __init__(self):
        """Initialize the FrodoKEM handler with the specified algorithm."""
        self.kem_alg = 'FrodoKEM-1344-AES'
        self.kem = KeyEncapsulation(self.kem_alg)
        self.ciphertext_length = self.kem.details['length_ciphertext']
        self.aes_nonce_length = 12  # GCM nonce is 12 bytes
        self.aes_tag_length = 16    # GCM tag is 16 bytes

    def generate_key_pair(self):
        """Generate a key pair (public key and private key)."""
        public_key = self.kem.generate_keypair()
        private_key = self.kem.export_secret_key()
        return public_key, private_key

    def encrypt_file(self, file_path, public_key):
        """Encrypt a file using FrodoKEM and AES-GCM."""
        try:
            # Generate a shared secret and ciphertext
            ciphertext, shared_secret_enc = self.kem.encap_secret(public_key)
            
            # Read the file content
            with open(file_path, 'rb') as file:
                file_content = file.read()
            
            # Derive a unique key using the filename as salt
            salt = os.path.basename(file_path).encode()  # Use filename as salt
            unique_key = self._derive_key(shared_secret_enc, salt)
            
            # Encrypt the file content using AES-GCM
            encrypted_content, aes_nonce, aes_tag = self._aes_encrypt(file_content, unique_key)
            
            # Save the encrypted content to a new file with .dpsk extension
            encrypted_file_path = file_path + '.dpsk'
            with open(encrypted_file_path, 'wb') as encrypted_file:
                # Write ciphertext, AES nonce, AES tag, and encrypted content
                encrypted_file.write(ciphertext + aes_nonce + aes_tag + encrypted_content)
            
            print(f"File encrypted and saved as: {encrypted_file_path}")
            return encrypted_file_path
        except Exception as e:
            print(f"Encryption failed for {file_path}: {e}")
            raise

    def decrypt_file(self, encrypted_file_path, private_key):
        """Decrypt a file using the provided private key."""
        try:
            # Read the encrypted file content
            with open(encrypted_file_path, 'rb') as encrypted_file:
                encrypted_content = encrypted_file.read()
            
            # Extract components from the encrypted file
            ciphertext = encrypted_content[:self.ciphertext_length]
            aes_nonce = encrypted_content[self.ciphertext_length:self.ciphertext_length + self.aes_nonce_length]
            aes_tag = encrypted_content[self.ciphertext_length + self.aes_nonce_length:self.ciphertext_length + self.aes_nonce_length + self.aes_tag_length]
            encrypted_data = encrypted_content[self.ciphertext_length + self.aes_nonce_length + self.aes_tag_length:]
            
            # Decapsulate the shared secret using the private key
            shared_secret_dec = self.kem.decap_secret(ciphertext, private_key)
            
            # Derive the unique key using the filename as salt
            salt = os.path.basename(encrypted_file_path).replace('.dpsk', '').encode()  # Remove .dpsk to get original filename
            unique_key = self._derive_key(shared_secret_dec, salt)
            
            # Decrypt the AES layer
            decrypted_content = self._aes_decrypt(encrypted_data, unique_key, aes_nonce, aes_tag)
            
            # Save the decrypted content to a new file (remove .dpsk extension)
            decrypted_file_path = encrypted_file_path.replace('.dpsk', '')
            with open(decrypted_file_path, 'wb') as decrypted_file:
                decrypted_file.write(decrypted_content)
            
            print(f"File decrypted and saved as: {decrypted_file_path}")
            return decrypted_file_path
        except InvalidTag:
            print(f"Decryption failed for {encrypted_file_path}: Invalid tag. The file may be corrupted or tampered with.")
            raise
        except Exception as e:
            print(f"Decryption failed for {encrypted_file_path}: {e}")
            raise

    def decrypt_all_files(self, root_dir, private_key):
        """Decrypt all .dpsk files in the specified directory and its subdirectories."""
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename.endswith('.dpsk'):
                    encrypted_file_path = os.path.join(dirpath, filename)
                    try:
                        self.decrypt_file(encrypted_file_path, private_key)
                    except Exception as e:
                        print(f"Skipping {encrypted_file_path} due to an error: {e}")

    @staticmethod
    def _derive_key(shared_secret, salt):
        """Derive a unique key using HKDF."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 32 bytes for AES-256
            salt=salt,
            info=b'frodokem-1344-aes',
        )
        return hkdf.derive(shared_secret)

    @staticmethod
    def _aes_encrypt(data, key):
        """Encrypt data using AES-GCM."""
        nonce = os.urandom(12)  # Generate a random 12-byte nonce for AES-GCM
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(data) + encryptor.finalize()
        return encrypted_data, nonce, encryptor.tag

    @staticmethod
    def _aes_decrypt(encrypted_data, key, nonce, tag):
        """Decrypt data using AES-GCM."""
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
        return decrypted_data

# Main function
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  To encrypt: python frodokem-1344-aes.py encrypt <file_or_directory>")
        print("  To decrypt: python frodokem-1344-aes.py decrypt <private_key_hex> <root_directory>")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    if mode == "encrypt":
        if len(sys.argv) != 3:
            print("Usage: python frodokem-1344-aes.py encrypt <file_or_directory>")
            sys.exit(1)
        
        target = sys.argv[2]
        handler = FrodoKEMHandler()
        
        # Generate a key pair
        public_key, private_key = handler.generate_key_pair()
        print("\n=== Private Key ===")
        print(f"Save this private key for decryption: {private_key.hex()}")
        
        # Encrypt file(s)
        if os.path.isfile(target):
            handler.encrypt_file(target, public_key)
        elif os.path.isdir(target):
            for dirpath, _, filenames in os.walk(target):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    handler.encrypt_file(file_path, public_key)
        else:
            print(f"Error: {target} is not a valid file or directory.")
            sys.exit(1)
    
    elif mode == "decrypt":
        if len(sys.argv) != 4:
            print("Usage: python frodokem-1344-aes.py decrypt <private_key_hex> <root_directory>")
            sys.exit(1)
        
        private_key_hex = sys.argv[2]
        root_directory = sys.argv[3]
        
        # Convert private key from hex to bytes
        try:
            private_key = bytes.fromhex(private_key_hex)
        except ValueError:
            print("Error: Invalid private key format. It must be a hexadecimal string.")
            sys.exit(1)
        
        handler = FrodoKEMHandler()
        handler.decrypt_all_files(root_directory, private_key)
    
    else:
        print("Invalid mode. Use 'encrypt' or 'decrypt'.")
        sys.exit(1)
