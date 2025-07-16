/* ---------------
 * collect.c
 * ---------------
 * Build  : gcc -O2 -Wall collect.c -o collect
 * Run    : sudo ./collect <seconds> <outfile>
 *
 * Requires: /dev/cpu/0/msr from the msr-tools package
 *
 * Samples every 100 µs on core 0:
 *   ns_since_start | TSC | APERF | MPERF   (all uint64_t, little-endian)
 */
#define _GNU_SOURCE
#include <sched.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#include <stdio.h>
#include <fcntl.h>

static inline uint64_t rdtsc(void)
{
    unsigned lo, hi;
    __asm__ volatile("rdtsc" : "=a"(lo), "=d"(hi));
    return ((uint64_t)hi << 32) | lo;
}

static inline uint64_t rdmsr(int fd, uint32_t msr)
{
    uint64_t val;
    if (pread(fd, &val, sizeof val, msr) != sizeof val)
        return 0;
    return val;
}

int main(int argc, char **argv)
{
    if (argc != 3) { fprintf(stderr, "usage: %s <seconds> <outfile>\n", argv[0]); return 1; }
    int seconds = atoi(argv[1]);
    FILE *out   = fopen(argv[2], "wb");               if (!out)   { perror(argv[2]); return 1; }
    int   msrfd = open("/dev/cpu/0/msr", O_RDONLY);   if (msrfd < 0){ perror("open msr"); return 1; }

    cpu_set_t set; CPU_ZERO(&set); CPU_SET(0, &set);  /* pin to core 0           */
    sched_setaffinity(0, sizeof set, &set);

    struct timespec t0, t; clock_gettime(CLOCK_MONOTONIC_RAW, &t0);

    do {
        uint64_t ns     = ( (t.tv_sec - t0.tv_sec) * 1000000000ULL ) + (t.tv_nsec - t0.tv_nsec);
        uint64_t tsc    = rdtsc();
        uint64_t aperf  = rdmsr(msrfd, 0xE8);         /* IA32_APERF */
        uint64_t mperf  = rdmsr(msrfd, 0xE7);         /* IA32_MPERF */

        fwrite(&ns,   8, 1, out);
        fwrite(&tsc,  8, 1, out);
        fwrite(&aperf,8, 1, out);
        fwrite(&mperf,8, 1, out);

        usleep(100);                                  /* 100 µs ≈ 10 kHz */
        clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    } while (t.tv_sec - t0.tv_sec < seconds);

    fclose(out); close(msrfd); return 0;
}
