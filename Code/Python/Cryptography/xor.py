# ref: https://stackoverflow.com/questions/68409078/differences-of-the-ord-function-between-python-2-7-and-3-9/68409604#68409604

import binascii

def encrypt(content: str, key: str) -> bytes:
    key_id = 0
    xored = ""
    for key_id, c in enumerate(content):
        xored += chr(ord(key[key_id % len(key)]) ^ ord(c))
        key_id += 1
    return binascii.hexlify(xored.encode())

def decrypt(content: bytes, key: str) -> str:
    key_id = 0
    xored = ""
    for key_id, c in enumerate(binascii.unhexlify(content).decode()):
        xored += chr(ord(key[key_id % len(key)]) ^ ord(c))
        key_id += 1
    return xored.encode()
