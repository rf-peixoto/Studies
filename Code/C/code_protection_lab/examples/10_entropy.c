#include <stdint.h>
#include <stdio.h>
#include <math.h>
#include <string.h>

static double entropy(const uint8_t *data, size_t length) {
    size_t frequencies[256] = {0};
    if (!data || !length) return 0.0;
    for (size_t i = 0; i < length; ++i) ++frequencies[data[i]];
    double h = 0.0;
    for (size_t i = 0; i < 256; ++i)
        if (frequencies[i]) {
            double p = (double)frequencies[i] / (double)length;
            h -= p * log2(p);
        }
    return h;
}
int main(int argc, char **argv) {
    if (argc == 1) {
        const uint8_t example[] = {0,0,0,0,1,1,1,1};
        printf("example entropy: %.6f bits/byte\n", entropy(example,sizeof example));
        return 0;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 1; }
    size_t hist[256] = {0};
    uint8_t buffer[8192];
    size_t total = 0, n;
    while ((n = fread(buffer,1,sizeof buffer,f)) != 0) {
        if (n > SIZE_MAX - total) { fclose(f); return 1; }
        total += n;
        for (size_t i = 0; i < n; ++i) ++hist[buffer[i]];
    }
    if (ferror(f)) { perror("read"); fclose(f); return 1; }
    fclose(f);
    double h = 0.0;
    for (size_t i = 0; i < 256; ++i)
        if (hist[i]) {
            double p = (double)hist[i] / (double)total;
            h -= p * log2(p);
        }
    printf("%s: %zu bytes, %.6f bits/byte\n", argv[1], total, h);
    return 0;
}
