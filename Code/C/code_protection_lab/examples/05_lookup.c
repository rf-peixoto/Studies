#include <stdint.h>
#include <stdio.h>

static const uint8_t times_seven[16] = {
    0,7,14,21,28,35,42,49,56,63,70,77,84,91,98,105
};
static uint8_t table_multiply(uint8_t x) {
    return times_seven[x & 15u];
}
int main(void) {
    for (unsigned i = 0; i < 256; ++i)
        if (table_multiply((uint8_t)i) != (uint8_t)((i & 15u) * 7u))
            return 1;
    puts("lookup table: verified");
    return 0;
}
