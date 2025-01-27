import os
import sys
from oqs import KeyEncapsulation
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class FrodoKEMHandler:
    def __init__(self):
        self.kem_alg = 'FrodoKEM-1344-AES'
        self.kem = KeyEncapsulation(self.kem_alg)

    def generate_key_pair(self):
        """Generate a key pair (public key and private key)."""
        public_key = self.kem.generate_keypair()
        private_key = self.kem.export_secret_key()
        return public_key, private_key

    def encrypt_file(self, file_path):
        """Encrypt a file using a newly generated key."""
        # Generate key pair
        public_key, private_key = self.generate_key_pair()
        
        # Display generated keys
        print("\n=== Generated Keys ===")
        print(f"Public Key: {public_key.hex()}")
        print(f"Private Key: {private_key.hex()}")
        
        # Generate a shared secret and ciphertext
        ciphertext, shared_secret_enc = self.kem.encap_secret(public_key)
        
        # Display shared secret and ciphertext
        print("\n=== Encryption Details ===")
        print(f"Shared Secret: {shared_secret_enc.hex()}")
        print(f"Ciphertext: {ciphertext.hex()}")
        
        # Read the file content
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        # Encrypt the file content using AES-GCM
        aes_key = shared_secret_enc[:32]  # Use first 32 bytes of shared secret as AES key
        encrypted_content, aes_nonce, aes_tag = self.aes_encrypt(file_content, aes_key)
        
        # Apply XOR encryption as an additional layer (for demonstration)
        xor_encrypted_content = self.xor_encrypt(encrypted_content, shared_secret_enc)
        
        # Save the encrypted content to a new file
        encrypted_file_path = file_path + '.enc'
        with open(encrypted_file_path, 'wb') as encrypted_file:
            # Write ciphertext, AES nonce, AES tag, and encrypted content
            encrypted_file.write(ciphertext + aes_nonce + aes_tag + xor_encrypted_content)
        
        print(f"\nFile encrypted and saved as: {encrypted_file_path}")
        return encrypted_file_path, private_key

    def decrypt_file(self, encrypted_file_path, private_key):
        """Decrypt a file using the provided private key."""
        # Read the encrypted file content
        with open(encrypted_file_path, 'rb') as encrypted_file:
            encrypted_content = encrypted_file.read()
        
        # Extract components from the encrypted file
        ciphertext_length = self.kem.details['length_ciphertext']
        aes_nonce_length = 12  # GCM nonce is 12 bytes
        aes_tag_length = 16    # GCM tag is 16 bytes
        
        ciphertext = encrypted_content[:ciphertext_length]
        aes_nonce = encrypted_content[ciphertext_length:ciphertext_length + aes_nonce_length]
        aes_tag = encrypted_content[ciphertext_length + aes_nonce_length:ciphertext_length + aes_nonce_length + aes_tag_length]
        xor_encrypted_data = encrypted_content[ciphertext_length + aes_nonce_length + aes_tag_length:]
        
        # Decapsulate the shared secret using the private key
        shared_secret_dec = self.kem.decap_secret(ciphertext, private_key)
        
        # Display decapsulated shared secret
        print("\n=== Decryption Details ===")
        print(f"Decapsulated Shared Secret: {shared_secret_dec.hex()}")
        
        # Decrypt the XOR layer
        decrypted_xor_content = self.xor_encrypt(xor_encrypted_data, shared_secret_dec)
        
        # Decrypt the AES layer
        aes_key = shared_secret_dec[:32]  # Use first 32 bytes of shared secret as AES key
        decrypted_content = self.aes_decrypt(decrypted_xor_content, aes_key, aes_nonce, aes_tag)
        
        # Save the decrypted content to a new file
        decrypted_file_path = encrypted_file_path.replace('.enc', '.dec')
        with open(decrypted_file_path, 'wb') as decrypted_file:
            decrypted_file.write(decrypted_content)
        
        print(f"\nFile decrypted and saved as: {decrypted_file_path}")
        return decrypted_file_path

    @staticmethod
    def aes_encrypt(data, key):
        """Encrypt data using AES-GCM."""
        # Generate a random 12-byte nonce for AES-GCM
        nonce = os.urandom(12)
        
        # Create AES-GCM cipher
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        
        # Encrypt the data
        encrypted_data = encryptor.update(data) + encryptor.finalize()
        
        # Return encrypted data, nonce, and tag
        return encrypted_data, nonce, encryptor.tag

    @staticmethod
    def aes_decrypt(encrypted_data, key, nonce, tag):
        """Decrypt data using AES-GCM."""
        # Create AES-GCM cipher
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        
        # Decrypt the data
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
        
        return decrypted_data

    @staticmethod
    def xor_encrypt(data, key):
        """Simple XOR encryption/decryption."""
        key_bytes = key
        if len(key_bytes) < len(data):
            key_bytes = key_bytes * (len(data) // len(key_bytes)) + key_bytes[:len(data) % len(key_bytes)]
        return bytes([a ^ b for a, b in zip(data, key_bytes)])

# Main function
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python frodokem-1344-xor-aes.py <file_to_encrypt>")
        sys.exit(1)
    
    file_to_encrypt = sys.argv[1]
    
    if not os.path.exists(file_to_encrypt):
        print(f"Error: File '{file_to_encrypt}' not found.")
        sys.exit(1)
    
    handler = FrodoKEMHandler()
    
    # Encrypt the file
    print(f"\nEncrypting file: {file_to_encrypt}")
    encrypted_file, private_key = handler.encrypt_file(file_to_encrypt)
    
    # Decrypt the file
    print(f"\nDecrypting file: {encrypted_file}")
    handler.decrypt_file(encrypted_file, private_key)
