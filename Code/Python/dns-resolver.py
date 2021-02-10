import socket
import sys

#host = sys.argv[1]
host = input("Host: ")
print("Host: {0}".format(socket.gethostbyname(host)))
