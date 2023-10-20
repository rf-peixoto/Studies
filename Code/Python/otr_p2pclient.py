# Example made by GPT.
import socket
from potr.compatcrypto import DSAKey
from potr import SimpleContext

# Generate DSA key for Bob
bob_key = DSAKey.generate()

# Create a socket object
s = socket.socket()
host = socket.gethostname()
port = 12345

# Connect to Alice
s.connect((host, port))

# Initialize OTR context
bob_context = SimpleContext('Bob', 'Alice', bob_key)

while True:
    message = input("Send: ")
    encrypted_message = bob_context.sendMessage(potr.context.FRAGMENT_SEND_ALL, message)[0]
        
    s.send(encrypted_message.encode('utf-8'))
    
    received_data = s.recv(1024).decode('utf-8')
    decrypted_message, tlvs = bob_context.receiveMessage(received_data)
    
    print(f"Received: {decrypted_message}")
