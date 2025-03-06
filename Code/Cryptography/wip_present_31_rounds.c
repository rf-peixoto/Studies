/* gcc -O2 -o present wip_present_31_rounds.c */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define PRESENT_BLOCK_SIZE 8      // 64-bit block size
#define NUM_ROUNDS 31             // Full 31 rounds
#define CTR_BLOCK_SIZE 4096       // File processing block size

// ------------------- PRESENT Cipher Functions -------------------

// S-box used by PRESENT.
static const uint8_t sbox[16] = {
    0xC, 0x5, 0x6, 0xB,
    0x9, 0x0, 0xA, 0xD,
    0x3, 0xE, 0xF, 0x8,
    0x4, 0x7, 0x1, 0x2
};

/* Bit permutation (pLayer) as specified in PRESENT. */
static uint64_t pLayer(uint64_t state) {
    uint64_t new_state = 0;
    for (int i = 0; i < 63; i++) {
        uint64_t bit = (state >> i) & 1ULL;
        int pos = (16 * i) % 63;
        new_state |= bit << pos;
    }
    // Bit 63 remains unchanged.
    new_state |= ((state >> 63) & 1ULL) << 63;
    return new_state;
}

/* S-box layer: apply the 4-bit S-box to each of the 16 nibbles. */
static uint64_t sBoxLayer(uint64_t state) {
    uint64_t new_state = 0;
    for (int i = 0; i < 16; i++) {
        uint8_t nibble = (state >> (4 * i)) & 0xF;
        new_state |= ((uint64_t)sbox[nibble]) << (4 * i);
    }
    return new_state;
}

/* Rotate left a 128-bit value by n bits. */
static __uint128_t rotate_left_128(__uint128_t x, unsigned int n) {
    return (x << n) | (x >> (128 - n));
}

/* Generate round keys for PRESENT-128.
   The procedure rotates the key, substitutes the top 8 bits via the S-box,
   and XORs the round counter into bits 66–62. */
static void generate_round_keys(__uint128_t key, uint64_t round_keys[NUM_ROUNDS + 1]) {
    round_keys[0] = (uint64_t)(key >> 64);
    for (int r = 1; r <= NUM_ROUNDS; r++) {
        key = rotate_left_128(key, 61);
        uint8_t top = (uint8_t)(key >> 120);
        uint8_t substituted = (sbox[top >> 4] << 4) | sbox[top & 0x0F];
        key = (key & (((__uint128_t)1 << 120) - 1)) | (((__uint128_t)substituted) << 120);
        key ^= (((__uint128_t)r & 0x1F) << 62);
        round_keys[r] = (uint64_t)(key >> 64);
    }
}

/* Encrypt a 64-bit plaintext block using the PRESENT cipher with the precomputed round keys. */
static uint64_t present_encrypt(uint64_t plaintext, uint64_t round_keys[NUM_ROUNDS + 1]) {
    uint64_t state = plaintext;
    state ^= round_keys[0];
    for (int r = 1; r <= NUM_ROUNDS; r++) {
        state = sBoxLayer(state);
        state = pLayer(state);
        state ^= round_keys[r];
    }
    return state;
}

// ------------------- Utility Functions -------------------

/* Securely clear sensitive memory. */
static void secure_clear(void *v, size_t n) {
    volatile unsigned char *p = v;
    while (n--) {
        *p++ = 0;
    }
}

/* Convert a hexadecimal character to its integer value. */
static int hex_char_to_int(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return -1;
}

/* Parse a 32-character hex string into a 16-byte array (128-bit key). */
static int parse_key(const char *hex, unsigned char *out) {
    if (strlen(hex) != 32)
        return -1;
    for (int i = 0; i < 16; i++) {
        int high = hex_char_to_int(hex[i * 2]);
        int low  = hex_char_to_int(hex[i * 2 + 1]);
        if (high < 0 || low < 0)
            return -1;
        out[i] = (unsigned char)((high << 4) | low);
    }
    return 0;
}

/* Generate cryptographically secure random bytes using /dev/urandom.
   Terminates with an error if /dev/urandom is not available. */
static int generate_random_bytes(unsigned char *out, int len) {
    FILE *urand = fopen("/dev/urandom", "rb");
    if (!urand) {
        fprintf(stderr, "Error: /dev/urandom not available.\n");
        return -1;
    }
    if (fread(out, 1, len, urand) != (size_t)len) {
        fprintf(stderr, "Error: Failed to read from /dev/urandom.\n");
        fclose(urand);
        return -1;
    }
    fclose(urand);
    return 0;
}

/* Convert 8 bytes (big-endian) to a 64-bit integer. */
static uint64_t bytes_to_uint64(const unsigned char *in) {
    uint64_t out = 0;
    for (int i = 0; i < 8; i++) {
        out = (out << 8) | in[i];
    }
    return out;
}

/* Convert a 64-bit integer to 8 bytes (big-endian). */
static void uint64_to_bytes(uint64_t in, unsigned char *out) {
    for (int i = 7; i >= 0; i--) {
        out[i] = in & 0xFF;
        in >>= 8;
    }
}

