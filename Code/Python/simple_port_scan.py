# Nada de mais aqui, só um scanner genérico.

import socket

ips = input("IPs: ").split(" ")
ports = [20, 21, 22, 23, 25, 53, 67, 68, 80, 110, 123, 156, 143, 161, 179, 443, 1723, 1863, 3128, 3389, 8080]
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

print("Connecting...")

for ip in ips:
    for p in ports:
        try:
            s.connect((ip, p))
            print("Port {0}: OPEN - {1}".format(p, ip))
        except:
            continue
        s.close()

print("Done.")
input()
