import socket
import sys

for i in range(1, 65535):
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if skt.connect((sys.argv[1], i)) == 0:
            print("Port: {0} OPEN".format(i))
        skt.close()
    except:
        continue
