#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>

/* FNV-1a is useful for demonstrations, NOT cryptographic integrity. */
int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s FILE\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 1; }
    uint64_t h = UINT64_C(14695981039346656037);
    unsigned char buffer[8192];
    size_t n;
    while ((n = fread(buffer,1,sizeof buffer,f)) > 0)
        for (size_t i = 0; i < n; ++i) {
            h ^= buffer[i];
            h *= UINT64_C(1099511628211);
        }
    if (ferror(f)) { perror("read"); fclose(f); return 1; }
    fclose(f);
    printf("FNV1a64: %016" PRIx64 "\n", h);
    return 0;
}
