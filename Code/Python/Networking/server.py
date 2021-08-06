import socket

HOST = 'localhost'
PORT = 2077

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST, PORT))

s.listen()
print("Waiting connection...")
connection, address = s.accept()
print("{0} connected.".format(address))

while True:
    data = connection.recv(1024)
    if not data:
        print("Closing connection.")
        connection.close()
        break
    connection.send(data)
