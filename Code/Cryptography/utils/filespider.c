/* gcc -pthread -o filespider filespider.c */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <limits.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/syscall.h>
#include <sys/types.h>

#define NUM_THREADS 16
#define GETDENTS_BUF_SIZE (16 * 1024)
#define OUTBUF_SIZE (64 * 1024)

struct linux_dirent64 {
    ino64_t        d_ino;
    off64_t        d_off;
    unsigned short d_reclen;
    unsigned char  d_type;
    char           d_name[];
};

typedef struct task {
    char *path;
    struct task *next;
} task_t;

task_t *task_queue_head = NULL;
task_t *task_queue_tail = NULL;
pthread_mutex_t queue_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t queue_cond = PTHREAD_COND_INITIALIZER;
int pending_tasks = 0;
int stop_workers = 0;

FILE *outfile = NULL;
pthread_mutex_t file_mutex = PTHREAD_MUTEX_INITIALIZER;

/* Enqueue a directory for further scanning */
void enqueue_task(const char *path) {
    task_t *new_task = malloc(sizeof(task_t));
    if (!new_task) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    new_task->path = strdup(path);
    new_task->next = NULL;
    
    pthread_mutex_lock(&queue_mutex);
    if (task_queue_tail == NULL) {
        task_queue_head = task_queue_tail = new_task;
    } else {
        task_queue_tail->next = new_task;
        task_queue_tail = new_task;
    }
    pending_tasks++;
    pthread_cond_signal(&queue_cond);
    pthread_mutex_unlock(&queue_mutex);
}

/* Dequeue a directory task */
task_t *dequeue_task() {
    task_t *task = NULL;
    pthread_mutex_lock(&queue_mutex);
    while (task_queue_head == NULL && !stop_workers) {
        if (pending_tasks == 0) {
            stop_workers = 1;
            pthread_cond_broadcast(&queue_cond);
            break;
        }
        pthread_cond_wait(&queue_cond, &queue_mutex);
    }
    if (task_queue_head) {
        task = task_queue_head;
        task_queue_head = task_queue_head->next;
        if (task_queue_head == NULL) {
            task_queue_tail = NULL;
        }
    }
    pthread_mutex_unlock(&queue_mutex);
    return task;
}

/* Flush a thread’s local output buffer to the shared file */
void flush_output_buffer(char *buf, size_t *used) {
    if (*used == 0)
        return;
    pthread_mutex_lock(&file_mutex);
    fwrite(buf, 1, *used, outfile);
    pthread_mutex_unlock(&file_mutex);
    *used = 0;
}

/* Append a file path and a newline to the thread’s local output buffer */
void append_to_buffer(char *buf, size_t *used, const char *path) {
    size_t path_len = strlen(path);
    size_t total_needed = path_len + 1; // include newline
    if (*used + total_needed >= OUTBUF_SIZE) {
        flush_output_buffer(buf, used);
    }
    memcpy(buf + *used, path, path_len);
    *used += path_len;
    buf[(*used)++] = '\n';
}

/* Worker thread function using getdents64 and local buffering */
void *worker(void *arg) {
    (void)arg;  // Unused parameter
    char *outbuf = malloc(OUTBUF_SIZE);
    if (!outbuf) {
        perror("malloc");
        pthread_exit(NULL);
    }
    size_t outbuf_used = 0;

    while (1) {
        task_t *task = dequeue_task();
        if (task == NULL) {
            if (stop_workers)
                break;
            else
                continue;
        }
        char *current_path = task->path;
        
        int fd = open(current_path, O_RDONLY | O_DIRECTORY);
        if (fd == -1) {
            free(current_path);
            free(task);
            pthread_mutex_lock(&queue_mutex);
            pending_tasks--;
            if (pending_tasks == 0 && task_queue_head == NULL) {
                stop_workers = 1;
                pthread_cond_broadcast(&queue_cond);
            }
            pthread_mutex_unlock(&queue_mutex);
            continue;
        }

        char buf[GETDENTS_BUF_SIZE];
        int nread;
        while ((nread = syscall(SYS_getdents64, fd, buf, GETDENTS_BUF_SIZE)) > 0) {
            int bpos = 0;
            while (bpos < nread) {
                struct linux_dirent64 *d = (struct linux_dirent64 *)(buf + bpos);
                char *d_name = d->d_name;
                /* Skip "." and ".." */
                if (strcmp(d_name, ".") == 0 || strcmp(d_name, "..") == 0) {
                    bpos += d->d_reclen;
                    continue;
                }
                char full_path[PATH_MAX];
                int ret = snprintf(full_path, PATH_MAX, "%s/%s", current_path, d_name);
                if (ret < 0 || ret >= PATH_MAX) {
                    bpos += d->d_reclen;
                    continue;
                }
                
                int is_dir = 0;
                if (d->d_type == DT_DIR) {
                    is_dir = 1;
                } else if (d->d_type == DT_UNKNOWN) {
                    struct stat statbuf;
                    if (stat(full_path, &statbuf) == 0 && S_ISDIR(statbuf.st_mode))
                        is_dir = 1;
                }
                if (is_dir) {
                    enqueue_task(full_path);
                } else {
                    append_to_buffer(outbuf, &outbuf_used, full_path);
                }
                bpos += d->d_reclen;
            }
        }
        if (nread == -1) {
            perror("getdents64");
        }
        close(fd);
        free(current_path);
        free(task);
        
        pthread_mutex_lock(&queue_mutex);
        pending_tasks--;
        if (pending_tasks == 0 && task_queue_head == NULL) {
            stop_workers = 1;
            pthread_cond_broadcast(&queue_cond);
        }
        pthread_mutex_unlock(&queue_mutex);
    }
    flush_output_buffer(outbuf, &outbuf_used);
    free(outbuf);
    return NULL;
}

int main() {
    outfile = fopen("files.txt", "w");
    if (!outfile) {
        perror("fopen");
        return EXIT_FAILURE;
    }

    /* Enqueue initial directories */
    enqueue_task("/var/logs");
    enqueue_task("/var/www");
    enqueue_task("/home");
    /* enqueue_task("/tmp"); */

    /* Enqueue /root if accessible */
    int fd_root = open("/root", O_RDONLY | O_DIRECTORY);
    if (fd_root != -1) {
        close(fd_root);
        enqueue_task("/root");
    }

    pthread_t threads[NUM_THREADS];
    for (int i = 0; i < NUM_THREADS; i++) {
        if (pthread_create(&threads[i], NULL, worker, NULL) != 0) {
            perror("pthread_create");
            return EXIT_FAILURE;
        }
    }

    for (int i = 0; i < NUM_THREADS; i++) {
        pthread_join(threads[i], NULL);
    }

    fclose(outfile);
    return EXIT_SUCCESS;
}
