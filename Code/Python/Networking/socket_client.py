# Simple Socket Client
import socket

# Create object:
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Get hostname:
host = socket.gethostname()
port = 9999

# Connect:
sock.connect((host, port))

# Receive response:
response = sock.recv(512) # 512 bytes
print(response.decode('ascii'))

# Close connection:
sock.close()
