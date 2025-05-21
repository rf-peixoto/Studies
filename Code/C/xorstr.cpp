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
