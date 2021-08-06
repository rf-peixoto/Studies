import socket

HOST = '127.0.0.1'
PORT = 2077

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

s.send('Hello word'.encode())
data = s.recv(1024)

print('Echo: ' + data.decode())
