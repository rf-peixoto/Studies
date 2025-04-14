// gcc -Wall -Wextra -o elgamal elgamal.c -lcrypto

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <openssl/bn.h>
#include <openssl/rand.h>
#include <openssl/evp.h>

#define AES_KEY_LEN 32  // 256 bits
#define AES_IV_LEN 16   // 128-bit IV

// A 2048-bit prime from a well-known Diffie–Hellman group (RFC 3526, Group 14)
const char *p_hex = 
  "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E08"
  "8A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B"
  "302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9"
  "A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE6"
  "49286651ECE65381FFFFFFFFFFFFFFFF";

// Use generator g = 2 for this group.
const char *g_hex = "02";

// Structure to hold ElGamal key parameters.
typedef struct {
    BIGNUM *p;  // large prime
    BIGNUM *g;  // generator
    BIGNUM *x;  // private key
    BIGNUM *h;  // public key (h = g^x mod p)
} ELGAMAL_KEY;

// Error handling function.
void handleErrors(const char *msg) {
    fprintf(stderr, "%s\n", msg);
    exit(EXIT_FAILURE);
}

// Generate an ElGamal key pair using OpenSSL’s BIGNUM functions.
ELGAMAL_KEY* elgamal_generate_key(void) {
    ELGAMAL_KEY *key = malloc(sizeof(ELGAMAL_KEY));
    if (!key) handleErrors("Memory allocation error");

    BN_CTX *ctx = BN_CTX_new();
    if (!ctx) handleErrors("Failed to create BN_CTX");

    key->p = BN_new();
    key->g = BN_new();
    key->x = BN_new();
    key->h = BN_new();
    if (!key->p || !key->g || !key->x || !key->h)
        handleErrors("Failed to allocate BIGNUMs");

    if (!BN_hex2bn(&key->p, p_hex))
        handleErrors("Failed to initialize prime p");
    if (!BN_hex2bn(&key->g, g_hex))
        handleErrors("Failed to initialize generator g");

    // Generate private key x randomly in the range [2, p-2]
    BIGNUM *p_minus_two = BN_dup(key->p);
    BN_sub_word(p_minus_two, 2);
    if (!BN_rand_range(key->x, p_minus_two))
        handleErrors("Failed to generate private key x");
    BN_add_word(key->x, 2);  // ensure x >= 2

    // Compute public key h = g^x mod p.
    if (!BN_mod_exp(key->h, key->g, key->x, key->p, ctx))
        handleErrors("Failed to compute public key h");

    BN_free(p_minus_two);
    BN_CTX_free(ctx);
    return key;
}

// ElGamal encryption: encrypt a symmetric key (as a BIGNUM) using the public key.
// Outputs c1 and c2.
int elgamal_encrypt(BIGNUM *sym_key, ELGAMAL_KEY *pub, BIGNUM **out_c1, BIGNUM **out_c2) {
    BN_CTX *ctx = BN_CTX_new();
    if (!ctx) return 0;

    BIGNUM *y = BN_new();
    BIGNUM *p_minus_two = BN_dup(pub->p);
    if (!y || !p_minus_two) return 0;
    BN_sub_word(p_minus_two, 2);

    // Choose ephemeral key y ∈ [2, p-2]
    if (!BN_rand_range(y, p_minus_two))
        handleErrors("Failed to generate ephemeral key y");
    BN_add_word(y, 2);

    *out_c1 = BN_new();
    *out_c2 = BN_new();
    if (!*out_c1 || !*out_c2) return 0;

    // Compute c1 = g^y mod p
    if (!BN_mod_exp(*out_c1, pub->g, y, pub->p, ctx))
        return 0;

    // Compute shared secret s = h^y mod p
    BIGNUM *s = BN_new();
    if (!s) return 0;
    if (!BN_mod_exp(s, pub->h, y, pub->p, ctx))
        return 0;

    // Compute c2 = (sym_key * s) mod p
    if (!BN_mod_mul(*out_c2, sym_key, s, pub->p, ctx))
        return 0;

    BN_free(s);
    BN_free(y);
    BN_free(p_minus_two);
    BN_CTX_free(ctx);
    return 1;
}

// ElGamal decryption: recover the symmetric key given c1 and c2.
int elgamal_decrypt(BIGNUM *sym_key_out, BIGNUM *c1, BIGNUM *c2, ELGAMAL_KEY *priv) {
    BN_CTX *ctx = BN_CTX_new();
    if (!ctx) return 0;

    // Compute shared secret s = c1^x mod p.
    BIGNUM *s = BN_new();
    if (!s) return 0;
    if (!BN_mod_exp(s, c1, priv->x, priv->p, ctx))
        return 0;

    // Compute the inverse of s mod p.
    BIGNUM *s_inv = BN_mod_inverse(NULL, s, priv->p, ctx);
    if (!s_inv) return 0;

    // Recover symmetric key: sym_key_out = (c2 * s_inv) mod p.
    if (!BN_mod_mul(sym_key_out, c2, s_inv, priv->p, ctx))
        return 0;

    BN_free(s);
    BN_free(s_inv);
    BN_CTX_free(ctx);
    return 1;
}

