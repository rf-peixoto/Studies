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

if [ "${1:-}" = "clean" ]; then
    rm -f report guard envcheck.o report.o guard.o
    echo "cleaned."
    exit 0
fi

# 1) report  — prints the per-signal breakdown, scores and percentage.
echo "Compiling: $CC $CFLAGS report.c envcheck.c -o report"
# shellcheck disable=SC2086
"$CC" $CFLAGS report.c envcheck.c -o report

# 2) guard   — ENFORCEMENT example: self-deletes the binary and halts if the
#              combined score >= GUARD_THRESHOLD (default 7). Override at build
#              time, e.g.:  CFLAGS="-O2 -DGUARD_THRESHOLD=14" ./build.sh
echo "Compiling: $CC $CFLAGS guard.c envcheck.c -o guard"
# shellcheck disable=SC2086
"$CC" $CFLAGS guard.c envcheck.c -o guard

echo
echo "Built ./report and ./guard"
echo
echo "report (safe, read-only):"
echo "  ./report               # full breakdown + score + percentage"
echo "  ./report --json        # raw JSON report"
echo "  ./report --sleep-skew  # also run the time-acceleration probe"
echo "  ./report --no-backdoor # skip the VMware I/O backdoor probe"
echo "  ./report --no-ptrace   # skip the PTRACE_TRACEME self-probe"
echo
echo "guard (DESTRUCTIVE — deletes its own binary if score >= ${GUARD_THRESHOLD:-7}):"
echo "  GUARD_DRY_RUN=1 ./guard  # report what it WOULD do, delete nothing  <-- test first!"
echo "  ./guard                  # live: self-deletes + exits if tripped"
