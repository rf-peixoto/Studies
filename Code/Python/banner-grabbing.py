# Banner Grabbing
# #!/usr/bin/python
import socket

host = input("Host: ")
port = int(input("Port: "))

sckt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
connection = sckt.connect((host, port))

banner = sckt.recv(1024)
print(banner)
