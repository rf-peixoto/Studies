#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/types.h>
#include <ifaddrs.h>
#include <netdb.h>
#include <errno.h>
#include <sys/time.h>
#include <json-c/json.h>

#define BANNER "TSP_NODE"
#define PORT 5000
#define TIMEOUT 1
#define MAX_PEERS 255
#define MAX_NODES 255
#define INF 1e9

typedef struct Peer {
    char ip[INET_ADDRSTRLEN];
    double latency;
} Peer;

typedef struct Node {
    int id;
    char ip[INET_ADDRSTRLEN];
    Peer peers[MAX_PEERS];
    int peer_count;
    double adj_matrix[MAX_NODES][MAX_NODES];
    int node_count;
    char node_ips[MAX_NODES][INET_ADDRSTRLEN];
} Node;

void initialize_graph(Node *node) {
    node->node_count = 0;
    for (int i = 0; i < MAX_NODES; ++i) {
        for (int j = 0; j < MAX_NODES; ++j) {
            node->adj_matrix[i][j] = (i == j) ? 0 : INF;
        }
    }
}

int get_node_index(Node *node, const char *ip) {
    for (int i = 0; i < node->node_count; ++i) {
        if (strcmp(node->node_ips[i], ip) == 0) {
            return i;
        }
    }
    strcpy(node->node_ips[node->node_count], ip);
    return node->node_count++;
}

void add_edge(Node *node, const char *ip1, const char *ip2, double latency) {
    int idx1 = get_node_index(node, ip1);
    int idx2 = get_node_index(node, ip2);
    node->adj_matrix[idx1][idx2] = latency;
    node->adj_matrix[idx2][idx1] = latency;
}

void dijkstra(Node *node, int src, double dist[], int prev[]) {
    int n = node->node_count;
    int visited[n];
    for (int i = 0; i < n; ++i) {
        dist[i] = INF;
        visited[i] = 0;
        prev[i] = -1;
    }
    dist[src] = 0;
    for (int i = 0; i < n - 1; ++i) {
        double min_dist = INF;
        int u = -1;
        for (int j = 0; j < n; ++j) {
            if (!visited[j] && dist[j] < min_dist) {
                min_dist = dist[j];
                u = j;
            }
        }
        if (u == -1) break;
        visited[u] = 1;
        for (int v = 0; v < n; ++v) {
            if (!visited[v] && node->adj_matrix[u][v] != INF && dist[u] + node->adj_matrix[u][v] < dist[v]) {
                dist[v] = dist[u] + node->adj_matrix[u][v];
                prev[v] = u;
            }
        }
    }
}

void print_path(int prev[], int j) {
    if (prev[j] == -1) return;
    print_path(prev, prev[j]);
    printf(" -> %d", j);
}

void* handle_client(void* arg) {
    int client_socket = *((int*)arg);
    send(client_socket, BANNER, strlen(BANNER), 0);
    close(client_socket);
    free(arg);
    return NULL;
}

void* start_node_server(void* arg) {
    int node_id = *((int*)arg);
    int server_socket, client_socket, *client_sock_ptr;
    struct sockaddr_in server_addr, client_addr;
    socklen_t client_addr_len = sizeof(client_addr);

    server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (server_socket == -1) {
        perror("Could not create socket");
        return NULL;
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        perror("Bind failed");
        close(server_socket);
        return NULL;
    }

    listen(server_socket, 5);
    printf("Node %d listening on port %d\n", node_id, PORT);

    while (1) {
        client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_addr_len);
        if (client_socket < 0) {
            perror("Accept failed");
            close(server_socket);
            return NULL;
        }

        client_sock_ptr = malloc(sizeof(int));
        *client_sock_ptr = client_socket;
        pthread_t client_thread;
        pthread_create(&client_thread, NULL, handle_client, (void*)client_sock_ptr);
        pthread_detach(client_thread);
    }

    close(server_socket);
    return NULL;
}

