#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/types.h>
#include <sys/time.h>
#include <errno.h>
#include <json-c/json.h>
#include <getopt.h>

#define DEFAULT_PORT       5000
#define DEFAULT_TIMEOUT    1       // seconds
#define MAX_PEERS          255
#define MAX_NODES          255
#define INF                1e9
#define BUFFER_SIZE        4096
#define BANNER             "TSP_NODE"

// --------------------------- Data Structures ---------------------------

typedef struct {
    char ip[INET_ADDRSTRLEN];
    double latency;
} Peer;

typedef struct {
    int     id;
    char    ip[INET_ADDRSTRLEN];
    Peer    peers[MAX_PEERS];
    int     peer_count;
    double  adj_matrix[MAX_NODES][MAX_NODES];
    int     node_count;
    char    node_ips[MAX_NODES][INET_ADDRSTRLEN];
} Node;

typedef struct {
    int     client_socket;
    Node   *node;
} ClientHandlerArgs;

// --------------------------- Utility Functions -------------------------

static void initialize_graph(Node *node) {
    node->node_count = 0;
    for (int i = 0; i < MAX_NODES; ++i) {
        for (int j = 0; j < MAX_NODES; ++j) {
            node->adj_matrix[i][j] = (i == j) ? 0.0 : INF;
        }
    }
}

// Returns index of existing IP or appends new IP and returns its index
static int get_node_index(Node *node, const char *ip) {
    for (int i = 0; i < node->node_count; ++i) {
        if (strcmp(node->node_ips[i], ip) == 0) {
            return i;
        }
    }
    if (node->node_count >= MAX_NODES) {
        fprintf(stderr, "Error: node list overflow\n");
        exit(EXIT_FAILURE);
    }
    strcpy(node->node_ips[node->node_count], ip);
    return node->node_count++;
}

// Add an undirected edge between ip1 and ip2 with given latency
static void add_edge(Node *node, const char *ip1, const char *ip2, double latency) {
    int u = get_node_index(node, ip1);
    int v = get_node_index(node, ip2);
    node->adj_matrix[u][v] = latency;
    node->adj_matrix[v][u] = latency;
}

// Standard O(n^2) Dijkstra; dist[] and prev[] must be sized MAX_NODES
static void dijkstra(const Node *node, int src, double dist[], int prev[]) {
    int n = node->node_count;
    int visited[MAX_NODES] = {0};

    for (int i = 0; i < n; ++i) {
        dist[i] = INF;
        prev[i] = -1;
    }
    dist[src] = 0.0;

    for (int i = 0; i < n - 1; ++i) {
        double min_dist = INF;
        int u = -1;
        for (int j = 0; j < n; ++j) {
            if (!visited[j] && dist[j] < min_dist) {
                min_dist = dist[j];
                u = j;
            }
        }
        if (u < 0) break;
        visited[u] = 1;
        for (int v = 0; v < n; ++v) {
            double w = node->adj_matrix[u][v];
            if (!visited[v] && w < INF && dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                prev[v] = u;
            }
        }
    }
}

static void print_path(const int prev[], int j) {
    if (prev[j] != -1) {
        print_path(prev, prev[j]);
        printf(" -> %d", j);
    }
}

// --------------------------- Networking ---------------------------

// Sends the banner and then a JSON array of this node's peer list
static void* handle_client(void *arg) {
    ClientHandlerArgs *ch = arg;
    int sock = ch->client_socket;
    Node *node = ch->node;

    // 1. send banner
    if (send(sock, BANNER "\n", strlen(BANNER) + 1, 0) < 0) {
        perror("send banner");
    }

    // 2. build JSON
    struct json_object *root = json_object_new_object();
    struct json_object *j_peers = json_object_new_array();
    for (int i = 0; i < node->peer_count; ++i) {
        struct json_object *obj = json_object_new_object();
        json_object_object_add(obj, "ip",      json_object_new_string(node->peers[i].ip));
        json_object_object_add(obj, "latency", json_object_new_double(node->peers[i].latency));
        json_object_array_add(j_peers, obj);
    }
    json_object_object_add(root, "peers", j_peers);
    const char *json_str = json_object_to_json_string(root);

    // 3. send JSON
    if (send(sock, json_str, strlen(json_str), 0) < 0) {
        perror("send json");
    }

    json_object_put(root);
    close(sock);
    free(ch);
    return NULL;
}

// Listens for incoming connections, dispatches handle_client threads
static void* start_node_server(void *arg) {
    Node *node = arg;
    int server_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (server_sock < 0) {
        perror("socket");
        return NULL;
    }

    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = INADDR_ANY,
        .sin_port = htons(node->id)
    };
    if (bind(server_sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(server_sock);
        return NULL;
    }

    if (listen(server_sock, 5) < 0) {
        perror("listen");
        close(server_sock);
        return NULL;
    }

    while (1) {
        struct sockaddr_in client_addr;
        socklen_t len = sizeof(client_addr);
        int client = accept(server_sock, (struct sockaddr*)&client_addr, &len);
        if (client < 0) {
            perror("accept");
            continue;
        }
        ClientHandlerArgs *ch = malloc(sizeof(*ch));
        ch->client_socket = client;
        ch->node          = node;
        pthread_t tid;
        pthread_create(&tid, NULL, handle_client, ch);
        pthread_detach(tid);
    }
    // unreachable
    close(server_sock);
    return NULL;
}

