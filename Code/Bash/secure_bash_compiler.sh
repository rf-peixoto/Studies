#!/bin/bash
#
# Script Name: elf_packer.sh
# Purpose:    1) Compile a Bash script to an ELF using shc
#             2) Strip the symbols
#             3) Pack the ELF using UPX
# Requirements:
#   - shc (https://neurobin.org/projects/software/shell/shc/)
#   - upx (https://upx.github.io/)
#
# Usage:
#   ./elf_packer.sh <source_script> <optional_output_binary_name>
#
# Example:
#   ./elf_packer.sh myscript.sh mypacked
#
# This script will:
#   1. Compile myscript.sh into an ELF.
#   2. Strip the ELF of its symbols.
#   3. Pack the ELF using UPX with best compression options.
#
# Security Flags:
#   shc:
#     -e  <date> : Expire compiled binary on a given date (YYYY/MM/DD)
#     -m  <msg>  : Print a message when the compiled file expires
#   upx:
#     --best        : Maximum compression
#     --ultra-brute : Tries all available compression methods

# Color definitions for simple status messages
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

# Verify that shc and upx are installed
if ! command -v shc &> /dev/null; then
  echo -e "${RED}Error: shc is not installed or not in PATH.${RESET}"
  exit 1
fi

if ! command -v upx &> /dev/null; then
  echo -e "${RED}Error: upx is not installed or not in PATH.${RESET}"
  exit 1
fi

# Check for input parameters
if [ $# -lt 1 ]; then
  echo -e "${YELLOW}Usage: $0 <source_script> <optional_output_binary_name>${RESET}"
  exit 1
fi

SOURCE_SCRIPT="$1"
if [ ! -f "$SOURCE_SCRIPT" ]; then
  echo -e "${RED}Error: File $SOURCE_SCRIPT not found.${RESET}"
  exit 1
fi

if [ -n "$2" ]; then
  OUTPUT_BIN="$2"
else
  # Use the same base name as the source script if no output name is specified
  OUTPUT_BIN="$(basename "$SOURCE_SCRIPT" .sh)"
fi

echo -e "${GREEN}Compiling $SOURCE_SCRIPT into an ELF binary using shc...${RESET}"
# Example with optional flags for demonstration (comment out or adjust as needed):
#   -e 2025/01/01   (expire compiled binary after 2025-01-01)
#   -m "Expired."   (message shown after expiration)
shc -f "$SOURCE_SCRIPT" -o "$OUTPUT_BIN"
if [ $? -ne 0 ]; then
  echo -e "${RED}Error: shc compilation failed.${RESET}"
  exit 1
fi

# Strip symbols to minimize metadata in the compiled ELF
echo -e "${GREEN}Stripping symbols from the ELF binary...${RESET}"
strip "$OUTPUT_BIN"

# Use UPX to compress the binary with best compression level
echo -e "${GREEN}Packing ELF with UPX (best compression, ultra brute mode)...${RESET}"
upx --best --ultra-brute "$OUTPUT_BIN"
if [ $? -ne 0 ]; then
  echo -e "${RED}Error: UPX compression failed.${RESET}"
  exit 1
fi

echo -e "${GREEN}Process complete. The compiled and packed ELF binary is: $OUTPUT_BIN${RESET}"
exit 0
