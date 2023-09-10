from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import PrivateFormat
from cryptography.hazmat.primitives.serialization import NoEncryption

# Load the private key from an external file (PEM format)
with open('private_key.pem', 'rb') as key_file:
    private_key_data = key_file.read()

private_key = load_pem_private_key(private_key_data, password=None, backend=default_backend())

# Message to sign
message = b"Hello, this is a message to sign"

# Sign the message
signature = private_key.sign(
    message,
    padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH
    ),
    hashes.SHA256()
)

# You can now use the 'signature' as the digital signature of your message.
print("Digital Signature:", signature.hex())
