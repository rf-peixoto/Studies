// Compiletime Example:

constexpr char XOR_KEY = 0x5A;  // Example key
constexpr size_t N = /* length of string including null */;

struct EncStr {
    char data[N];
    constexpr EncStr(const char* plain) : data{} {
        // Encrypt at compile time
        for (size_t i = 0; i < N; ++i) {
            data[i] = plain[i] ^ XOR_KEY;
        }
    }
    // Decrypt at runtime (when accessed)
    std::string decrypt() const {
        std::string result;
        result.resize(N);
        for (size_t i = 0; i < N; ++i) {
            result[i] = data[i] ^ XOR_KEY;
        }
        return result;
    }
};

// Usage
constexpr EncStr secret("Hello World!");
// 'secret.data' is stored encrypted in the binary, 
// and secret.decrypt() returns the plaintext at runtime.


// Simple XOR:

// Encrypt or decrypt a buffer in-place using XOR key
void xor_cipher(char *data, size_t len, unsigned char key) {
    for (size_t i = 0; i < len; ++i) {
        data[i] ^= key;
    }
}
...
// Usage:
char secret[] = "SensitiveInfo";
size_t len = strlen(secret);
xor_cipher(secret, len, 0x5A);   // Encrypt the string (now secret is obfuscated)
printf("%s\n", secret);         // Would print gibberish
xor_cipher(secret, len, 0x5A);   // Decrypt back to original

// XTEA:

#include <stdint.h>
void xtea_encrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0=v[0], v1=v[1]; 
    uint32_t sum=0, delta=0x9e3779b9;
    for (unsigned i = 0; i < 32; ++i) {          // 64 rounds
        v0 += (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[sum & 3]);
        sum += delta;
        v1 += (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum>>11) & 3]);
    }
    v[0]=v0; v[1]=v1;
}
void xtea_decrypt(uint32_t v[2], const uint32_t key[4]) {
    uint32_t v0=v[0], v1=v[1];
    uint32_t delta=0x9e3779b9, sum=delta*32;
    for (unsigned i = 0; i < 32; ++i) {          // 64 rounds
        v1 -= (((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum>>11) & 3]);
        sum -= delta;
        v0 -= (((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[sum & 3]);
    }
    v[0]=v0; v[1]=v1;
}


// Libsodium:

unsigned char key[crypto_secretbox_KEYBYTES];
unsigned char nonce[crypto_secretbox_NONCEBYTES];
unsigned char ciphertext[crypto_secretbox_MACBYTES + message_len];
// (In an offline tool or at init)
crypto_secretbox_keygen(key);                     // generate a random key
randombytes_buf(nonce, sizeof nonce);             // random nonce
crypto_secretbox_easy(ciphertext, message, message_len, nonce, key);  // encrypt
// ... store `ciphertext` and `nonce` in the program ...

// (At runtime)
unsigned char decrypted[message_len];
if (crypto_secretbox_open_easy(decrypted, ciphertext, sizeof ciphertext, nonce, key) != 0) {
    // decryption failed (e.g., data tampered)
}

