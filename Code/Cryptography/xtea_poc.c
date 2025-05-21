// gcc -std=c11 -O2 -o xtea_poc xtea_poc.c


#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define DELTA 0x9E3779B9
#define NUM_ROUNDS 32   // 32 iterations → 64 Feistel rounds
#define BLOCK_SIZE 8    // 64 bits

// XTEA encrypt one 64-bit block (v[0], v[1]) with 128-bit key
void xtea_encrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0 = v[0], v1 = v[1], sum = 0;
    for (unsigned i = 0; i < NUM_ROUNDS; i++) {
        v0 += (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[ sum & 3 ]);
        sum += DELTA;
        v1 += (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 3]);
    }
    v[0] = v0; v[1] = v1;
}

// XTEA decrypt one 64-bit block
void xtea_decrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0 = v[0], v1 = v[1], sum = DELTA * NUM_ROUNDS;
    for (unsigned i = 0; i < NUM_ROUNDS; i++) {
        v1 -= (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 3]);
        sum -= DELTA;
        v0 -= (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[ sum & 3 ]);
    }
    v[0] = v0; v[1] = v1;
}

// Pad or truncate user key to exactly 16 bytes, then interpret as four uint32_t
void derive_key(const char *in, uint32_t key_out[4]) {
    unsigned char buf[16] = {0};
    size_t len = strlen(in);
    if (len > 16) len = 16;
    memcpy(buf, in, len);
    // Combine each 4 bytes into a 32-bit word (little endian)
    for (int i = 0; i < 4; i++) {
        key_out[i] =  (uint32_t)buf[4*i + 0]
                    | (uint32_t)buf[4*i + 1] << 8
                    | (uint32_t)buf[4*i + 2] << 16
                    | (uint32_t)buf[4*i + 3] << 24;
    }
}

int main(void) {
    char plaintext[1024];
    char keystr[64];
    printf("Enter plaintext (max 1023 chars):\n> ");
    if (!fgets(plaintext, sizeof plaintext, stdin)) {
        fprintf(stderr, "Failed to read plaintext\n");
        return EXIT_FAILURE;
    }
    // Remove trailing newline
    plaintext[strcspn(plaintext, "\n")] = '\0';

    printf("Enter encryption key (max 16 chars):\n> ");
    if (!fgets(keystr, sizeof keystr, stdin)) {
        fprintf(stderr, "Failed to read key\n");
        return EXIT_FAILURE;
    }
    keystr[strcspn(keystr, "\n")] = '\0';

    // Derive 128-bit key
    uint32_t key[4];
    derive_key(keystr, key);

    size_t pt_len = strlen(plaintext);
    size_t num_blocks = (pt_len + BLOCK_SIZE - 1) / BLOCK_SIZE;
    size_t buf_size = num_blocks * BLOCK_SIZE;

    // Allocate buffers
    unsigned char *inbuf  = calloc(buf_size, 1);  // zero-pad
    unsigned char *encbuf = malloc(buf_size);
    unsigned char *decbuf = malloc(buf_size);
    if (!inbuf || !encbuf || !decbuf) {
        fprintf(stderr, "Memory allocation error\n");
        return EXIT_FAILURE;
    }
    memcpy(inbuf, plaintext, pt_len);

    // Encrypt each 8-byte block
    for (size_t i = 0; i < num_blocks; i++) {
        uint32_t block[2];
        memcpy(block, inbuf + i*BLOCK_SIZE, BLOCK_SIZE);
        xtea_encrypt(block, key);
        memcpy(encbuf + i*BLOCK_SIZE, block, BLOCK_SIZE);
    }

    // Print ciphertext as hex
    printf("\nCiphertext (hex):\n");
    for (size_t i = 0; i < buf_size; i++) {
        printf("%02X", encbuf[i]);
    }
    printf("\n");

    // Decrypt each block
    for (size_t i = 0; i < num_blocks; i++) {
        uint32_t block[2];
        memcpy(block, encbuf + i*BLOCK_SIZE, BLOCK_SIZE);
        xtea_decrypt(block, key);
        memcpy(decbuf + i*BLOCK_SIZE, block, BLOCK_SIZE);
    }

    // Null-terminate and print decrypted text
    decbuf[pt_len] = '\0';
    printf("\nDecrypted plaintext:\n%s\n", (char*)decbuf);

    // Clean up
    memset(inbuf,  0, buf_size);
    memset(encbuf, 0, buf_size);
    memset(decbuf, 0, buf_size);
    free(inbuf);
    free(encbuf);
    free(decbuf);

    return EXIT_SUCCESS;
}
