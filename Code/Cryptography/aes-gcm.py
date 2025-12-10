import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate_key(key_size_bits: int = 256) -> bytes:
    """
    Generate a random AES key.

    key_size_bits: 128, 192, or 256.
    """
    if key_size_bits not in (128, 192, 256):
        raise ValueError("key_size_bits must be 128, 192, or 256")
    return os.urandom(key_size_bits // 8)


def encrypt_aes_gcm(key: bytes, plaintext: bytes, aad: bytes | None = None):
    """
    Encrypt using AES-GCM.

    Returns (nonce, ciphertext_with_tag).

    In this API, the authentication tag is appended to the ciphertext.
    """
    # GCM standard recommends a 96-bit (12-byte) nonce
    nonce = os.urandom(12)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None) -> bytes:
    """
    Decrypt using AES-GCM.

    Raises InvalidTag if authentication fails.
    """
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    return plaintext


if __name__ == "__main__":
    # -----------------------------
    # Example usage
    # -----------------------------

    # 1) Generate a random 256-bit key
    key = generate_key(256)

    # 2) Define plaintext and AAD
    plaintext_str = "AES-GCM test message: confidentiality + integrity."
    plaintext = plaintext_str.encode("utf-8")

    # AAD = associated data (authenticated but not encrypted)
    aad = b"example-header-or-metadata"

    # 3) Encrypt
    nonce, ciphertext = encrypt_aes_gcm(key, plaintext, aad)

    print(f"Key (hex):        {key.hex()}")
    print(f"Nonce (hex):      {nonce.hex()}")
    print(f"Ciphertext+Tag:   {ciphertext.hex()}")

    # 4) Decrypt
    try:
        recovered_plaintext = decrypt_aes_gcm(key, nonce, ciphertext, aad)
        print(f"Recovered text:   {recovered_plaintext.decode('utf-8')}")
    except Exception as e:
        # If the tag does not validate, decryption will fail
        print(f"Decryption failed: {e}")
