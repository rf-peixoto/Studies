import socket
import threading
import subprocess
import time
import networkx as nx

BANNER = "TSP_NODE"
PORT = 5000
TIMEOUT = 1

def start_node_server(node_id):
    def handle_client(client_socket):
        client_socket.send(BANNER.encode())
        client_socket.close()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", PORT))
    server.listen(5)

    print(f"Node {node_id} listening on port {PORT}")
    while True:
        client, addr = server.accept()
        client_handler = threading.Thread(target=handle_client, args=(client,))
        client_handler.start()

def discover_peers():
    peers = []
    for ip in range(1, 255):
        target_ip = f"192.168.1.{ip}"
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(TIMEOUT)
            client.connect((target_ip, PORT))
            banner = client.recv(1024).decode()
            if banner == BANNER:
                latency = ping(target_ip)
                if latency:
                    peers.append((target_ip, latency))
            client.close()
        except (socket.timeout, ConnectionRefusedError):
            continue
    return peers

def ping(host):
    try:
        output = subprocess.check_output(["ping", "-c", "1", host], universal_newlines=True)
        time_ms = float(output.split("time=")[1].split(" ms")[0])
        return time_ms
    except Exception as e:
        print(f"Ping to {host} failed: {e}")
        return None

class Node:
    def __init__(self, id, ip):
        self.id = id
        self.ip = ip
        self.peers = {}
        self.network_map = nx.Graph()

    def add_peer(self, peer_ip, latency):
        self.peers[peer_ip] = latency
        self.network_map.add_edge(self.ip, peer_ip, weight=latency)

    def discover_peers(self):
        discovered_peers = discover_peers()
        for peer_ip, latency in discovered_peers:
            self.add_peer(peer_ip, latency)

    def exchange_peer_lists(self):
        for peer_ip in self.peers:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect((peer_ip, PORT))
                banner = client.recv(1024).decode()
                if banner == BANNER:
                    client.send(str(self.peers).encode())
                    peer_data = client.recv(4096).decode()
                    peer_list = eval(peer_data)
                    for other_peer_ip, other_latency in peer_list.items():
                        if other_peer_ip != self.ip:
                            self.network_map.add_edge(peer_ip, other_peer_ip, weight=other_latency)
                client.close()
            except Exception as e:
                print(f"Failed to exchange peers with {peer_ip}: {e}")

    def update_network_map(self):
        self.exchange_peer_lists()

    def shortest_path(self, target_ip):
        return nx.shortest_path(self.network_map, source=self.ip, target=target_ip, weight='weight')

    def broadcast_message(self, target_ip, message):
        path = self.shortest_path(target_ip)
        print(f"Message from {self.ip} to {target_ip} via {path}: {message}")

# Start node server
node_id = 1  # Unique identifier for this node
node_ip = "192.168.1.1"  # IP address of this node
node = Node(node_id, node_ip)
server_thread = threading.Thread(target=start_node_server, args=(node_id,))
server_thread.start()

# Discover peers and build initial network map
node.discover_peers()
node.update_network_map()

# Node 1 broadcasts a message to another node
target_ip = "192.168.1.2"  # Example target IP
node.broadcast_message(target_ip, "Hello, Node 2!")
