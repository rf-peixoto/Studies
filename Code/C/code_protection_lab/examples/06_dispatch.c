#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

typedef uint32_t (*op_t)(uint32_t);
static uint32_t a(uint32_t x) { return x * 3u; }
static uint32_t b(uint32_t x) { return x ^ 0xAA55u; }
static uint32_t c(uint32_t x) { return x + 100u; }
static const op_t dispatch[] = {a,b,c};
static int run(size_t index, uint32_t x, uint32_t *out) {
    if (out == NULL || index >= sizeof dispatch / sizeof *dispatch) return -1;
    *out = dispatch[index](x);
    return 0;
}
int main(void) {
    uint32_t out;
    if (run(1, 0x1234u, &out) != 0) return 1;
    printf("dispatch: 0x%08x\n", (unsigned)out);
    return 0;
}