// Issues a single system ping and parses the time= field (ms)
static double ping_host(const char *host) {
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "ping -c 1 -W %d %s", DEFAULT_TIMEOUT, host);
    FILE *fp = popen(cmd, "r");
    if (!fp) {
        perror("popen");
        return -1.0;
    }
    char line[256];
    double t = -1.0;
    while (fgets(line, sizeof(line), fp)) {
        char *p = strstr(line, "time=");
        if (p) {
            sscanf(p, "time=%lf", &t);
            break;
        }
    }
    pclose(fp);
    return t;
}

// Scans a /24 subnet, handshakes, collects latencies
static void discover_peers(Node *node, const char *subnet) {
    for (int i = 1; i < 255 && node->peer_count < MAX_PEERS; ++i) {
        char ip[INET_ADDRSTRLEN];
        snprintf(ip, sizeof(ip), "%s.%d", subnet, i);

        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) continue;
        struct sockaddr_in srv = {
            .sin_family = AF_INET,
            .sin_port   = htons(node->id)
        };
        inet_pton(AF_INET, ip, &srv.sin_addr);

        struct timeval tv = { .tv_sec = DEFAULT_TIMEOUT, .tv_usec = 0 };
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

        if (connect(sock, (struct sockaddr*)&srv, sizeof(srv)) == 0) {
            char buf[BUFFER_SIZE] = {0};
            int len = recv(sock, buf, sizeof(buf)-1, 0);
            if (len > 0 && strstr(buf, BANNER) == buf) {
                double lat = ping_host(ip);
                if (lat > 0.0) {
                    strcpy(node->peers[node->peer_count].ip, ip);
                    node->peers[node->peer_count].latency = lat;
                    node->peer_count++;
                    add_edge(node, node->ip, ip, lat);
                }
            }
        }
        close(sock);
    }
}

// Connects to each discovered peer, retrieves their peer‐list, and integrates edges
static void exchange_peer_lists(Node *node) {
    for (int i = 0; i < node->peer_count; ++i) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) continue;
        struct sockaddr_in srv = {
            .sin_family = AF_INET,
            .sin_port   = htons(node->id)
        };
        inet_pton(AF_INET, node->peers[i].ip, &srv.sin_addr);

        if (connect(sock, (struct sockaddr*)&srv, sizeof(srv)) == 0) {
            // handshake
            send(sock, BANNER "\n", strlen(BANNER) + 1, 0);
            char buf[BUFFER_SIZE] = {0};
            int len = recv(sock, buf, sizeof(buf)-1, 0);
            if (len > 0) {
                struct json_object *parsed = json_tokener_parse(buf);
                struct json_object *arr    = json_object_object_get(parsed, "peers");
                if (arr && json_object_is_type(arr, json_type_array)) {
                    int n = json_object_array_length(arr);
                    for (int j = 0; j < n; ++j) {
                        struct json_object *o = json_object_array_get_idx(arr, j);
                        const char *peer_ip = json_object_get_string(
                            json_object_object_get(o, "ip"));
                        double      lat     = json_object_get_double(
                            json_object_object_get(o, "latency"));
                        add_edge(node, node->peers[i].ip, peer_ip, lat);
                    }
                }
                json_object_put(parsed);
            }
        }
        close(sock);
    }
}

// Computes shortest path from local node to target_ip and prints it
static void broadcast_message(Node *node, const char *target_ip, const char *msg) {
    int src = get_node_index(node, node->ip);
    int tgt = get_node_index(node, target_ip);
    double dist[MAX_NODES];
    int    prev[MAX_NODES];

    dijkstra(node, src, dist, prev);
    if (dist[tgt] >= INF) {
        printf("No path from %s to %s\n", node->ip, target_ip);
        return;
    }

    printf("Message from %s to %s: %s\nPath: %d", node->ip, target_ip, msg, src);
    print_path(prev, tgt);
    printf("\nTotal latency: %.2f ms\n", dist[tgt]);
}

// --------------------------- Main & CLI ---------------------------

int main(int argc, char **argv) {
    Node node = { .id = DEFAULT_PORT, .peer_count = 0 };
    char subnet_prefix[32] = "192.168.1";
    char target_ip[INET_ADDRSTRLEN] = "192.168.1.2";
    char message[256] = "Hello, Node 2!";

    int opt;
    while ((opt = getopt(argc, argv, "p:s:t:m:")) != -1) {
        switch (opt) {
            case 'p': node.id = atoi(optarg);          break;
            case 's': strncpy(subnet_prefix, optarg, sizeof(subnet_prefix)-1); break;
            case 't': strncpy(target_ip,   optarg, INET_ADDRSTRLEN-1);         break;
            case 'm': strncpy(message,     optarg, sizeof(message)-1);         break;
            default:
                fprintf(stderr,
                    "Usage: %s [-p port] [-s subnet_prefix] [-t target_ip] [-m message]\n",
                    argv[0]);
                exit(EXIT_FAILURE);
        }
    }

    // set local IP = subnet_prefix . ".1"
    snprintf(node.ip, INET_ADDRSTRLEN, "%s.1", subnet_prefix);

    initialize_graph(&node);
    // include self in graph
    get_node_index(&node, node.ip);

    pthread_t server_thread;
    pthread_create(&server_thread, NULL, start_node_server, &node);
    sleep(1);  // allow accept loop to start

    discover_peers(&node, subnet_prefix);
    exchange_peer_lists(&node);

    for (int i = 0; i < node.peer_count; ++i) {
        printf("Discovered peer: %s (%.2f ms)\n",
               node.peers[i].ip, node.peers[i].latency);
    }

    broadcast_message(&node, target_ip, message);

    pthread_join(server_thread, NULL);
    return 0;
}
