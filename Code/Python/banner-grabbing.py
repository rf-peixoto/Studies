#!/usr/bin/python
import socket
# Target
host = input("Host: ")
port = int(input("Port: "))
# Socket
sckt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
connection = sckt.connect((host, port))
# Banner
print(sckt.recv(1024))
