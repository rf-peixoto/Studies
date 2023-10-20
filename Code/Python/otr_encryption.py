# Reference: ChatGPT, https://en.wikipedia.org/wiki/Off-the-record_messaging
# pip install python-otr

from potr.compatcrypto import DSAKey
from potr import SimpleContext

# Generate DSA keys for Alice and Bob
alice_key = DSAKey.generate()
bob_key = DSAKey.generate()

# Initialize OTR contexts for Alice and Bob
alice_context = SimpleContext('Alice', 'Bob', alice_key)
bob_context = SimpleContext('Bob', 'Alice', bob_key)

# Simulate Alice sending an encrypted message to Bob
alice_message = 'Hello, Bob!'
alice_encrypted_message = alice_context.sendMessage(
    potr.context.FRAGMENT_SEND_ALL, alice_message)

# Simulate Bob decrypting the message
bob_decrypted_message = bob_context.receiveMessage(alice_encrypted_message[0])[0]

print(f"Bob decrypted message: {bob_decrypted_message}")

# Simulate Bob replying to Alice
bob_message = 'Hello, Alice!'
bob_encrypted_message = bob_context.sendMessage(
    potr.context.FRAGMENT_SEND_ALL, bob_message)

# Simulate Alice decrypting the reply
alice_decrypted_message = alice_context.receiveMessage(bob_encrypted_message[0])[0]

print(f"Alice decrypted message: {alice_decrypted_message}")
