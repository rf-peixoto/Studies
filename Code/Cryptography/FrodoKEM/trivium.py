def bytes_to_bits(b):
    bits = []
    for byte in b:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits

def bits_to_bytes(bits):
    b = []
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i:i+8]:
            byte = (byte << 1) | bit
        b.append(byte)
    return bytes(b)

class Trivium:
    def __init__(self, key, iv):
        if len(key) != 80 or len(iv) != 80:
            raise ValueError("Key and IV must be 80 bits each.")
        
        self.state = [0] * 288
        
        # Load key into bits 0-79.
        for i in range(80):
            self.state[i] = key[i]
        # Bits 80-92 remain zero.
        
        # Load IV into bits 93-172.
        for i in range(80):
            self.state[93 + i] = iv[i]
        # Bits 173-176 remain zero.
        
        # Initialize bits 177-287; bits 285-287 set to 1.
        for i in range(177, 285):
            self.state[i] = 0
        self.state[285] = 1
        self.state[286] = 1
        self.state[287] = 1
        
        # Warm-up rounds.
        for _ in range(1152):
            self._update()
    
    def _update(self):
        s = self.state
        # Compute temporary variables (zero-indexed).
        t1 = s[65] ^ s[92]
        t2 = s[161] ^ s[176]
        t3 = s[242] ^ s[287]
        
        # (output bit = t1 ⊕ t2 ⊕ t3) – not used directly for encryption.
        output = t1 ^ t2 ^ t3
        
        # Nonlinear feedback.
        t1 = t1 ^ (s[90] & s[91]) ^ s[170]
        t2 = t2 ^ (s[174] & s[175]) ^ s[263]
        t3 = t3 ^ (s[285] & s[286]) ^ s[68]
        
        # Shift registers and update.
        newA = [t3] + s[0:92]
        newB = [t1] + s[93:176]
        newC = [t2] + s[177:287]
        
        self.state = newA + newB + newC
        
        return output
    
    def keystream(self, n):
        stream = []
        for _ in range(n):
            stream.append(self._update())
        return stream

class TriviumCipher:
    def __init__(self, key, iv):
        # Accept key and IV as bytes or as strings (UTF-8 encoded).
        if isinstance(key, str):
            key = key.encode("utf-8")
        if isinstance(iv, str):
            iv = iv.encode("utf-8")
        if len(key) != 10:
            raise ValueError("Key must be 10 bytes (80 bits).")
        if len(iv) != 10:
            raise ValueError("IV must be 10 bytes (80 bits).")
        self.key = key
        self.iv = iv
    
    def _create_cipher(self):
        key_bits = bytes_to_bits(self.key)
        iv_bits = bytes_to_bits(self.iv)
        return Trivium(key_bits, iv_bits)
    
    def encrypt(self, plaintext: str) -> bytes:
        plaintext_bytes = plaintext.encode("utf-8")
        cipher = self._create_cipher()
        # Generate enough keystream bits for the plaintext.
        keystream_bits = cipher.keystream(len(plaintext_bytes) * 8)
        keystream_bytes = bits_to_bytes(keystream_bits)
        # XOR each plaintext byte with the corresponding keystream byte.
        ciphertext = bytes([pb ^ kb for pb, kb in zip(plaintext_bytes, keystream_bytes)])
        return ciphertext
    
    def decrypt(self, ciphertext: bytes) -> str:
        cipher = self._create_cipher()
        keystream_bits = cipher.keystream(len(ciphertext) * 8)
        keystream_bytes = bits_to_bytes(keystream_bits)
        plaintext_bytes = bytes([cb ^ kb for cb, kb in zip(ciphertext, keystream_bytes)])
        return plaintext_bytes.decode("utf-8")

# Example usage:
if __name__ == "__main__":
    # Define a 10-byte key and IV.
    key = b'\x01\x02\x03\x04\x05\x06\x07\x08\t\n'       # 10 bytes (80 bits)
    iv = b'\n\t\x08\x07\x06\x05\x04\x03\x02\x01'          # 10 bytes (80 bits)
    cipher = TriviumCipher(key, iv)
    
    message = "This is a secret message."
    print("Original message:", message)
    
    encrypted = cipher.encrypt(message)
    print("Encrypted (hex):", encrypted.hex())
    
    decrypted = cipher.decrypt(encrypted)
    print("Decrypted message:", decrypted)
