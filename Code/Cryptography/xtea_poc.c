// gcc -std=c11 -O2 -o xtea_poc xtea_poc.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>

#define DELTA       0x9E3779B9
#define NUM_ROUNDS  32       // 32 iterations → 64 Feistel rounds
#define BLOCK_SIZE  8        // 64-bit block

// XTEA single-block encrypt/decrypt
void xtea_encrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0 = v[0], v1 = v[1], sum = 0;
    for (unsigned i = 0; i < NUM_ROUNDS; i++) {
        v0 += (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[ sum & 3 ]);
        sum += DELTA;
        v1 += (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 3]);
    }
    v[0] = v0; v[1] = v1;
}

void xtea_decrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0 = v[0], v1 = v[1], sum = DELTA * NUM_ROUNDS;
    for (unsigned i = 0; i < NUM_ROUNDS; i++) {
        v1 -= (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 3]);
        sum -= DELTA;
        v0 -= (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[ sum & 3 ]);
    }
    v[0] = v0; v[1] = v1;
}

// Derive 128-bit key from user input (pad/truncate to 16 bytes)
void derive_key(const char *in, uint32_t key_out[4]) {
    unsigned char buf[16] = {0};
    size_t len = strlen(in);
    if (len > 16) len = 16;
    memcpy(buf, in, len);
    for (int i = 0; i < 4; i++) {
        key_out[i] =  (uint32_t)buf[4*i + 0]
                    | (uint32_t)buf[4*i + 1] << 8
                    | (uint32_t)buf[4*i + 2] << 16
                    | (uint32_t)buf[4*i + 3] << 24;
    }
}

// Parse up to 16 hex digits from user into a 64-bit value.
// Returns 0 on success, non-zero on failure.
int parse_iv(const char *s, uint32_t iv_out[2]) {
    uint64_t iv = 0;
    int len = 0;
    // skip leading spaces
    while (isspace((unsigned char)*s)) s++;
    // count hex digits
    const char *p = s;
    while (isxdigit((unsigned char)*p) && len < 16) {
        iv = (iv << 4) | (uint64_t)(isdigit((unsigned char)*p)
              ? *p - '0'
              : (tolower((unsigned char)*p) - 'a' + 10));
        p++; len++;
    }
    if (len == 0) {
        // no hex digits → use zero IV
        iv = 0;
    }
    else if (*p && !isspace((unsigned char)*p)) {
        return -1;  // invalid character
    }
    iv_out[0] = (uint32_t)(iv & 0xFFFFFFFF);
    iv_out[1] = (uint32_t)(iv >> 32);
    return 0;
}

