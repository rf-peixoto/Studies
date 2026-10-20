#include <stdint.h>
#include <stdio.h>

static uint32_t ordinary(uint32_t x) {
    if (x > 100u) return x * 3u;
    if (x > 50u) return x + 20u;
    return x ^ 0x55u;
}

static uint32_t flattened(uint32_t x) {
    enum { INITIAL, SECOND, MULTIPLY, ADD, XOR, FINISH } state = INITIAL;
    uint32_t result = 0;
    for (;;) {
        switch (state) {
        case INITIAL: state = x > 100u ? MULTIPLY : SECOND; break;
        case SECOND: state = x > 50u ? ADD : XOR; break;
        case MULTIPLY: result = x * 3u; state = FINISH; break;
        case ADD: result = x + 20u; state = FINISH; break;
        case XOR: result = x ^ 0x55u; state = FINISH; break;
        case FINISH: return result;
        default: return 0;
        }
    }
}

int main(void) {
    for (uint32_t x = 0; x < 256; ++x)
        if (ordinary(x) != flattened(x)) return 1;
    puts("flatten: equivalent for x=0..255");
    return 0;
}
