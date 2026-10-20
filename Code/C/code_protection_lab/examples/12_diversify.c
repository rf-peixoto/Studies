#include <stdint.h>
#include <stdio.h>

/* BUILD_VARIANT selects two equivalent formulations. */
static uint32_t transform(uint32_t x) {
#if BUILD_VARIANT == 2
    x = (x ^ 0xA5A5A5A5u);
    return (x ^ 0x5A5A5A5Au) + 101u;
#else
    return (~x) + 101u;
#endif
}
int main(void) {
    const uint32_t inputs[] = {0u, 1u, 13u, UINT32_MAX};
    for (size_t i=0; i<sizeof inputs/sizeof inputs[0]; ++i)
        printf("%u\n", (unsigned)transform(inputs[i]));
    return 0;
}
