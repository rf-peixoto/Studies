/* aes256_ctr_auth_bitsliced.c */
/* Compile with: gcc -O2 -lpthread -o wip_aes256_bitsliced wip_aes256_bitsliced.c */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/random.h>
#include <pthread.h>
#include <errno.h>

// ---------------------------------------------------------------------------
// Configuration Macros
// ---------------------------------------------------------------------------
#define AES_BLOCK_SIZE 16       // 128-bit block
#define AES_KEY_SIZE 32         // 256-bit key (32 bytes)
#define AES_ROUNDS 14           // For AES-256, 14 rounds
#define EXPANDED_KEY_SIZE ((AES_ROUNDS+1) * AES_BLOCK_SIZE)  // 15 round keys (15*16 = 240 bytes)
#define CTR_BLOCK_SIZE 4096     // I/O buffer block size
#define NUM_THREADS 4           // Number of threads for parallel processing

// ---------------------------------------------------------------------------
// Function prototypes for AES (bitsliced/constant–time style)
// ---------------------------------------------------------------------------
static uint8_t gf_mul(uint8_t a, uint8_t b);
static uint8_t aes_inv(uint8_t a);
static uint8_t aes_sbox(uint8_t a);
static void SubBytes(uint8_t state[16]);
static void ShiftRows(uint8_t state[16]);
static void MixColumns(uint8_t state[16]);
static void AddRoundKey(uint8_t state[16], const uint8_t roundKey[16]);

void AES256_Encrypt_Block(const uint8_t in[16], uint8_t out[16], const uint8_t roundKeys[EXPANDED_KEY_SIZE]);
void AES256_KeyExpansion(const uint8_t key[AES_KEY_SIZE], uint8_t roundKeys[EXPANDED_KEY_SIZE]);

// ---------------------------------------------------------------------------
// Function prototypes for SHA256 and HMAC-SHA256 (minimal implementations)
// ---------------------------------------------------------------------------
void sha256(const uint8_t *data, size_t len, uint8_t hash[32]);
void hmac_sha256(const uint8_t *key, size_t keylen,
                 const uint8_t *data, size_t datalen,
                 uint8_t mac[32]);

// ---------------------------------------------------------------------------
// Secure memory and randomness functions
// ---------------------------------------------------------------------------
int secure_lock(void *ptr, size_t len);
void secure_clear(void *v, size_t n);
int get_random_bytes(uint8_t *buf, size_t len);

// ---------------------------------------------------------------------------
// Parallel CTR mode processing data structures and functions
// ---------------------------------------------------------------------------
typedef struct {
    uint8_t *in;              // Pointer to input data (already in memory)
    uint8_t *out;             // Pointer to output buffer
    size_t start_block;       // Global starting block index for this thread
    size_t num_blocks;        // Number of 16-byte blocks to process
    uint8_t iv[16];           // Initialization vector (counter seed)
    const uint8_t *roundKeys; // Expanded AES round keys
} thread_arg_t;

void *process_chunk(void *arg);
void add_counter(uint8_t counter[16], uint64_t value);

// ---------------------------------------------------------------------------
// File processing and key derivation prototypes
// ---------------------------------------------------------------------------
int process_file(const char *input_path, const char *output_path, const char *mode,
                 const uint8_t roundKeys[EXPANDED_KEY_SIZE], const uint8_t hmac_key[32]);
void derive_hmac_key(const uint8_t enc_key[AES_KEY_SIZE], uint8_t hmac_key[32]);

// ==================== AES Implementation ====================

// Multiply two elements in GF(2^8) using the AES irreducible polynomial.
static uint8_t gf_mul(uint8_t a, uint8_t b) {
    uint8_t p = 0;
    for (int i = 0; i < 8; i++) {
        if (b & 1)
            p ^= a;
        uint8_t hi = a & 0x80;
        a <<= 1;
        if (hi)
            a ^= 0x1b; // AES polynomial: x^8 + x^4 + x^3 + x + 1
        b >>= 1;
    }
    return p;
}

// Compute multiplicative inverse in GF(2^8) via exponentiation (constant time).
static uint8_t aes_inv(uint8_t a) {
    if (a == 0) return 0;
    uint8_t x2 = gf_mul(a, a);
    uint8_t x4 = gf_mul(x2, x2);
    uint8_t x8 = gf_mul(x4, x4);
    uint8_t x16 = gf_mul(x8, x8);
    uint8_t x32 = gf_mul(x16, x16);
    uint8_t x64 = gf_mul(x32, x32);
    uint8_t x128 = gf_mul(x64, x64);
    // a^(254) = a^(128+64+32+16+8+4+2)
    uint8_t inv = gf_mul(x128, gf_mul(x64, gf_mul(x32, gf_mul(x16, gf_mul(x8, gf_mul(x4, x2))))));
    return inv;
}

// Compute the AES S-box in constant time (avoiding lookup tables).
static uint8_t aes_sbox(uint8_t a) {
    uint8_t inv = aes_inv(a);
    // Apply affine transformation:
    uint8_t r1 = (inv << 1) | (inv >> 7);
    uint8_t r2 = (inv << 2) | (inv >> 6);
    uint8_t r3 = (inv << 3) | (inv >> 5);
    uint8_t r4 = (inv << 4) | (inv >> 4);
    uint8_t s = inv ^ r1 ^ r2 ^ r3 ^ r4 ^ 0x63;
    return s;
}

static void SubBytes(uint8_t state[16]) {
    for (int i = 0; i < 16; i++) {
        state[i] = aes_sbox(state[i]);
    }
}

static void ShiftRows(uint8_t state[16]) {
    uint8_t temp[16];
    memcpy(temp, state, 16);
    // Row 0 (indices 0,4,8,12): no shift.
    state[0] = temp[0];
    state[4] = temp[4];
    state[8] = temp[8];
    state[12] = temp[12];
    // Row 1: shift left by 1.
    state[1] = temp[5];
    state[5] = temp[9];
    state[9] = temp[13];
    state[13] = temp[1];
    // Row 2: shift left by 2.
    state[2] = temp[10];
    state[6] = temp[14];
    state[10] = temp[2];
    state[14] = temp[6];
    // Row 3: shift left by 3.
    state[3] = temp[15];
    state[7] = temp[3];
    state[11] = temp[7];
    state[15] = temp[11];
}