/* Print command-line usage help. */
static void print_help(const char *progname) {
    fprintf(stdout, "Usage: %s <mode> <key> <input file> [output file]\n", progname);
    fprintf(stdout, "  mode: encryption or decryption\n");
    fprintf(stdout, "  key: 32 hex digits representing 16 bytes (128 bits)\n");
    fprintf(stdout, "  input file: file to encrypt or decrypt\n");
    fprintf(stdout, "  output file: optional, defaults to \"output\"\n");
    fprintf(stdout, "\nExamples:\n");
    fprintf(stdout, "  %s encryption 00112233445566778899AABBCCDDEEFF plaintext.txt\n", progname);
    fprintf(stdout, "  %s decryption 00112233445566778899AABBCCDDEEFF ciphertext.enc output.txt\n", progname);
    fprintf(stdout, "\nNote: This implementation uses the full 31 rounds of PRESENT.\n");
    fprintf(stdout, "Differential attacks on a 26-round variant are mitigated by enforcing the complete round structure.\n");
}

// ------------------- CTR Mode Functions --------------------

/* Process the input file using CTR mode.
   Each block is processed by XORing with the PRESENT keystream generated from the nonce (IV + counter). */
static int process_file(FILE *fin, FILE *fout, uint64_t round_keys[NUM_ROUNDS + 1], uint64_t iv_val) {
    unsigned char buffer[CTR_BLOCK_SIZE];
    size_t bytes_read;
    uint64_t counter = 0;
    
    while ((bytes_read = fread(buffer, 1, CTR_BLOCK_SIZE, fin)) > 0) {
        for (size_t offset = 0; offset < bytes_read; offset += 8) {
            uint64_t nonce = iv_val + counter;
            uint64_t keystream = present_encrypt(nonce, round_keys);
            unsigned char ks_bytes[8];
            uint64_to_bytes(keystream, ks_bytes);
            size_t block_size = (offset + 8 <= bytes_read) ? 8 : (bytes_read - offset);
            for (size_t i = 0; i < block_size; i++) {
                buffer[offset + i] ^= ks_bytes[i];
            }
            counter++;
        }
        if (fwrite(buffer, 1, bytes_read, fout) != bytes_read) {
            fprintf(stderr, "Error: Failed to write data to output file.\n");
            return -1;
        }
    }
    if (ferror(fin)) {
        fprintf(stderr, "Error: Failed to read from input file.\n");
        return -1;
    }
    return 0;
}

// ------------------- Main Function -------------------

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    
    if ((strcmp(argv[1], "-h") == 0) || (strcmp(argv[1], "--help") == 0)) {
        print_help(argv[0]);
        return EXIT_SUCCESS;
    }
    
    const char *mode = argv[1];
    const char *key_str = argv[2];
    const char *input_filename = argv[3];
    const char *output_filename = (argc == 5) ? argv[4] : "output";
    
    if (strcmp(mode, "encryption") != 0 && strcmp(mode, "decryption") != 0) {
        fprintf(stderr, "Error: Mode must be either 'encryption' or 'decryption'.\n");
        return EXIT_FAILURE;
    }
    
    unsigned char key_bytes[16];
    if (parse_key(key_str, key_bytes) != 0) {
        fprintf(stderr, "Error: Invalid key. Must be 32 hex digits representing 16 bytes.\n");
        return EXIT_FAILURE;
    }
    
    FILE *fin = fopen(input_filename, "rb");
    if (!fin) {
        fprintf(stderr, "Error: Cannot open input file: %s\n", input_filename);
        return EXIT_FAILURE;
    }
    
    FILE *fout = fopen(output_filename, "wb");
    if (!fout) {
        fprintf(stderr, "Error: Cannot open output file: %s\n", output_filename);
        fclose(fin);
        return EXIT_FAILURE;
    }
    
    // Precompute round keys from the 128-bit key (big-endian).
    __uint128_t key_reg = 0;
    for (int i = 0; i < 16; i++) {
        key_reg = (key_reg << 8) | key_bytes[i];
    }
    uint64_t round_keys[NUM_ROUNDS + 1];
    generate_round_keys(key_reg, round_keys);
    
    unsigned char iv[PRESENT_BLOCK_SIZE];
    uint64_t iv_val = 0;
    if (strcmp(mode, "encryption") == 0) {
        if (generate_random_bytes(iv, PRESENT_BLOCK_SIZE) != 0) {
            fprintf(stderr, "Error: Failed to generate random IV.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key_bytes, sizeof(key_bytes));
            return EXIT_FAILURE;
        }
        if (fwrite(iv, 1, PRESENT_BLOCK_SIZE, fout) != PRESENT_BLOCK_SIZE) {
            fprintf(stderr, "Error: Failed to write IV to output file.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key_bytes, sizeof(key_bytes));
            return EXIT_FAILURE;
        }
        iv_val = bytes_to_uint64(iv);
    } else { // decryption
        if (fread(iv, 1, PRESENT_BLOCK_SIZE, fin) != PRESENT_BLOCK_SIZE) {
            fprintf(stderr, "Error: Input file too short to contain IV.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key_bytes, sizeof(key_bytes));
            return EXIT_FAILURE;
        }
        iv_val = bytes_to_uint64(iv);
    }
    
    if (process_file(fin, fout, round_keys, iv_val) != 0) {
        fclose(fin);
        fclose(fout);
        secure_clear(key_bytes, sizeof(key_bytes));
        secure_clear(round_keys, sizeof(round_keys));
        return EXIT_FAILURE;
    }
    
    fclose(fin);
    fclose(fout);
    
    secure_clear(key_bytes, sizeof(key_bytes));
    secure_clear(round_keys, sizeof(round_keys));
    secure_clear(&key_reg, sizeof(key_reg));
    secure_clear(iv, sizeof(iv));
    
    fprintf(stdout, "%s complete. Output written to %s\n", mode, output_filename);
    return EXIT_SUCCESS;
}