// Derive a 256-bit key from a BIGNUM by applying SHA-256 over its binary representation.
int derive_key_from_bn(BIGNUM *bn, unsigned char *key, int key_len) {
    int bn_len = BN_num_bytes(bn);
    unsigned char *bn_bin = malloc(bn_len);
    if (!bn_bin) return 0;
    BN_bn2bin(bn, bn_bin);

    EVP_MD_CTX *mdctx = EVP_MD_CTX_new();
    if (!mdctx) return 0;
    if (1 != EVP_DigestInit_ex(mdctx, EVP_sha256(), NULL))
        return 0;
    if (1 != EVP_DigestUpdate(mdctx, bn_bin, bn_len))
        return 0;
    unsigned int digest_len;
    if (1 != EVP_DigestFinal_ex(mdctx, key, &digest_len))
        return 0;
    EVP_MD_CTX_free(mdctx);
    free(bn_bin);
    return (digest_len == key_len);
}

// Encrypt file data with AES-256-CBC using the provided key and IV.
int aes_encrypt_file(const char *in_filename, const char *out_filename,
                     unsigned char *key, unsigned char *iv) {
    FILE *fin = fopen(in_filename, "rb");
    if (!fin) return 0;
    FILE *fout = fopen(out_filename, "wb");
    if (!fout) { fclose(fin); return 0; }

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;
    if (1 != EVP_EncryptInit_ex(ctx, EVP_aes_256_cbc(), NULL, key, iv))
        return 0;

    unsigned char inbuf[1024];
    unsigned char outbuf[1024 + EVP_CIPHER_block_size(EVP_aes_256_cbc())];
    int inlen, outlen;
    while ((inlen = fread(inbuf, 1, sizeof(inbuf), fin)) > 0) {
        if (1 != EVP_EncryptUpdate(ctx, outbuf, &outlen, inbuf, inlen))
            return 0;
        fwrite(outbuf, 1, outlen, fout);
    }
    if (1 != EVP_EncryptFinal_ex(ctx, outbuf, &outlen))
        return 0;
    fwrite(outbuf, 1, outlen, fout);

    EVP_CIPHER_CTX_free(ctx);
    fclose(fin);
    fclose(fout);
    return 1;
}

// Decrypt file data with AES-256-CBC using the provided key and IV.
int aes_decrypt_file(const char *in_filename, const char *out_filename,
                     unsigned char *key, unsigned char *iv) {
    FILE *fin = fopen(in_filename, "rb");
    if (!fin) return 0;
    FILE *fout = fopen(out_filename, "wb");
    if (!fout) { fclose(fin); return 0; }

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;
    if (1 != EVP_DecryptInit_ex(ctx, EVP_aes_256_cbc(), NULL, key, iv))
        return 0;

    unsigned char inbuf[1024];
    unsigned char outbuf[1024 + EVP_CIPHER_block_size(EVP_aes_256_cbc())];
    int inlen, outlen;
    while ((inlen = fread(inbuf, 1, sizeof(inbuf), fin)) > 0) {
        if (1 != EVP_DecryptUpdate(ctx, outbuf, &outlen, inbuf, inlen))
            return 0;
        fwrite(outbuf, 1, outlen, fout);
    }
    if (1 != EVP_DecryptFinal_ex(ctx, outbuf, &outlen))
        return 0;
    fwrite(outbuf, 1, outlen, fout);

    EVP_CIPHER_CTX_free(ctx);
    fclose(fin);
    fclose(fout);
    return 1;
}

