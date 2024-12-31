#!/bin/bash
#
# Script Name: secure_compile.sh
# Purpose:
#   1) Convert a Bash script into an ELF binary using shc.
#   2) Inject a simple anti-debugging function (ptrace usage).
#   3) Compile with compiler hardening flags.
#   4) Strip the symbols from the ELF.
#   5) Pack the ELF using UPX with best compression.
#      - Optional repeated packing if specified.
#
# Requirements:
#   - shc (https://neurobin.org/projects/software/shell/shc/)
#   - gcc
#   - strip
#   - upx (https://upx.github.io/)
#
# Usage:
#   ./secure_compile.sh <source_script> <optional_output_binary_name> <optional_pack_times>
#
# Example:
#   ./secure_compile.sh myscript.sh mybinary 2
#
#   1) Compiles myscript.sh into an ELF with anti-debug checks.
#   2) Strips symbols.
#   3) Compresses the binary with UPX twice.
#
# NOTES:
#   - This script attempts to modify the generated C code from shc to insert an anti-debugging call.
#     It does so by searching for a brace ("{") in the main function, then injecting a function call.
#     This method is approximate and may require adjustment if shc's output changes.
#   - The anti-debugging measure is minimal and easily bypassed by advanced methods.
#   - The hardened flags reduce some exploitability but do not prevent static analysis.

# Color definitions for status messages
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

# Check for required tools
for tool in shc gcc strip upx; do
  if ! command -v "${tool}" &> /dev/null; then
    echo -e "${RED}Error: '${tool}' is not installed or not in PATH.${RESET}"
    exit 1
  fi
done

# Check arguments
if [ $# -lt 1 ]; then
  echo -e "${YELLOW}Usage: $0 <source_script> <optional_output_binary_name> <optional_pack_times>${RESET}"
  exit 1
fi

SOURCE_SCRIPT="$1"
if [ ! -f "$SOURCE_SCRIPT" ]; then
  echo -e "${RED}Error: File '$SOURCE_SCRIPT' not found.${RESET}"
  exit 1
fi

# Output binary name defaults to the source script name (without .sh)
if [ -n "$2" ]; then
  OUTPUT_BIN="$2"
else
  OUTPUT_BIN="$(basename "$SOURCE_SCRIPT" .sh)"
fi

# Number of UPX pack iterations (default 1, can be overridden)
PACK_TIMES=1
if [ -n "$3" ]; then
  PACK_TIMES="$3"
fi

echo -e "${GREEN}==> Compiling '${SOURCE_SCRIPT}' into C code with shc...${RESET}"
# -r : keep the generated .x.c file
# -f : input file
# -o : specify output file name
shc -r -f "$SOURCE_SCRIPT" -o "${OUTPUT_BIN}"
if [ $? -ne 0 ]; then
  echo -e "${RED}Error: shc compilation failed.${RESET}"
  exit 1
fi

# The generated C file (e.g. myscript.sh.x.c)
GENERATED_C_FILE="${SOURCE_SCRIPT}.x.c"
if [ ! -f "$GENERATED_C_FILE" ]; then
  echo -e "${RED}Error: Generated C file '${GENERATED_C_FILE}' not found.${RESET}"
  exit 1
fi

echo -e "${GREEN}==> Injecting anti-debugging function into '${GENERATED_C_FILE}'...${RESET}"
# Insert the needed #include <sys/ptrace.h> at the top (line 1).
# Then insert a static inline function for anti_debug after that.
# Finally, insert a call to 'anti_debug();' inside the main function body.
sed -i '1i #include <sys/ptrace.h>\n\nstatic inline void anti_debug(void) {\n    ptrace(PTRACE_TRACEME, 0, 1, 0);\n}\n' "$GENERATED_C_FILE"

# Attempt to find the first opening brace '{' after the 'main' definition
# and inject our function call. This is a simplistic approach.
sed -i '0,/{/s//{\n    anti_debug();/' "$GENERATED_C_FILE"

echo -e "${GREEN}==> Compiling '${GENERATED_C_FILE}' with hardened flags...${RESET}"
# Common hardened flags:
#   -fstack-protector-strong : Stack canary protections
#   -D_FORTIFY_SOURCE=2      : Automatic checks on unsafe functions
#   -Wl,-z,relro,-z,now      : Read-only relocations, lazy binding disabled
gcc -o "${OUTPUT_BIN}" -fstack-protector-strong -D_FORTIFY_SOURCE=2 -Wl,-z,relro -Wl,-z,now -O2 "${GENERATED_C_FILE}"
if [ $? -ne 0 ]; then
  echo -e "${RED}Error: GCC compilation failed.${RESET}"
  exit 1
fi

echo -e "${GREEN}==> Stripping symbols from the ELF binary...${RESET}"
strip "${OUTPUT_BIN}"

echo -e "${GREEN}==> Packing ELF with UPX...${RESET}"
for i in $(seq 1 "$PACK_TIMES"); do
  echo -e "${YELLOW}   -> UPX pass $i/${PACK_TIMES}${RESET}"
  upx -qq --no-time --best --ultra-brute "${OUTPUT_BIN}"
  if [ $? -ne 0 ]; then
    echo -e "${RED}Error: UPX compression failed on pass $i.${RESET}"
    exit 1
  fi
done

echo -e "${GREEN}Process complete. The compiled and packed ELF binary is: '${OUTPUT_BIN}'${RESET}"
exit 0
