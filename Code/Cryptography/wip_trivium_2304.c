/* gcc -O2 -o trivium wip_trivium_2304.c */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#define STATE_SIZE 288
#define KEY_BITS 80
#define IV_BITS 80
#define BLOCK_SIZE 4096
#define WARMUP_ROUNDS 2304       /* (1152 * 2) Double warm-up rounds */

/* Securely clear sensitive memory (attempts to avoid optimization removal) */
void secure_clear(void *v, size_t n) {
    volatile unsigned char *p = v;
    while (n--) {
        *p++ = 0;
    }
}

/* Optimized in-place state update using memmove for each register */
int trivium_update(int *state) {
    int t1 = state[65] ^ state[92];
    int t2 = state[161] ^ state[176];
    int t3 = state[242] ^ state[287];
    int output = t1 ^ t2 ^ t3;
    
    t1 = t1 ^ (state[90] & state[91]) ^ state[170];
    t2 = t2 ^ (state[174] & state[175]) ^ state[263];
    t3 = t3 ^ (state[285] & state[286]) ^ state[68];
    
    /* Register A: positions 0..92 (93 bits) */
    memmove(&state[1], state, 92 * sizeof(int));
    state[0] = t3;
    
    /* Register B: positions 93..176 (84 bits) */
    memmove(&state[94], &state[93], 83 * sizeof(int));  // Shift bits 93..175 to positions 94..176
    state[93] = t1;
    
    /* Register C: positions 177..287 (111 bits) */
    memmove(&state[178], &state[177], 110 * sizeof(int));  // Shift bits 177..286 to positions 178..287
    state[177] = t2;
    
    return output;
}

/* Unrolled inner loop: generate one keystream byte by 8 successive rounds */
unsigned char get_keystream_byte(int *state) {
    unsigned char ks = 0;
    ks |= (trivium_update(state) & 1) << 7;
    ks |= (trivium_update(state) & 1) << 6;
    ks |= (trivium_update(state) & 1) << 5;
    ks |= (trivium_update(state) & 1) << 4;
    ks |= (trivium_update(state) & 1) << 3;
    ks |= (trivium_update(state) & 1) << 2;
    ks |= (trivium_update(state) & 1) << 1;
    ks |= (trivium_update(state) & 1);
    return ks;
}

/* Initialize the Trivium state with 80-bit key and IV (both provided as bit arrays) */
void trivium_init(int *state, int *key_bits, int *iv_bits) {
    // Load key bits into state positions 0-79.
    for (int i = 0; i < 80; i++) {
        state[i] = key_bits[i];
    }
    // Positions 80-92: set to 0.
    for (int i = 80; i < 93; i++) {
        state[i] = 0;
    }
    // Load IV bits into positions 93-172.
    for (int i = 0; i < 80; i++) {
        state[93 + i] = iv_bits[i];
    }
    // Positions 173-176: set to 0.
    for (int i = 173; i < 177; i++) {
        state[i] = 0;
    }
    // Positions 177-284: set to 0.
    for (int i = 177; i < 285; i++) {
        state[i] = 0;
    }
    // Positions 285-287: set to 1.
    state[285] = 1;
    state[286] = 1;
    state[287] = 1;
    
    // Warm-up rounds (doubled for added security)
    for (int i = 0; i < WARMUP_ROUNDS; i++) {
        trivium_update(state);
    }
}

/* Convert a byte array to an array of bits (0 or 1). */
void bytes_to_bits(const unsigned char *in, int len, int *out) {
    for (int i = 0; i < len; i++) {
        for (int j = 0; j < 8; j++) {
            out[i * 8 + j] = (in[i] >> (7 - j)) & 1;
        }
    }
}

