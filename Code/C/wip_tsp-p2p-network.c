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

#define BANNER "TSP_NODE"
#define PORT 5000
#define TIMEOUT 1
#define MAX_PEERS 255

typedef struct Peer {
    char ip[INET_ADDRSTRLEN];
    double latency;
} Peer;

typedef struct Node {
    int id;
    char ip[INET_ADDRSTRLEN];
    Peer peers[MAX_PEERS];
    int peer_count;
} Node;

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
                }
            }
        }

        close(sock);
    }
}

void broadcast_message(Node* node, const char* target_ip, const char* message) {
    printf("Message from %s to %s: %s\n", node->ip, target_ip, message);
    // Implement the shortest path and message broadcast logic here
}

int main() {
    int node_id = 1;
    char node_ip[] = "192.168.1.1";
    Node node = { .id = node_id, .peer_count = 0 };
    strcpy(node.ip, node_ip);

    pthread_t server_thread;
    pthread_create(&server_thread, NULL, start_node_server, (void*)&node_id);

    sleep(1);  // Allow server to start

    discover_peers(&node);

    for (int i = 0; i < node.peer_count; i++) {
        printf("Discovered peer: %s with latency %.2f ms\n", node.peers[i].ip, node.peers[i].latency);
    }

    broadcast_message(&node, "192.168.1.2", "Hello, Node 2!");

    pthread_join(server_thread, NULL);

    return 0;
}