int main(void) {
    char plaintext[1024];
    char keystr[64];
    char mode[16];
    char iv_input[32];

    // 1. Read plaintext
    printf("Enter plaintext (max 1023 chars):\n> ");
    if (!fgets(plaintext, sizeof plaintext, stdin)) return 1;
    plaintext[strcspn(plaintext, "\n")] = '\0';

    // 2. Read key
    printf("Enter encryption key (max 16 chars):\n> ");
    if (!fgets(keystr, sizeof keystr, stdin)) return 1;
    keystr[strcspn(keystr, "\n")] = '\0';

    // 3. Read mode
    printf("Select mode (ECB, CBC, CTR):\n> ");
    if (!fgets(mode, sizeof mode, stdin)) return 1;
    mode[strcspn(mode, "\n")] = '\0';

    // Normalize mode to uppercase
    for (char *p = mode; *p; ++p) *p = toupper((unsigned char)*p);

    // 4. If CBC or CTR, read IV
    uint32_t iv[2] = {0,0};
    int use_iv = 0;
    if (strcmp(mode, "CBC") == 0 || strcmp(mode, "CTR") == 0) {
        use_iv = 1;
        printf("Enter 64-bit IV as 16 hex digits (press Enter for 0000000000000000):\n> ");
        if (!fgets(iv_input, sizeof iv_input, stdin)) return 1;
        iv_input[strcspn(iv_input, "\n")] = '\0';
        if (parse_iv(iv_input, iv) != 0) {
            fprintf(stderr, "Invalid IV format\n");
            return 1;
        }
    }

    // 5. Derive key
    uint32_t key[4];
    derive_key(keystr, key);

    // 6. Prepare buffers
    size_t pt_len     = strlen(plaintext);
    size_t num_blocks = (pt_len + BLOCK_SIZE - 1) / BLOCK_SIZE;
    size_t buf_size   = num_blocks * BLOCK_SIZE;

    unsigned char *inbuf  = calloc(buf_size, 1);
    unsigned char *encbuf = malloc(buf_size);
    unsigned char *decbuf = malloc(buf_size);
    if (!inbuf || !encbuf || !decbuf) return 1;
    memcpy(inbuf, plaintext, pt_len);

    // 7. Encryption
    uint64_t ctr = ((uint64_t)iv[1] << 32) | iv[0];
    uint32_t prev[2] = { iv[0], iv[1] };

    for (size_t i = 0; i < num_blocks; i++) {
        uint32_t block[2];
        memcpy(block, inbuf + i*BLOCK_SIZE, BLOCK_SIZE);

        if (strcmp(mode, "ECB") == 0) {
            // ECB: encrypt block directly
            xtea_encrypt(block, key);
        }
        else if (strcmp(mode, "CBC") == 0) {
            // CBC: XOR with prev ciphertext (or IV), then encrypt
            block[0] ^= prev[0];
            block[1] ^= prev[1];
            xtea_encrypt(block, key);
            // update prev to this ciphertext
            prev[0] = block[0];
            prev[1] = block[1];
        }
        else if (strcmp(mode, "CTR") == 0) {
            // CTR: generate keystream by encrypting counter
            uint32_t ks[2] = { (uint32_t)(ctr & 0xFFFFFFFF), (uint32_t)(ctr >> 32) };
            xtea_encrypt(ks, key);
            // XOR plaintext block with keystream
            block[0] ^= ks[0];
            block[1] ^= ks[1];
            // increment counter
            ctr++;
        }
        else {
            fprintf(stderr, "Unknown mode: %s\n", mode);
            return 1;
        }

        memcpy(encbuf + i*BLOCK_SIZE, block, BLOCK_SIZE);
    }

    // 8. Print ciphertext
    printf("\nCiphertext (hex):\n");
    for (size_t i = 0; i < buf_size; i++) {
        printf("%02X", encbuf[i]);
    }
    printf("\n");

    // 9. Decryption (reset state)
    ctr = ((uint64_t)iv[1] << 32) | iv[0];
    prev[0] = iv[0]; prev[1] = iv[1];

    for (size_t i = 0; i < num_blocks; i++) {
        uint32_t block[2];
        memcpy(block, encbuf + i*BLOCK_SIZE, BLOCK_SIZE);

        if (strcmp(mode, "ECB") == 0) {
            xtea_decrypt(block, key);
        }
        else if (strcmp(mode, "CBC") == 0) {
            uint32_t cur_ct[2] = { block[0], block[1] };
            xtea_decrypt(block, key);
            // XOR with previous ciphertext (or IV)
            block[0] ^= prev[0];
            block[1] ^= prev[1];
            // update prev to this ciphertext
            prev[0] = cur_ct[0];
            prev[1] = cur_ct[1];
        }
        else if (strcmp(mode, "CTR") == 0) {
            uint32_t ks[2] = { (uint32_t)(ctr & 0xFFFFFFFF), (uint32_t)(ctr >> 32) };
            xtea_encrypt(ks, key);
            block[0] ^= ks[0];
            block[1] ^= ks[1];
            ctr++;
        }

        memcpy(decbuf + i*BLOCK_SIZE, block, BLOCK_SIZE);
    }

    decbuf[pt_len] = '\0';
    printf("\nDecrypted plaintext:\n%s\n", (char*)decbuf);

    // 10. Clean up and exit
    memset(inbuf,  0, buf_size);
    memset(encbuf, 0, buf_size);
    memset(decbuf, 0, buf_size);
    free(inbuf);
    free(encbuf);
    free(decbuf);

    return 0;
}
