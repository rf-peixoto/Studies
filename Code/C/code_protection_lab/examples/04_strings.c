#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

static int decode(char *dst, size_t cap) {
    /* XOR encoding of PROPRIETARY, key 0x53; not cryptography. */
    static const uint8_t data[] = {
        0x03,0x01,0x1c,0x03,0x01,0x1a,0x16,0x07,0x12,0x01,0x0a
    };
    if (cap < sizeof data + 1u) return -1;
    for (size_t i = 0; i < sizeof data; ++i)
        dst[i] = (char)(data[i] ^ 0x53u);
    dst[sizeof data] = '\0';
    return 0;
}
int main(void) {
    char buffer[32];
    if (decode(buffer, sizeof buffer) != 0) return 1;
    puts(buffer);
    return 0;
}