// Main function demonstrating the hybrid encryption scheme.
// Usage:
//   To encrypt:   ./program -e filename
//   To decrypt:   ./program -d filename
//
// During encryption, the output is split into two files:
//   - output.header : Contains the ElGamal ciphertext (for the symmetric key) and the IV.
//   - output.enc    : Contains the AES-encrypted file data.
int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s -e|-d filename\n", argv[0]);
        return EXIT_FAILURE;
    }
    int mode_encrypt = 0, mode_decrypt = 0;
    if (strcmp(argv[1], "-e") == 0)
        mode_encrypt = 1;
    else if (strcmp(argv[1], "-d") == 0)
        mode_decrypt = 1;
    else {
        fprintf(stderr, "Invalid option. Use -e for encryption or -d for decryption.\n");
        return EXIT_FAILURE;
    }

    // Generate a new ElGamal key pair.
    ELGAMAL_KEY *el_key = elgamal_generate_key();

    if (mode_encrypt) {
        // Generate a 256-bit symmetric key and a 128-bit IV using a secure random generator.
        unsigned char sym_key[AES_KEY_LEN];
        unsigned char iv[AES_IV_LEN];
        if (1 != RAND_bytes(sym_key, AES_KEY_LEN))
            handleErrors("Failed to generate symmetric key");
        if (1 != RAND_bytes(iv, AES_IV_LEN))
            handleErrors("Failed to generate IV");

        // Convert the symmetric key into a BIGNUM.
        BIGNUM *sym_bn = BN_bin2bn(sym_key, AES_KEY_LEN, NULL);
        if (!sym_bn)
            handleErrors("Failed to convert symmetric key to BIGNUM");

        // Encrypt the symmetric key with ElGamal.
        BIGNUM *c1 = NULL, *c2 = NULL;
        if (!elgamal_encrypt(sym_bn, el_key, &c1, &c2))
            handleErrors("ElGamal encryption of symmetric key failed");

        // (Optional) Derive a fixed-length key from one of the ciphertext components.
        // In this example the symmetric key generated above is used directly for AES encryption.

        // Encrypt the file data with AES-256-CBC.
        const char *out_filename = "output.enc";
        if (!aes_encrypt_file(argv[2], out_filename, sym_key, iv))
            handleErrors("AES encryption of file failed");

        // Write header information (ElGamal ciphertext and IV) to a header file.
        FILE *hdr = fopen("output.header", "wb");
        if (!hdr)
            handleErrors("Failed to create header file");

        int c1_len = BN_num_bytes(c1);
        int c2_len = BN_num_bytes(c2);
        fwrite(&c1_len, sizeof(int), 1, hdr);
        unsigned char *c1_bin = malloc(c1_len);
        BN_bn2bin(c1, c1_bin);
        fwrite(c1_bin, 1, c1_len, hdr);
        fwrite(&c2_len, sizeof(int), 1, hdr);
        unsigned char *c2_bin = malloc(c2_len);
        BN_bn2bin(c2, c2_bin);
        fwrite(c2_bin, 1, c2_len, hdr);
        fwrite(iv, 1, AES_IV_LEN, hdr);
        fclose(hdr);
        free(c1_bin);
        free(c2_bin);

        printf("Encryption completed.\nGenerated files: output.header and output.enc\n");

        BN_free(sym_bn);
        BN_free(c1);
        BN_free(c2);
    } else if (mode_decrypt) {
        // Read the header file to obtain the ElGamal ciphertext and IV.
        FILE *hdr = fopen("output.header", "rb");
        if (!hdr)
            handleErrors("Failed to open header file");

        int c1_len, c2_len;
        fread(&c1_len, sizeof(int), 1, hdr);
        unsigned char *c1_bin = malloc(c1_len);
        fread(c1_bin, 1, c1_len, hdr);
        fread(&c2_len, sizeof(int), 1, hdr);
        unsigned char *c2_bin = malloc(c2_len);
        fread(c2_bin, 1, c2_len, hdr);
        unsigned char iv[AES_IV_LEN];
        fread(iv, 1, AES_IV_LEN, hdr);
        fclose(hdr);

        // Convert the binary data back into BIGNUMs.
        BIGNUM *c1 = BN_bin2bn(c1_bin, c1_len, NULL);
        BIGNUM *c2 = BN_bin2bn(c2_bin, c2_len, NULL);
        free(c1_bin);
        free(c2_bin);

        // Decrypt the symmetric key using the ElGamal private key.
        BIGNUM *sym_bn = BN_new();
        if (!elgamal_decrypt(sym_bn, c1, c2, el_key))
            handleErrors("ElGamal decryption failed");

        // Convert the recovered BIGNUM into a 256-bit symmetric key.
        unsigned char sym_key[AES_KEY_LEN];
        int bn_size = BN_num_bytes(sym_bn);
        if (bn_size > AES_KEY_LEN)
            handleErrors("Recovered symmetric key size is larger than expected");
        memset(sym_key, 0, AES_KEY_LEN);
        BN_bn2bin(sym_bn, sym_key + (AES_KEY_LEN - bn_size));

        // Decrypt the AES-encrypted file.
        const char *out_filename = "output.dec";
        if (!aes_decrypt_file("output.enc", out_filename, sym_key, iv))
            handleErrors("AES decryption failed");

        printf("Decryption completed.\nOutput file: %s\n", out_filename);

        BN_free(c1);
        BN_free(c2);
        BN_free(sym_bn);
    }

    // Clean up ElGamal key components.
    BN_free(el_key->p);
    BN_free(el_key->g);
    BN_free(el_key->x);
    BN_free(el_key->h);
    free(el_key);

    return EXIT_SUCCESS;
}
