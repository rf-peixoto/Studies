import networkx as nx
import heapq

class Node:
    def __init__(self, id, position):
        self.id = id
        self.position = position
        self.peers = {}
        self.network_map = nx.Graph()

    def add_peer(self, peer, distance):
        self.peers[peer.id] = (peer, distance)
        self.network_map.add_edge(self.id, peer.id, weight=distance)

    def discover_peers(self, all_nodes):
        for node in all_nodes:
            if node.id != self.id:
                distance = self.calculate_distance(node)
                self.add_peer(node, distance)
                node.add_peer(self, distance)

    def calculate_distance(self, other_node):
        # Example distance calculation (Euclidean distance)
        return ((self.position[0] - other_node.position[0]) ** 2 + (self.position[1] - other_node.position[1]) ** 2) ** 0.5

    def exchange_peer_lists(self):
        for peer_id, (peer, distance) in self.peers.items():
            for other_peer_id, (other_peer, other_distance) in peer.peers.items():
                if other_peer_id != self.id:
                    self.network_map.add_edge(peer_id, other_peer_id, weight=other_distance)

    def update_network_map(self):
        for peer_id, (peer, distance) in self.peers.items():
            peer.exchange_peer_lists()
            self.exchange_peer_lists()

    def shortest_path(self, target_id):
        return nx.shortest_path(self.network_map, source=self.id, target=target_id, weight='weight')

    def broadcast_message(self, target_id, message):
        path = self.shortest_path(target_id)
        print(f"Message from {self.id} to {target_id} via {path}: {message}")

# Example usage
nodes = [
    Node(0, (0, 0)),
    Node(1, (1, 2)),
    Node(2, (4, 5)),
    Node(3, (7, 8)),
    Node(4, (10, 1))
]

# Discover peers and build initial network map
for node in nodes:
    node.discover_peers(nodes)

# Update network map with exchanged peer lists
for node in nodes:
    node.update_network_map()

# Node 0 broadcasts a message to Node 3
nodes[0].broadcast_message(3, "Hello, Node 3!")
