#SMTP ENUM
import requests
import socket
import sys
import re

if len(sys.argv) != 3:
    print("Usage: smtpenum.py (ip address) (username)")
    sys.exit(0)

ip = sys.argv[1]
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.connect((ip, 25))
banner = tcp.recv(1024)
print(banner)

tcp.send("VRFY {0}\r\n".format(sys.argv[2]))
user = tcp.recv(1024)
print(user)

# ===============================================================
# Test:

with open("word_list.txt", "r") as fl:
    word_list = fl.read()
    fl.close()

port = 25
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.connect((sys.argv[1], port))
bannert = tcp.recv(1024)

for word in word_list:
    tcp.send("VRFY {0}".format(word))
    user = tcp.recv(1024)
    if re.search("252", user):
        print(user.replace("252 2.0.0", ""))
