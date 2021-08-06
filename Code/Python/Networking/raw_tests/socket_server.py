# Simple Socket Server
import socket

# Create object:
server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Get machine's local name:
host = socket.gethostname()
port = 9999

# Bind socket to this host and port:
server_sock.bind((host, port))

# Listen to five requests:
server_sock.listen(5)

# Test:
while True:
    client, address = server_sock.accept()
    print("Got a connection from %s." %str(address))
    response = "Message received.\r\n"
    client.send(response.encode('ascii'))
    client.close()
