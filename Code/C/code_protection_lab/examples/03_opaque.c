#include <stdint.h>
#include <stdio.h>

static int always_true(uint32_t x) {
    /* Consecutive integers: one must be even. Unsigned wrap is defined. */
    return ((x * (x + 1u)) & 1u) == 0u;
}
static uint32_t normal(uint32_t x) { return x * 7u + 13u; }
static uint32_t transformed(uint32_t x) {
    if (always_true(x)) return x * 7u + 13u;
    return x ^ 0xDEADBEEFu; /* unreachable branch */
}
int main(void) {
    uint32_t x = 0x12345678u;
    for (unsigned i = 0; i < 100000; ++i) {
        x = x * 1664525u + 1013904223u;
        if (transformed(x) != normal(x)) return 1;
    }
    puts("opaque predicate: verified");
    return 0;
}
