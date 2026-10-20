#include <stdint.h>
#include <stdio.h>
#if defined(_MSC_VER)
# define FORCE_INLINE __forceinline
# define NO_INLINE __declspec(noinline)
#elif defined(__GNUC__) || defined(__clang__)
# define FORCE_INLINE inline __attribute__((always_inline))
# define NO_INLINE __attribute__((noinline))
#else
# define FORCE_INLINE inline
# define NO_INLINE
#endif
static FORCE_INLINE uint32_t mix(uint32_t x) {
    x ^= x >> 13;
    x *= 0x85EBCA6Bu;
    return x ^ (x >> 16);
}
static NO_INLINE uint32_t outer(uint32_t x) {
    return mix(x) ^ 0x12345678u;
}
int main(void) {
    printf("inline/outlining hint: 0x%08x\n", (unsigned)outer(42));
    return 0;
}
