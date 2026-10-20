#!/usr/bin/env bash
# build.sh — compile the envcheck test harness on Linux (gcc/clang).
#
#   ./build.sh            # builds ./report
#   ./build.sh clean      # removes build output
#
# On Windows use MSVC instead:
#   cl /O2 report.c envcheck.c
#
set -euo pipefail

CC="${CC:-cc}"
CFLAGS="${CFLAGS:--O2 -Wall -Wextra}"
OUT="report"
SRC="report.c envcheck.c"

if [ "${1:-}" = "clean" ]; then
    rm -f "$OUT" envcheck.o report.o
    echo "cleaned."
    exit 0
fi

echo "Compiling with: $CC $CFLAGS $SRC -o $OUT"
# shellcheck disable=SC2086
"$CC" $CFLAGS $SRC -o "$OUT"
echo "Built ./$OUT"
echo
echo "Run it:"
echo "  ./$OUT                 # full breakdown + score + percentage"
echo "  ./$OUT --json          # raw JSON report"
echo "  ./$OUT --sleep-skew    # also run the time-acceleration probe"
echo "  ./$OUT --no-backdoor   # skip the VMware I/O backdoor probe"
echo "  ./$OUT --no-ptrace     # skip the PTRACE_TRACEME self-probe"
