# Build guide

## Linux (GCC or Clang)

```sh
make MODE=debug
make check MODE=debug
make MODE=release
make check MODE=release
make CC=clang MODE=release
```

The default Makefile builds each standalone example. It does not link all
examples together (each has a separate `main()`). The shared-library example
`09_exports.c` is omitted from `make all`.

## Windows PE using MinGW-w64

From Linux with MinGW-w64 installed:

```sh
make windows
```

On Windows from a MinGW-w64 shell:

```sh
mingw32-make CC=gcc EXE=.exe MODE=release
```

On Windows with MSVC, the examples can also be compiled individually where
they do not use GCC-specific attributes:

```bat
cl /nologo /std:c11 /O2 /W4 examples\01_flatten.c /Fe:01_flatten.exe
```

MSVC support is demonstrative; the Makefile targets GNU-compatible
toolchains. `10_entropy.c` needs the math library (`-lm` on many Unix
platforms). Some Windows SDK or compiler versions may not support `/std:c11`.

## Inspect the result

```sh
objdump -d build/release/01_flatten
readelf -S build/release/01_flatten
nm -D --defined-only libexample.so
make inspect
```

To build distinct diversification variants:

```sh
gcc -std=c11 -O2 -DBUILD_VARIANT=1 examples/12_diversify.c -o variant1
gcc -std=c11 -O2 -DBUILD_VARIANT=2 examples/12_diversify.c -o variant2
```

Compare outputs with `diff <(./variant1) <(./variant2)` in Bash.

## Important caveats

* Optimization can erase a source-level obfuscation entirely.
* LTO support depends on compiler/linker setup. If unavailable, remove
  `-flto` for a baseline build.
* `make strip` mutates the build outputs. Keep debug artifacts separately.
* Binary trust is not predicted by Shannon entropy alone.
* The integrity sample uses FNV-1a, not a cryptographic signature.
* The Windows build instructions have not been verified in this environment
  because MinGW-w64 is not installed.
