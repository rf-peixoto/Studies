import socket
from time import sleep
from base64 import b64decode

class Node:

    def __init__(self):
        self.node_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host_name = socket.gethostname()
        self.node_socket.connect((self.host_name, 7890))
        self.start()

    def run(self, command):
        try:
            exec(b64decode(command))
            return True
        except Exception as error:
            print(error)
            return False

    def start(self):
        print("Listen on {0}:7890".format(self.host_name))
        while True:
            sleep(5)
            task = self.node_socket.recv(1024)
            if self.run(task):
                pass
                #self.node_socket.send("200".encode("ascii"))
            else:
                pass
                #self.node_socket.send("500".encode("ascii"))


if __name__ == "__main__":
    node = Node()
    node.start()