/* Convert a hexadecimal character to its integer value */
int hex_char_to_int(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

/* Parse a 20-character hex string into a 10-byte array */
int parse_key(const char *hex, unsigned char *out) {
    if (strlen(hex) != 20) return -1;
    for (int i = 0; i < 10; i++) {
        int high = hex_char_to_int(hex[i * 2]);
        int low  = hex_char_to_int(hex[i * 2 + 1]);
        if (high < 0 || low < 0) return -1;
        out[i] = (unsigned char)((high << 4) | low);
    }
    return 0;
}

/* Generate random bytes using /dev/urandom if available; fallback to rand() */
int generate_random_bytes(unsigned char *out, int len) {
    FILE *urand = fopen("/dev/urandom", "rb");
    if (urand) {
        if (fread(out, 1, len, urand) != (size_t)len) {
            fclose(urand);
            return -1;
        }
        fclose(urand);
        return 0;
    } else {
        srand((unsigned)time(NULL));
        for (int i = 0; i < len; i++) {
            out[i] = rand() & 0xFF;
        }
        return 0;
    }
}

/* Print command-line help */
void print_help(const char *progname) {
    fprintf(stdout, "Usage: %s <mode> <key> <input file> [output file]\n", progname);
    fprintf(stdout, "  mode: encryption or decryption\n");
    fprintf(stdout, "  key: 20 hex digits representing 10 bytes (80 bits)\n");
    fprintf(stdout, "  input file: file to encrypt or decrypt\n");
    fprintf(stdout, "  output file: optional, defaults to \"output\"\n");
    fprintf(stdout, "\nExamples:\n");
    fprintf(stdout, "  %s encryption 0123456789ABCDEF0123 plaintext.txt\n", progname);
    fprintf(stdout, "  %s decryption 0123456789ABCDEF0123 ciphertext.enc output.txt\n", progname);
}

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        print_help(argv[0]);
        return 1;
    }
    
    if ((strcmp(argv[1], "-h") == 0) || (strcmp(argv[1], "--help") == 0)) {
        print_help(argv[0]);
        return 0;
    }
    
    const char *mode = argv[1];
    const char *key_str = argv[2];
    const char *input_filename = argv[3];
    const char *output_filename = (argc == 5) ? argv[4] : "output";
    
    if (strcmp(mode, "encryption") != 0 && strcmp(mode, "decryption") != 0) {
        fprintf(stderr, "Error: Mode must be either 'encryption' or 'decryption'.\n");
        return 1;
    }
    
    unsigned char key[10];
    if (parse_key(key_str, key) != 0) {
        fprintf(stderr, "Error: Invalid key. Must be 20 hex digits representing 10 bytes.\n");
        return 1;
    }
    
    FILE *fin = fopen(input_filename, "rb");
    if (!fin) {
        fprintf(stderr, "Error: Cannot open input file: %s\n", input_filename);
        return 1;
    }
    
    FILE *fout = fopen(output_filename, "wb");
    if (!fout) {
        fprintf(stderr, "Error: Cannot open output file: %s\n", output_filename);
        fclose(fin);
        return 1;
    }
    
    int state[STATE_SIZE];
    int key_bits[KEY_BITS];
    int iv_bits[IV_BITS];
    unsigned char iv[10];
    
    /* Convert key to bit array */
    bytes_to_bits(key, 10, key_bits);
    
    if (strcmp(mode, "encryption") == 0) {
        /* Generate random IV */
        if (generate_random_bytes(iv, 10) != 0) {
            fprintf(stderr, "Error: Failed to generate random IV.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key, sizeof(key));
            return 1;
        }
        /* Write IV as the first 10 bytes of the output */
        if (fwrite(iv, 1, 10, fout) != 10) {
            fprintf(stderr, "Error: Failed to write IV to output file.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key, sizeof(key));
            return 1;
        }
        bytes_to_bits(iv, 10, iv_bits);
    } else {  // decryption
        /* Read IV from the input file */
        if (fread(iv, 1, 10, fin) != 10) {
            fprintf(stderr, "Error: Input file too short to contain IV.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(key, sizeof(key));
            return 1;
        }
        bytes_to_bits(iv, 10, iv_bits);
    }
    
    /* Initialize Trivium state with key and IV bits */
    trivium_init(state, key_bits, iv_bits);
    
    /* Process file in blocks */
    unsigned char buffer[BLOCK_SIZE];
    size_t bytes_read;
    while ((bytes_read = fread(buffer, 1, BLOCK_SIZE, fin)) > 0) {
        for (size_t i = 0; i < bytes_read; i++) {
            unsigned char ks_byte = get_keystream_byte(state);
            buffer[i] ^= ks_byte;
        }
        if (fwrite(buffer, 1, bytes_read, fout) != bytes_read) {
            fprintf(stderr, "Error: Failed to write data to output file.\n");
            fclose(fin);
            fclose(fout);
            secure_clear(state, sizeof(state));
            secure_clear(key, sizeof(key));
            return 1;
        }
    }
    
    if (ferror(fin)) {
        fprintf(stderr, "Error: Failed to read from input file.\n");
    }
    
    fclose(fin);
    fclose(fout);
    
    /* Clear sensitive data from memory */
    secure_clear(state, sizeof(state));
    secure_clear(key, sizeof(key));
    secure_clear(iv, sizeof(iv));
    secure_clear(key_bits, sizeof(key_bits));
    secure_clear(iv_bits, sizeof(iv_bits));
    
    fprintf(stdout, "%s complete. Output written to %s\n", mode, output_filename);
    return 0;
}