double ping(const char* host) {
    char command[64];
    snprintf(command, sizeof(command), "ping -c 1 %s", host);
    FILE* fp = popen(command, "r");
    if (fp == NULL) {
        perror("popen failed");
        return -1;
    }

    char buffer[128];
    double time_ms = -1;
    while (fgets(buffer, sizeof(buffer), fp) != NULL) {
        if (strstr(buffer, "time=")) {
            sscanf(strstr(buffer, "time="), "time=%lf", &time_ms);
            break;
        }
    }

    pclose(fp);
    return time_ms;
}

void discover_peers(Node* node) {
    for (int ip = 1; ip < 255; ++ip) {
        char target_ip[INET_ADDRSTRLEN];
        snprintf(target_ip, sizeof(target_ip), "192.168.1.%d", ip);

        int sock = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in server_addr;
        server_addr.sin_family = AF_INET;
        server_addr.sin_port = htons(PORT);
        inet_pton(AF_INET, target_ip, &server_addr.sin_addr);

        struct timeval timeout;
        timeout.tv_sec = TIMEOUT;
        timeout.tv_usec = 0;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout, sizeof(timeout));
        setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeout, sizeof(timeout));

        if (connect(sock, (struct sockaddr*)&server_addr, sizeof(server_addr)) == 0) {
            char banner[256];
            recv(sock, banner, sizeof(banner), 0);
            if (strcmp(banner, BANNER) == 0) {
                double latency = ping(target_ip);
                if (latency > 0) {
                    strcpy(node->peers[node->peer_count].ip, target_ip);
                    node->peers[node->peer_count].latency = latency;
                    node->peer_count++;
                    add_edge(node, node->ip, target_ip, latency);
                }
            }
        }

        close(sock);
    }
}

void exchange_peer_lists(Node* node) {
    for (int i = 0; i < node->peer_count; ++i) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in server_addr;
        server_addr.sin_family = AF_INET;
        server_addr.sin_port = htons(PORT);
        inet_pton(AF_INET, node->peers[i].ip, &server_addr.sin_addr);

        if (connect(sock, (struct sockaddr*)&server_addr, sizeof(server_addr)) == 0) {
            send(sock, BANNER, strlen(BANNER), 0);
            char buffer[4096];
            recv(sock, buffer, sizeof(buffer), 0);

            struct json_object *parsed_json = json_tokener_parse(buffer);
            struct json_object *peer_array = json_object_object_get(parsed_json, "peers");

            int peer_array_len = json_object_array_length(peer_array);
            for (int j = 0; j < peer_array_len; ++j) {
                struct json_object *peer_obj = json_object_array_get_idx(peer_array, j);
                const char *peer_ip = json_object_get_string(json_object_object_get(peer_obj, "ip"));
                double latency = json_object_get_double(json_object_object_get(peer_obj, "latency"));
                add_edge(node, node->peers[i].ip, peer_ip, latency);
            }

            json_object_put(parsed_json);
        }

        close(sock);
    }
}

void broadcast_message(Node* node, const char* target_ip, const char* message) {
    double dist[MAX_NODES];
    int prev[MAX_NODES];
    int src_idx = get_node_index(node, node->ip);
    int tgt_idx = get_node_index(node, target_ip);

    dijkstra(node, src_idx, dist, prev);

    if (dist[tgt_idx] == INF) {
        printf("No path from %s to %s\n", node->ip, target_ip);
        return;
    }

    printf("Message from %s to %s: %s\nPath: %d", node->ip, target_ip, message, src_idx);
    print_path(prev, tgt_idx);
    printf("\n");
}

int main() {
    int node_id = 1;
    char node_ip[] = "192.168.1.1";
    Node node = { .id = node_id, .peer_count = 0 };
    strcpy(node.ip, node_ip);
    initialize_graph(&node);

    pthread_t server_thread;
    pthread_create(&server_thread, NULL, start_node_server, (void*)&node_id);

    sleep(1);  // Allow server to start

    discover_peers(&node);
    exchange_peer_lists(&node);

    for (int i = 0; i < node.peer_count; i++) {
        printf("Discovered peer: %s with latency %.2f ms\n", node.peers[i].ip, node.peers[i].latency);
    }

    broadcast_message(&node, "192.168.1.2", "Hello, Node 2!");

    pthread_join(server_thread, NULL);

    return 0;
}