static void MixColumns(uint8_t state[16]) {
    for (int i = 0; i < 4; i++) {
        int col = i * 4;
        uint8_t a0 = state[col];
        uint8_t a1 = state[col+1];
        uint8_t a2 = state[col+2];
        uint8_t a3 = state[col+3];
        uint8_t r0 = gf_mul(a0,2) ^ gf_mul(a1,3) ^ a2 ^ a3;
        uint8_t r1 = a0 ^ gf_mul(a1,2) ^ gf_mul(a2,3) ^ a3;
        uint8_t r2 = a0 ^ a1 ^ gf_mul(a2,2) ^ gf_mul(a3,3);
        uint8_t r3 = gf_mul(a0,3) ^ a1 ^ a2 ^ gf_mul(a3,2);
        state[col] = r0;
        state[col+1] = r1;
        state[col+2] = r2;
        state[col+3] = r3;
    }
}

static void AddRoundKey(uint8_t state[16], const uint8_t roundKey[16]) {
    for (int i = 0; i < 16; i++) {
        state[i] ^= roundKey[i];
    }
}

// Encrypt one 16-byte block using AES-256 (constant–time, no T–tables)
void AES256_Encrypt_Block(const uint8_t in[16], uint8_t out[16], const uint8_t roundKeys[EXPANDED_KEY_SIZE]) {
    uint8_t state[16];
    memcpy(state, in, 16);
    AddRoundKey(state, roundKeys);
    for (int round = 1; round < AES_ROUNDS; round++) {
        SubBytes(state);
        ShiftRows(state);
        MixColumns(state);
        AddRoundKey(state, roundKeys + round * 16);
    }
    // Final round (without MixColumns)
    SubBytes(state);
    ShiftRows(state);
    AddRoundKey(state, roundKeys + AES_ROUNDS * 16);
    memcpy(out, state, 16);
}

// Expand the 256-bit key into the round keys (using constant–time S-box)
void AES256_KeyExpansion(const uint8_t key[AES_KEY_SIZE], uint8_t roundKeys[EXPANDED_KEY_SIZE]) {
    uint32_t temp;
    uint32_t *w = (uint32_t *)roundKeys;
    int i;
    // Copy original key (256 bits = 8 words)
    for (i = 0; i < 8; i++) {
        w[i] = ((uint32_t)key[4*i] << 24) | ((uint32_t)key[4*i+1] << 16) |
               ((uint32_t)key[4*i+2] << 8) | key[4*i+3];
    }
    // Rcon values (for AES-256, 7 rounds are needed)
    uint32_t Rcon[7] = {0x01000000,0x02000000,0x04000000,0x08000000,
                        0x10000000,0x20000000,0x40000000};
    for (i = 8; i < 4 * (AES_ROUNDS + 1); i++) {
        temp = w[i - 1];
        if (i % 8 == 0) {
            // RotWord and SubWord
            temp = (temp << 8) | (temp >> 24);
            temp = ((uint32_t)aes_sbox(temp >> 24) << 24) |
                   ((uint32_t)aes_sbox((temp >> 16) & 0xff) << 16) |
                   ((uint32_t)aes_sbox((temp >> 8) & 0xff) << 8) |
                   ((uint32_t)aes_sbox(temp & 0xff));
            temp ^= Rcon[(i/8) - 1];
        } else if (i % 8 == 4) {
            // SubWord only
            temp = ((uint32_t)aes_sbox(temp >> 24) << 24) |
                   ((uint32_t)aes_sbox((temp >> 16) & 0xff) << 16) |
                   ((uint32_t)aes_sbox((temp >> 8) & 0xff) << 8) |
                   ((uint32_t)aes_sbox(temp & 0xff));
        }
        w[i] = w[i - 8] ^ temp;
    }
}

// ==================== Minimal SHA256 and HMAC-SHA256 ====================

/* This minimal SHA256 implementation is based on public domain code. */

typedef struct {
    uint32_t state[8];
    uint64_t bitlen;
    uint8_t data[64];
    uint32_t datalen;
} SHA256_CTX;

#define SHA256_K { \
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5, \
    0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5, \
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3, \
    0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174, \
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc, \
    0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da, \
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7, \
    0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967, \
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13, \
    0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85, \
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3, \
    0xd192e819,0xd6990624,0xf40e3585,0x106aa070, \
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5, \
    0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3, \
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208, \
    0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2  \
}

static const uint32_t K[64] = SHA256_K;

