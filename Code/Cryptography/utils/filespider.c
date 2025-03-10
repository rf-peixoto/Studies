/* gcc -pthread -o filespider filespider.c */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <limits.h>
#include <errno.h>

#define NUM_THREADS 8

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

/* Enqueue a new directory path for processing */
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

/* Write a file or directory absolute path to the output file */
void write_path(const char *path) {
    pthread_mutex_lock(&file_mutex);
    fprintf(outfile, "%s\n", path);
    pthread_mutex_unlock(&file_mutex);
}

/* Worker thread function: process a directory, write paths, and enqueue subdirectories */
void *worker(void *arg) {
    (void)arg;  // Unused parameter
    while (1) {
        task_t *task = dequeue_task();
        if (task == NULL) {
            if (stop_workers)
                break;
            else
                continue;
        }
        char *current_path = task->path;
        /* Write the directory itself */
        write_path(current_path);

        DIR *dir = opendir(current_path);
        if (dir) {
            struct dirent *entry;
            while ((entry = readdir(dir)) != NULL) {
                if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
                    continue;

                char full_path[PATH_MAX];
                snprintf(full_path, PATH_MAX, "%s/%s", current_path, entry->d_name);
                write_path(full_path);

                int is_dir = 0;
                if (entry->d_type == DT_DIR) {
                    is_dir = 1;
                } else if (entry->d_type == DT_UNKNOWN) {
                    struct stat statbuf;
                    if (stat(full_path, &statbuf) == 0 && S_ISDIR(statbuf.st_mode))
                        is_dir = 1;
                }
                if (is_dir) {
                    enqueue_task(full_path);
                }
            }
            closedir(dir);
        }
        /* Free memory for the processed task */
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
    return NULL;
}

int main() {
    outfile = fopen("files.txt", "w");
    if (!outfile) {
        perror("fopen");
        return EXIT_FAILURE;
    }

    /* Enqueue initial directories */
    enqueue_task("/var");
    enqueue_task("/home");
    enqueue_task("/tmp");

    /* Enqueue /root if accessible */
    DIR *root_dir = opendir("/root");
    if (root_dir) {
        closedir(root_dir);
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
