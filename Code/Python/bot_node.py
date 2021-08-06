from datetime import datetime
import socket

class Node:
    def __init__(self, node_id: int, nodes_table: list):
        self.local_ip = socket.gethostbyname(socket.gethostname())
        self.port = 2077
        self.node_id = node_id
        self.nodes_table = nodes_table
        self.birthtime = datetime.now().timestamp()

    def set_new_port(self, new_port: int):
        self.port = new_port