static void sha256_transform(SHA256_CTX *ctx, const uint8_t data[]) {
    uint32_t a,b,c,d,e,f,g,h,t1,t2;
    uint32_t m[64];
    int i,j;
    for(i=0,j=0; i < 16; ++i, j+=4)
        m[i] = (data[j] << 24) | (data[j+1] << 16) | (data[j+2] << 8) | (data[j+3]);
    for(; i < 64; ++i) {
        uint32_t s0 = ((m[i-15] >> 7) | (m[i-15] << (32-7))) ^
                      ((m[i-15] >> 18) | (m[i-15] << (32-18))) ^
                      (m[i-15] >> 3);
        uint32_t s1 = ((m[i-2] >> 17) | (m[i-2] << (32-17))) ^
                      ((m[i-2] >> 19) | (m[i-2] << (32-19))) ^
                      (m[i-2] >> 10);
        m[i] = m[i-16] + s0 + m[i-7] + s1;
    }
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];
    for(i=0; i < 64; ++i) {
        uint32_t S1 = ((e >> 6) | (e << (32-6))) ^
                      ((e >> 11) | (e << (32-11))) ^
                      ((e >> 25) | (e << (32-25)));
        t1 = h + S1 + ((e & f) ^ ((~e) & g)) + K[i] + m[i];
        uint32_t S0 = ((a >> 2) | (a << (32-2))) ^
                      ((a >> 13) | (a << (32-13))) ^
                      ((a >> 22) | (a << (32-22)));
        t2 = S0 + ((a & b) ^ (a & c) ^ (b & c));
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sha256_init(SHA256_CTX *ctx) {
    ctx->datalen = 0;
    ctx->bitlen = 0;
    ctx->state[0] = 0x6a09e667;
    ctx->state[1] = 0xbb67ae85;
    ctx->state[2] = 0x3c6ef372;
    ctx->state[3] = 0xa54ff53a;
    ctx->state[4] = 0x510e527f;
    ctx->state[5] = 0x9b05688c;
    ctx->state[6] = 0x1f83d9ab;
    ctx->state[7] = 0x5be0cd19;
}

static void sha256_update(SHA256_CTX *ctx, const uint8_t data[], size_t len) {
    for (size_t i=0; i < len; i++) {
        ctx->data[ctx->datalen] = data[i];
        ctx->datalen++;
        if(ctx->datalen == 64) {
            sha256_transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

static void sha256_final(SHA256_CTX *ctx, uint8_t hash[32]) {
    uint32_t i = ctx->datalen;
    if(ctx->datalen < 56) {
        ctx->data[i++] = 0x80;
        while(i < 56)
            ctx->data[i++] = 0x00;
    } else {
        ctx->data[i++] = 0x80;
        while(i < 64)
            ctx->data[i++] = 0x00;
        sha256_transform(ctx, ctx->data);
        memset(ctx->data, 0, 56);
    }
    ctx->bitlen += ctx->datalen * 8;
    ctx->data[63] = ctx->bitlen;
    ctx->data[62] = ctx->bitlen >> 8;
    ctx->data[61] = ctx->bitlen >> 16;
    ctx->data[60] = ctx->bitlen >> 24;
    ctx->data[59] = ctx->bitlen >> 32;
    ctx->data[58] = ctx->bitlen >> 40;
    ctx->data[57] = ctx->bitlen >> 48;
    ctx->data[56] = ctx->bitlen >> 56;
    sha256_transform(ctx, ctx->data);
    for(i = 0; i < 4; i++) {
        hash[i]      = (ctx->state[0] >> (24 - i * 8)) & 0xff;
        hash[i + 4]  = (ctx->state[1] >> (24 - i * 8)) & 0xff;
        hash[i + 8]  = (ctx->state[2] >> (24 - i * 8)) & 0xff;
        hash[i + 12] = (ctx->state[3] >> (24 - i * 8)) & 0xff;
        hash[i + 16] = (ctx->state[4] >> (24 - i * 8)) & 0xff;
        hash[i + 20] = (ctx->state[5] >> (24 - i * 8)) & 0xff;
        hash[i + 24] = (ctx->state[6] >> (24 - i * 8)) & 0xff;
        hash[i + 28] = (ctx->state[7] >> (24 - i * 8)) & 0xff;
    }
}

void sha256(const uint8_t *data, size_t len, uint8_t hash[32]) {
    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, hash);
}

void hmac_sha256(const uint8_t *key, size_t keylen,
                 const uint8_t *data, size_t datalen,
                 uint8_t mac[32]) {
    uint8_t k_ipad[64] = {0};
    uint8_t k_opad[64] = {0};
    uint8_t tk[32];
    if (keylen > 64) {
        sha256(key, keylen, tk);
        key = tk;
        keylen = 32;
    }
    memcpy(k_ipad, key, keylen);
    memcpy(k_opad, key, keylen);
    for (int i = 0; i < 64; i++) {
        k_ipad[i] ^= 0x36;
        k_opad[i] ^= 0x5c;
    }
    uint8_t inner_hash[32];
    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, k_ipad, 64);
    sha256_update(&ctx, data, datalen);
    sha256_final(&ctx, inner_hash);
    sha256_init(&ctx);
    sha256_update(&ctx, k_opad, 64);
    sha256_update(&ctx, inner_hash, 32);
    sha256_final(&ctx, mac);
}

// ==================== Secure Memory and Random Bytes ====================
int secure_lock(void *ptr, size_t len) {
    return mlock(ptr, len);
}

void secure_clear(void *v, size_t n) {
    volatile unsigned char *p = v;
    while(n--) *p++ = 0;
}

int get_random_bytes(uint8_t *buf, size_t len) {
    ssize_t ret = getrandom(buf, len, 0);
    return (ret == (ssize_t)len) ? 0 : -1;
}

// ==================== Parallel CTR Mode Processing ====================

// Add a 64-bit value to the last 8 bytes of the counter (big-endian).
void add_counter(uint8_t counter[16], uint64_t value) {
    for (int i = 15; i >= 8; i--) {
        uint64_t sum = counter[i] + (value & 0xff);
        counter[i] = sum & 0xff;
        value >>= 8;
    }
}

void *process_chunk(void *arg) {
    thread_arg_t *targ = (thread_arg_t *)arg;
    for (size_t block = 0; block < targ->num_blocks; block++) {
        uint8_t counter[16];
        memcpy(counter, targ->iv, 16);
        add_counter(counter, targ->start_block + block);
        uint8_t keystream[16];
        AES256_Encrypt_Block(counter, keystream, targ->roundKeys);
        uint8_t *in_block = targ->in + block * AES_BLOCK_SIZE;
        uint8_t *out_block = targ->out + block * AES_BLOCK_SIZE;
        for (int i = 0; i < AES_BLOCK_SIZE; i++) {
            out_block[i] = in_block[i] ^ keystream[i];
        }
    }
    return NULL;
}

// ==================== Key Derivation ====================

// Derive a separate 256-bit HMAC key by hashing "HMAC" concatenated with the encryption key.
void derive_hmac_key(const uint8_t enc_key[AES_KEY_SIZE], uint8_t hmac_key[32]) {
    const char *prefix = "HMAC";
    size_t prefix_len = strlen(prefix);
    uint8_t buf[64];
    memcpy(buf, prefix, prefix_len);
    memcpy(buf + prefix_len, enc_key, AES_KEY_SIZE);
    sha256(buf, prefix_len + AES_KEY_SIZE, hmac_key);
}

// ==================== File Processing ====================

int process_file(const char *input_path, const char *output_path, const char *mode,
                 const uint8_t roundKeys[EXPANDED_KEY_SIZE], const uint8_t hmac_key[32]) {
    FILE *fin = fopen(input_path, "rb");
    if (!fin) {
        fprintf(stderr, "Error: Cannot open input file: %s\n", input_path);
        return -1;
    }
    FILE *fout = fopen(output_path, "wb");
    if (!fout) {
        fprintf(stderr, "Error: Cannot open output file: %s\n", output_path);
        fclose(fin);
        return -1;
    }
    uint8_t iv[AES_BLOCK_SIZE];
    if (strcmp(mode, "encryption") == 0) {
        if (get_random_bytes(iv, AES_BLOCK_SIZE) != 0) {
            fclose(fin); fclose(fout);
            return -1;
        }
        if (fwrite(iv, 1, AES_BLOCK_SIZE, fout) != AES_BLOCK_SIZE) {
            fclose(fin); fclose(fout);
            return -1;
        }
    } else { // decryption – read IV from file
        if (fread(iv, 1, AES_BLOCK_SIZE, fin) != AES_BLOCK_SIZE) {
            fclose(fin); fclose(fout);
            return -1;
        }
    }
    // For simplicity, load entire file into memory.
    fseek(fin, 0, SEEK_END);
    long fsize = ftell(fin);
    fseek(fin, 0, SEEK_SET);
    uint8_t *in_buf = malloc(fsize);
    if (!in_buf) { fclose(fin); fclose(fout); return -1; }
    if (fread(in_buf, 1, fsize, fin) != (size_t)fsize) {
        free(in_buf); fclose(fin); fclose(fout);
        return -1;
    }
    fclose(fin);
    // Determine number of AES blocks (pad to a multiple of 16 if needed)
    size_t num_blocks = (fsize + AES_BLOCK_SIZE - 1) / AES_BLOCK_SIZE;
    size_t buf_size = num_blocks * AES_BLOCK_SIZE;
    uint8_t *in_data = calloc(buf_size, 1);
    uint8_t *out_data = malloc(buf_size);
    if (!in_data || !out_data) {
        free(in_buf); if(in_data) free(in_data); fclose(fout);
        return -1;
    }
    memcpy(in_data, in_buf, fsize);
    free(in_buf);
    // Divide blocks among threads.
    pthread_t threads[NUM_THREADS];
    thread_arg_t targs[NUM_THREADS];
    size_t blocks_per_thread = num_blocks / NUM_THREADS;
    size_t remaining = num_blocks % NUM_THREADS;
    size_t current_block = 0;
    for (int i = 0; i < NUM_THREADS; i++) {
        targs[i].in = in_data + current_block * AES_BLOCK_SIZE;
        targs[i].out = out_data + current_block * AES_BLOCK_SIZE;
        targs[i].start_block = current_block;
        targs[i].num_blocks = blocks_per_thread + (i < remaining ? 1 : 0);
        memcpy(targs[i].iv, iv, AES_BLOCK_SIZE);
        targs[i].roundKeys = roundKeys;
        current_block += targs[i].num_blocks;
        if (pthread_create(&threads[i], NULL, process_chunk, &targs[i]) != 0) {
            free(in_data); free(out_data); fclose(fout);
            return -1;
        }
    }
    for (int i = 0; i < NUM_THREADS; i++) {
        pthread_join(threads[i], NULL);
    }
    // Write (encrypted or decrypted) data.
    if (fwrite(out_data, 1, buf_size, fout) != buf_size) {
        free(in_data); free(out_data); fclose(fout);
        return -1;
    }
    // For encryption, compute and append HMAC over the ciphertext.
    if (strcmp(mode, "encryption") == 0) {
        uint8_t mac[32];
        hmac_sha256(hmac_key, 32, out_data, buf_size, mac);
        if (fwrite(mac, 1, 32, fout) != 32) {
            free(in_data); free(out_data); fclose(fout);
            return -1;
        }
    }
    free(in_data);
    free(out_data);
    fclose(fout);
    return 0;
}/* aes256_ctr_auth_bitsliced.c */
/* Compile with: gcc -O2 -lpthread -o wip_aes256_bitsliced wip_aes256_bitsliced.c */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/random.h>
#include <pthread.h>
#include <errno.h>

// ---------------------------------------------------------------------------
// Configuration Macros
// ---------------------------------------------------------------------------
#define AES_BLOCK_SIZE 16       // 128-bit block
#define AES_KEY_SIZE 32         // 256-bit key (32 bytes)
#define AES_ROUNDS 14           // For AES-256, 14 rounds
#define EXPANDED_KEY_SIZE ((AES_ROUNDS+1) * AES_BLOCK_SIZE)  // 15 round keys (15*16 = 240 bytes)
#define CTR_BLOCK_SIZE 4096     // I/O buffer block size

// ---------------------------------------------------------------------------
// Function prototypes for AES (bitsliced/constant–time style)
// ---------------------------------------------------------------------------
static uint8_t gf_mul(uint8_t a, uint8_t b);
static uint8_t aes_inv(uint8_t a);
static uint8_t aes_sbox(uint8_t a);
static void SubBytes(uint8_t state[16]);
static void ShiftRows(uint8_t state[16]);
static void MixColumns(uint8_t state[16]);
static void AddRoundKey(uint8_t state[16], const uint8_t roundKey[16]);

void AES256_Encrypt_Block(const uint8_t in[16], uint8_t out[16], const uint8_t roundKeys[EXPANDED_KEY_SIZE]);
void AES256_KeyExpansion(const uint8_t key[AES_KEY_SIZE], uint8_t roundKeys[EXPANDED_KEY_SIZE]);

// ---------------------------------------------------------------------------
// Function prototypes for SHA256 and HMAC-SHA256 (minimal implementations)
// ---------------------------------------------------------------------------
void sha256(const uint8_t *data, size_t len, uint8_t hash[32]);

// Minimal SHA256 implementation context and functions.
typedef struct {
    uint32_t state[8];
    uint64_t bitlen;
    uint8_t data[64];
    uint32_t datalen;
} SHA256_CTX;

#define SHA256_K { \
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5, \
    0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5, \
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3, \
    0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174, \
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc, \
    0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da, \
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7, \
    0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967, \
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13, \
    0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85, \
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3, \
    0xd192e819,0xd6990624,0xf40e3585,0x106aa070, \
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5, \
    0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3, \
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208, \
    0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2  \
}

static const uint32_t K[64] = SHA256_K;

static void sha256_transform(SHA256_CTX *ctx, const uint8_t data[]) {
    uint32_t a,b,c,d,e,f,g,h,t1,t2;
    uint32_t m[64];
    int i,j;
    for(i=0,j=0; i < 16; ++i, j+=4)
        m[i] = (data[j] << 24) | (data[j+1] << 16) | (data[j+2] << 8) | (data[j+3]);
    for(; i < 64; ++i) {
        uint32_t s0 = ((m[i-15] >> 7) | (m[i-15] << (32-7))) ^
                      ((m[i-15] >> 18) | (m[i-15] << (32-18))) ^
                      (m[i-15] >> 3);
        uint32_t s1 = ((m[i-2] >> 17) | (m[i-2] << (32-17))) ^
                      ((m[i-2] >> 19) | (m[i-2] << (32-19))) ^
                      (m[i-2] >> 10);
        m[i] = m[i-16] + s0 + m[i-7] + s1;
    }
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];
    for(i=0; i < 64; ++i) {
        uint32_t S1 = ((e >> 6) | (e << (32-6))) ^
                      ((e >> 11) | (e << (32-11))) ^
                      ((e >> 25) | (e << (32-25)));
        t1 = h + S1 + ((e & f) ^ ((~e) & g)) + K[i] + m[i];
        uint32_t S0 = ((a >> 2) | (a << (32-2))) ^
                      ((a >> 13) | (a << (32-13))) ^
                      ((a >> 22) | (a << (32-22)));
        t2 = S0 + ((a & b) ^ (a & c) ^ (b & c));
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sha256_init(SHA256_CTX *ctx) {
    ctx->datalen = 0;
    ctx->bitlen = 0;
    ctx->state[0] = 0x6a09e667;
    ctx->state[1] = 0xbb67ae85;
    ctx->state[2] = 0x3c6ef372;
    ctx->state[3] = 0xa54ff53a;
    ctx->state[4] = 0x510e527f;
    ctx->state[5] = 0x9b05688c;
    ctx->state[6] = 0x1f83d9ab;
    ctx->state[7] = 0x5be0cd19;
}

static void sha256_update(SHA256_CTX *ctx, const uint8_t data[], size_t len) {
    for (size_t i=0; i < len; i++) {
        ctx->data[ctx->datalen] = data[i];
        ctx->datalen++;
        if(ctx->datalen == 64) {
            sha256_transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

static void sha256_final(SHA256_CTX *ctx, uint8_t hash[32]) {
    uint32_t i = ctx->datalen;
    if(ctx->datalen < 56) {
        ctx->data[i++] = 0x80;
        while(i < 56)
            ctx->data[i++] = 0x00;
    } else {
        ctx->data[i++] = 0x80;
        while(i < 64)
            ctx->data[i++] = 0x00;
        sha256_transform(ctx, ctx->data);
        memset(ctx->data, 0, 56);
    }
    ctx->bitlen += ctx->datalen * 8;
    ctx->data[63] = ctx->bitlen;
    ctx->data[62] = ctx->bitlen >> 8;
    ctx->data[61] = ctx->bitlen >> 16;
    ctx->data[60] = ctx->bitlen >> 24;
    ctx->data[59] = ctx->bitlen >> 32;
    ctx->data[58] = ctx->bitlen >> 40;
    ctx->data[57] = ctx->bitlen >> 48;
    ctx->data[56] = ctx->bitlen >> 56;
    sha256_transform(ctx, ctx->data);
    for(i = 0; i < 4; i++) {
        hash[i]      = (ctx->state[0] >> (24 - i * 8)) & 0xff;
        hash[i + 4]  = (ctx->state[1] >> (24 - i * 8)) & 0xff;
        hash[i + 8]  = (ctx->state[2] >> (24 - i * 8)) & 0xff;
        hash[i + 12] = (ctx->state[3] >> (24 - i * 8)) & 0xff;
        hash[i + 16] = (ctx->state[4] >> (24 - i * 8)) & 0xff;
        hash[i + 20] = (ctx->state[5] >> (24 - i * 8)) & 0xff;
        hash[i + 24] = (ctx->state[6] >> (24 - i * 8)) & 0xff;
        hash[i + 28] = (ctx->state[7] >> (24 - i * 8)) & 0xff;
    }
}

void sha256(const uint8_t *data, size_t len, uint8_t hash[32]) {
    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, hash);
}

// ---------------------------------------------------------------------------
// Incremental HMAC-SHA256 Implementation
// ---------------------------------------------------------------------------
typedef struct {
    SHA256_CTX inner;
    uint8_t k_opad[64];
} HMAC_SHA256_CTX;

void hmac_sha256_init(HMAC_SHA256_CTX *ctx, const uint8_t *key, size_t keylen) {
    uint8_t keybuf[64];
    memset(keybuf, 0, 64);
    if (keylen > 64) {
        uint8_t tk[32];
        sha256(key, keylen, tk);
        memcpy(keybuf, tk, 32);
    } else {
        memcpy(keybuf, key, keylen);
    }
    uint8_t k_ipad[64];
    for (int i = 0; i < 64; i++) {
        k_ipad[i] = keybuf[i] ^ 0x36;
        ctx->k_opad[i] = keybuf[i] ^ 0x5c;
    }
    sha256_init(&ctx->inner);
    sha256_update(&ctx->inner, k_ipad, 64);
}

void hmac_sha256_update(HMAC_SHA256_CTX *ctx, const uint8_t *data, size_t datalen) {
    sha256_update(&ctx->inner, data, datalen);
}

void hmac_sha256_final(HMAC_SHA256_CTX *ctx, uint8_t mac[32]) {
    uint8_t inner_hash[32];
    sha256_final(&ctx->inner, inner_hash);
    SHA256_CTX outer;
    sha256_init(&outer);
    sha256_update(&outer, ctx->k_opad, 64);
    sha256_update(&outer, inner_hash, 32);
    sha256_final(&outer, mac);
}

// ---------------------------------------------------------------------------
// Secure memory and randomness functions
// ---------------------------------------------------------------------------
int secure_lock(void *ptr, size_t len) {
    return mlock(ptr, len);
}

void secure_clear(void *v, size_t n) {
    volatile unsigned char *p = v;
    while(n--) *p++ = 0;
}

int get_random_bytes(uint8_t *buf, size_t len) {
    ssize_t ret = getrandom(buf, len, 0);
    return (ret == (ssize_t)len) ? 0 : -1;
}

// ---------------------------------------------------------------------------
// AES Implementation (bitsliced, constant-time)
// ---------------------------------------------------------------------------
static uint8_t gf_mul(uint8_t a, uint8_t b) {
    uint8_t p = 0;
    for (int i = 0; i < 8; i++) {
        if (b & 1)
            p ^= a;
        uint8_t hi = a & 0x80;
        a <<= 1;
        if (hi)
            a ^= 0x1b; // AES polynomial: x^8 + x^4 + x^3 + x + 1
        b >>= 1;
    }
    return p;
}

static uint8_t aes_inv(uint8_t a) {
    if (a == 0) return 0;
    uint8_t x2 = gf_mul(a, a);
    uint8_t x4 = gf_mul(x2, x2);
    uint8_t x8 = gf_mul(x4, x4);
    uint8_t x16 = gf_mul(x8, x8);
    uint8_t x32 = gf_mul(x16, x16);
    uint8_t x64 = gf_mul(x32, x32);
    uint8_t x128 = gf_mul(x64, x64);
    uint8_t inv = gf_mul(x128, gf_mul(x64, gf_mul(x32, gf_mul(x16, gf_mul(x8, gf_mul(x4, x2))))));
    return inv;
}

static uint8_t aes_sbox(uint8_t a) {
    uint8_t inv = aes_inv(a);
    uint8_t r1 = (inv << 1) | (inv >> 7);
    uint8_t r2 = (inv << 2) | (inv >> 6);
    uint8_t r3 = (inv << 3) | (inv >> 5);
    uint8_t r4 = (inv << 4) | (inv >> 4);
    uint8_t s = inv ^ r1 ^ r2 ^ r3 ^ r4 ^ 0x63;
    return s;
}

static void SubBytes(uint8_t state[16]) {
    for (int i = 0; i < 16; i++) {
        state[i] = aes_sbox(state[i]);
    }
}

static void ShiftRows(uint8_t state[16]) {
    uint8_t temp[16];
    memcpy(temp, state, 16);
    state[0] = temp[0];
    state[4] = temp[4];
    state[8] = temp[8];
    state[12] = temp[12];
    state[1] = temp[5];
    state[5] = temp[9];
    state[9] = temp[13];
    state[13] = temp[1];
    state[2] = temp[10];
    state[6] = temp[14];
    state[10] = temp[2];
    state[14] = temp[6];
    state[3] = temp[15];
    state[7] = temp[3];
    state[11] = temp[7];
    state[15] = temp[11];
}

static void MixColumns(uint8_t state[16]) {
    for (int i = 0; i < 4; i++) {
        int col = i * 4;
        uint8_t a0 = state[col];
        uint8_t a1 = state[col+1];
        uint8_t a2 = state[col+2];
        uint8_t a3 = state[col+3];
        uint8_t r0 = gf_mul(a0,2) ^ gf_mul(a1,3) ^ a2 ^ a3;
        uint8_t r1 = a0 ^ gf_mul(a1,2) ^ gf_mul(a2,3) ^ a3;
        uint8_t r2 = a0 ^ a1 ^ gf_mul(a2,2) ^ gf_mul(a3,3);
        uint8_t r3 = gf_mul(a0,3) ^ a1 ^ a2 ^ gf_mul(a3,2);
        state[col] = r0;
        state[col+1] = r1;
        state[col+2] = r2;
        state[col+3] = r3;
    }
}

static void AddRoundKey(uint8_t state[16], const uint8_t roundKey[16]) {
    for (int i = 0; i < 16; i++) {
        state[i] ^= roundKey[i];
    }
}

void AES256_Encrypt_Block(const uint8_t in[16], uint8_t out[16], const uint8_t roundKeys[EXPANDED_KEY_SIZE]) {
    uint8_t state[16];
    memcpy(state, in, 16);
    AddRoundKey(state, roundKeys);
    for (int round = 1; round < AES_ROUNDS; round++) {
        SubBytes(state);
        ShiftRows(state);
        MixColumns(state);
        AddRoundKey(state, roundKeys + round * 16);
    }
    SubBytes(state);
    ShiftRows(state);
    AddRoundKey(state, roundKeys + AES_ROUNDS * 16);
    memcpy(out, state, 16);
}

void AES256_KeyExpansion(const uint8_t key[AES_KEY_SIZE], uint8_t roundKeys[EXPANDED_KEY_SIZE]) {
    uint32_t temp;
    uint32_t *w = (uint32_t *)roundKeys;
    int i;
    for (i = 0; i < 8; i++) {
        w[i] = ((uint32_t)key[4*i] << 24) | ((uint32_t)key[4*i+1] << 16) |
               ((uint32_t)key[4*i+2] << 8) | key[4*i+3];
    }
    uint32_t Rcon[7] = {0x01000000,0x02000000,0x04000000,0x08000000,
                        0x10000000,0x20000000,0x40000000};
    for (i = 8; i < 4 * (AES_ROUNDS + 1); i++) {
        temp = w[i - 1];
        if (i % 8 == 0) {
            temp = (temp << 8) | (temp >> 24);
            temp = ((uint32_t)aes_sbox(temp >> 24) << 24) |
                   ((uint32_t)aes_sbox((temp >> 16) & 0xff) << 16) |
                   ((uint32_t)aes_sbox((temp >> 8) & 0xff) << 8) |
                   ((uint32_t)aes_sbox(temp & 0xff));
            temp ^= Rcon[(i/8) - 1];
        } else if (i % 8 == 4) {
            temp = ((uint32_t)aes_sbox(temp >> 24) << 24) |
                   ((uint32_t)aes_sbox((temp >> 16) & 0xff) << 16) |
                   ((uint32_t)aes_sbox((temp >> 8) & 0xff) << 8) |
                   ((uint32_t)aes_sbox(temp & 0xff));
        }
        w[i] = w[i - 8] ^ temp;
    }
}

// ---------------------------------------------------------------------------
// Counter mode helper
// ---------------------------------------------------------------------------
void add_counter(uint8_t counter[16], uint64_t value) {
    for (int i = 15; i >= 8; i--) {
        uint64_t sum = counter[i] + (value & 0xff);
        counter[i] = sum & 0xff;
        value >>= 8;
    }
}

// ---------------------------------------------------------------------------
// File Processing: Stream-based Encryption/Decryption with Incremental HMAC
// ---------------------------------------------------------------------------
int process_file_stream(const char *input_path, const char *output_path, const char *mode,
                        const uint8_t roundKeys[EXPANDED_KEY_SIZE], const uint8_t hmac_key[32]) {
    FILE *fin = fopen(input_path, "rb");
    if (!fin) {
        fprintf(stderr, "Error: Cannot open input file: %s\n", input_path);
        return -1;
    }
    FILE *fout = fopen(output_path, "wb");
    if (!fout) {
        fprintf(stderr, "Error: Cannot open output file: %s\n", output_path);
        fclose(fin);
        return -1;
    }
    uint8_t iv[AES_BLOCK_SIZE];
    if (strcmp(mode, "encryption") == 0) {
        if (get_random_bytes(iv, AES_BLOCK_SIZE) != 0) {
            fclose(fin); fclose(fout);
            return -1;
        }
        if (fwrite(iv, 1, AES_BLOCK_SIZE, fout) != AES_BLOCK_SIZE) {
            fclose(fin); fclose(fout);
            return -1;
        }
    } else { // decryption: read IV from file
        if (fread(iv, 1, AES_BLOCK_SIZE, fin) != AES_BLOCK_SIZE) {
            fclose(fin); fclose(fout);
            return -1;
        }
    }

    if (strcmp(mode, "encryption") == 0) {
        // Initialize incremental HMAC context.
        HMAC_SHA256_CTX hmac_ctx;
        hmac_sha256_init(&hmac_ctx, hmac_key, 32);
        uint8_t in_buf[CTR_BLOCK_SIZE];
        uint8_t out_buf[CTR_BLOCK_SIZE];
        size_t bytes_read;
        uint64_t global_block_index = 0;
        while ((bytes_read = fread(in_buf, 1, CTR_BLOCK_SIZE, fin)) > 0) {
            size_t num_blocks = (bytes_read + AES_BLOCK_SIZE - 1) / AES_BLOCK_SIZE;
            for (size_t block = 0; block < num_blocks; block++) {
                uint8_t counter[AES_BLOCK_SIZE];
                memcpy(counter, iv, AES_BLOCK_SIZE);
                add_counter(counter, global_block_index + block);
                uint8_t keystream[AES_BLOCK_SIZE];
                AES256_Encrypt_Block(counter, keystream, roundKeys);
                size_t offset = block * AES_BLOCK_SIZE;
                for (size_t i = 0; i < AES_BLOCK_SIZE; i++) {
                    if (offset + i < bytes_read) {
                        out_buf[offset + i] = in_buf[offset + i] ^ keystream[i];
                    }
                }
            }
            global_block_index += num_blocks;
            if (fwrite(out_buf, 1, bytes_read, fout) != bytes_read) {
                fclose(fin); fclose(fout);
                return -1;
            }
            hmac_sha256_update(&hmac_ctx, out_buf, bytes_read);
        }
        uint8_t mac[32];
        hmac_sha256_final(&hmac_ctx, mac);
        if (fwrite(mac, 1, 32, fout) != 32) {
            fclose(fin); fclose(fout);
            return -1;
        }
    } else { // decryption mode
        // Determine file size.
        fseek(fin, 0, SEEK_END);
        long fsize = ftell(fin);
        if (fsize < AES_BLOCK_SIZE + 32) {
            fclose(fin); fclose(fout);
            return -1;
        }
        long ciphertext_size = fsize - AES_BLOCK_SIZE - 32;
        fseek(fin, AES_BLOCK_SIZE, SEEK_SET);
        HMAC_SHA256_CTX hmac_ctx;
        hmac_sha256_init(&hmac_ctx, hmac_key, 32);
        uint8_t in_buf[CTR_BLOCK_SIZE];
        uint8_t out_buf[CTR_BLOCK_SIZE];
        size_t bytes_to_process = ciphertext_size;
        uint64_t global_block_index = 0;
        while (bytes_to_process > 0) {
            size_t chunk = (bytes_to_process > CTR_BLOCK_SIZE) ? CTR_BLOCK_SIZE : bytes_to_process;
            size_t bytes_read = fread(in_buf, 1, chunk, fin);
            if (bytes_read != chunk) {
                fclose(fin); fclose(fout);
                return -1;
            }
            hmac_sha256_update(&hmac_ctx, in_buf, bytes_read);
            size_t num_blocks = (bytes_read + AES_BLOCK_SIZE - 1) / AES_BLOCK_SIZE;
            for (size_t block = 0; block < num_blocks; block++) {
                uint8_t counter[AES_BLOCK_SIZE];
                memcpy(counter, iv, AES_BLOCK_SIZE);
                add_counter(counter, global_block_index + block);
                uint8_t keystream[AES_BLOCK_SIZE];
                AES256_Encrypt_Block(counter, keystream, roundKeys);
                size_t offset = block * AES_BLOCK_SIZE;
                for (size_t i = 0; i < AES_BLOCK_SIZE; i++) {
                    if (offset + i < bytes_read) {
                        out_buf[offset + i] = in_buf[offset + i] ^ keystream[i];
                    }
                }
            }
            global_block_index += num_blocks;
            if (fwrite(out_buf, 1, bytes_read, fout) != bytes_read) {
                fclose(fin); fclose(fout);
                return -1;
            }
            bytes_to_process -= bytes_read;
        }
        uint8_t expected_mac[32];
        if (fread(expected_mac, 1, 32, fin) != 32) {
            fclose(fin); fclose(fout);
            return -1;
        }
        uint8_t computed_mac[32];
        hmac_sha256_final(&hmac_ctx, computed_mac);
        if (memcmp(expected_mac, computed_mac, 32) != 0) {
            fprintf(stderr, "Error: HMAC verification failed. Data may be tampered.\n");
            fclose(fin); fclose(fout);
            return -1;
        }
    }
    fclose(fin);
    fclose(fout);
    return 0;
}

// ---------------------------------------------------------------------------
// Key Derivation: Derive a separate HMAC key by hashing "HMAC" concatenated with the encryption key.
// ---------------------------------------------------------------------------
void derive_hmac_key(const uint8_t enc_key[AES_KEY_SIZE], uint8_t hmac_key[32]) {
    const char *prefix = "HMAC";
    size_t prefix_len = strlen(prefix);
    uint8_t buf[64];
    memcpy(buf, prefix, prefix_len);
    memcpy(buf + prefix_len, enc_key, AES_KEY_SIZE);
    sha256(buf, prefix_len + AES_KEY_SIZE, hmac_key);
}

// ---------------------------------------------------------------------------
// Main Function and Usage
// ---------------------------------------------------------------------------
void print_help(const char *progname) {
    printf("Usage:\n");
    printf("  %s <mode> <key> <input file> [output file]\n", progname);
    printf("  mode: encryption or decryption\n");
    printf("  key: 64 hex digits representing 256 bits\n");
}

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    const char *mode = argv[1];
    if (strcmp(mode, "encryption") && strcmp(mode, "decryption")) {
        fprintf(stderr, "Error: Mode must be 'encryption' or 'decryption'.\n");
        return EXIT_FAILURE;
    }
    const char *key_str = argv[2];
    const char *input_path = argv[3];
    const char *output_path = (argc == 5) ? argv[4] : "output";
    if (strlen(key_str) != 64) {
        fprintf(stderr, "Error: Key must be 64 hex digits representing 256 bits.\n");
        return EXIT_FAILURE;
    }
    uint8_t enc_key[AES_KEY_SIZE];
    for (int i = 0; i < AES_KEY_SIZE; i++) {
        char byte_str[3] = { key_str[2*i], key_str[2*i+1], '\0' };
        enc_key[i] = (uint8_t) strtoul(byte_str, NULL, 16);
    }
    uint8_t roundKeys[EXPANDED_KEY_SIZE];
    AES256_KeyExpansion(enc_key, roundKeys);
    uint8_t hmac_key[32];
    derive_hmac_key(enc_key, hmac_key);
    secure_lock(enc_key, sizeof(enc_key));
    secure_lock(roundKeys, sizeof(roundKeys));
    secure_lock(hmac_key, sizeof(hmac_key));
    int ret = process_file_stream(input_path, output_path, mode, roundKeys, hmac_key);
    secure_clear(enc_key, sizeof(enc_key));
    secure_clear(roundKeys, sizeof(roundKeys));
    secure_clear(hmac_key, sizeof(hmac_key));
    if (ret == 0) {
        printf("%s complete. Output written to %s\n", mode, output_path);
        return EXIT_SUCCESS;
    } else {
        fprintf(stderr, "Error processing file.\n");
        return EXIT_FAILURE;
    }
}


// ==================== Main Function ====================

void print_help(const char *progname) {
    printf("Usage:\n");
    printf("  %s <mode> <key> <input file> [output file]\n", progname);
    printf("  mode: encryption or decryption\n");
    printf("  key: 64 hex digits representing 256 bits\n");
}

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    const char *mode = argv[1];
    if (strcmp(mode, "encryption") && strcmp(mode, "decryption")) {
        fprintf(stderr, "Error: Mode must be 'encryption' or 'decryption'.\n");
        return EXIT_FAILURE;
    }
    const char *key_str = argv[2];
    const char *input_path = argv[3];
    const char *output_path = (argc == 5) ? argv[4] : "output";
    if (strlen(key_str) != 64) {
        fprintf(stderr, "Error: Key must be 64 hex digits representing 256 bits.\n");
        return EXIT_FAILURE;
    }
    uint8_t enc_key[AES_KEY_SIZE];
    for (int i = 0; i < AES_KEY_SIZE; i++) {
        char byte_str[3] = { key_str[2*i], key_str[2*i+1], '\0' };
        enc_key[i] = (uint8_t) strtoul(byte_str, NULL, 16);
    }
    // Expand key for AES encryption.
    uint8_t roundKeys[EXPANDED_KEY_SIZE];
    AES256_KeyExpansion(enc_key, roundKeys);
    // Derive a separate HMAC key.
    uint8_t hmac_key[32];
    derive_hmac_key(enc_key, hmac_key);
    // Securely lock sensitive key material.
    secure_lock(enc_key, sizeof(enc_key));
    secure_lock(roundKeys, sizeof(roundKeys));
    secure_lock(hmac_key, sizeof(hmac_key));
    // Process file (encryption or decryption).
    int ret = process_file(input_path, output_path, mode, roundKeys, hmac_key);
    secure_clear(enc_key, sizeof(enc_key));
    secure_clear(roundKeys, sizeof(roundKeys));
    secure_clear(hmac_key, sizeof(hmac_key));
    if (ret == 0) {
        printf("%s complete. Output written to %s\n", mode, output_path);
        return EXIT_SUCCESS;
    } else {
        fprintf(stderr, "Error processing file.\n");
        return EXIT_FAILURE;
    }
}
