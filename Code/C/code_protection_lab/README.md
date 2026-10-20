# Code Protection Lab

Portable C11 demonstrations for Linux ELF and Windows PE. Build with `make`, `make CC=clang`, or `make windows` with MinGW-w64 installed. Run `make check` to execute Linux builds. `make MODE=debug` retains symbols; release defaults to `-O2 -flto` and `-DNDEBUG`. `make strip` strips release binaries (keep separate debug symbols). `make inspect` shows binary metadata.

All examples are independent executables under `examples/`. `09_exports.c` is a shared-library example and is built separately. These are educational transformations, not strong confidentiality or antivirus-trust guarantees. No runtime executable decryption or anti-analysis behavior is included.

| File | Subject |
|---|---|
| 01_flatten.c | control-flow flattening |
| 02_arithmetic.c | arithmetic substitution |
| 03_opaque.c | opaque predicates and bogus control flow |
| 04_strings.c | encoded string constant |
| 05_lookup.c | lookup tables |
| 06_dispatch.c | function-pointer dispatch |
| 07_vm.c | stack bytecode interpreter |
| 08_inline.c | function inlining and outlining hints |
| 09_exports.c | explicit DLL/SO exports |
| 10_entropy.c | whole-file Shannon entropy measurement |
| 11_integrity.c | non-cryptographic file integrity checksum |
| 12_diversify.c | equivalent implementation variants |
| 13_vm_advanced.c | register VM with branches and bounds checks |
| 14_state_machine.c | transition-table parser |

Compile the library example on Linux:

`gcc -std=c11 -O2 -fPIC -fvisibility=hidden -shared examples/09_exports.c -o libexample.so`

Compile for Windows with MinGW-w64:

`x86_64-w64-mingw32-gcc -std=c11 -O2 -shared examples/09_exports.c -o example.dll`

Use `objdump -d` and a decompiler to verify which transformations actually survive optimization. Simple XOR strings, opaque predicates, and homegrown VM instructions are recoverable. Never embed private keys or assume these examples secure credentials.
