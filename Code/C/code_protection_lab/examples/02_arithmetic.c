#include <stdint.h>
#include <stdio.h>

static uint32_t add_alt(uint32_t a, uint32_t b) {
    return (a ^ b) + ((a & b) << 1);
}
static uint32_t sub_alt(uint32_t a, uint32_t b) {
    return ~(~a + b);
}
static uint32_t xor_alt(uint32_t a, uint32_t b) {
    return (a | b) & ~(a & b);
}
int main(void) {
    const uint32_t xs[] = {0, 1, 10, UINT32_MAX, 0xABCDEF01u};
    for (size_t i = 0; i < sizeof xs / sizeof *xs; i++)
        for (size_t j = 0; j < sizeof xs / sizeof *xs; j++) {
            uint32_t a = xs[i], b = xs[j];
            if (add_alt(a,b) != a+b || sub_alt(a,b) != a-b ||
                xor_alt(a,b) != (a^b)) return 1;
        }
    puts("arithmetic: identities confirmed");
    return 0;
}
