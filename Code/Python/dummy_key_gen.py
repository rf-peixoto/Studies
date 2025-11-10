import os
import base64

# Generate 32 random bytes (256 bits)
private_key_bytes = os.urandom(32)

# Encode in Base64 (44 characters with padding)
private_key_b64 = base64.b64encode(private_key_bytes).decode('utf-8')

print("Private key (Base64):", private_key_b64)
