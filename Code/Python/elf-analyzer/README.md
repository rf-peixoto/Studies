# elfanalyzer

A modular framework for analyzing ELF files. It grew out of a checklist of the
usual tools (`readelf`, `objdump`, `strace`, `gdb`, `tcpdump`, ...) and turns
them into one driver that produces a structured JSON report plus a scored
terminal summary.

**Static analysis is the default and never executes the sample.** Dynamic
capture, the interactive syscall gate, and gdb all *run* the binary and are
opt-in behind flags. Run those on samples you don't trust only inside a VM or a
disposable container.

## Install

```bash
./install.sh            # creates .venv and installs pyelftools + python-ptrace
./start.sh --check-tools   # shows which external tools are present / missing
```

External CLI tools are detected at runtime. Missing ones are reported with the
exact `apt-get` line for **Debian trixie**; stages that need a missing tool are
skipped (and the skip is recorded in the report). Install everything with:

```bash
sudo apt-get install -y binutils file strace ltrace tcpdump gdb binwalk upx-ucl
```

## Usage

```bash
./start.sh <elf>                    # static analysis (safe, default)
./start.sh <elf> --mitigations      # add checksec-style mitigation report
./start.sh <elf> --entropy-check    # block-by-block entropy map (table)
./start.sh <elf> --disasm           # disassembly-based signals
./start.sh <elf> --only strings,imports     # run a subset of static stages
./start.sh <elf> --dynamic -y       # strace + ltrace (executes the sample)
./start.sh <elf> --netsim -y        # fake network services (executes the sample)
./start.sh <elf> --dynamic --tcpdump --memdump --timeout 30
./start.sh <elf> --supervise        # interactive syscall gate (executes it!)
./start.sh <elf> --gdb              # drop into gdb with sane defaults
./start.sh <elf> --all              # everything, interactive
./start.sh --batch ./samples        # static sweep of a directory
```

`--args ...` (last on the line) passes arguments through to the sample for the
dynamic/interactive stages. `-y/--yes` skips the "are you sure you want to
execute this" prompts. `--install-deps` apt-installs missing tools without
asking.

## The syscall gate (`--supervise`)

This is the "run it like a debugger and veto actions before they happen" mode.
The target runs under `ptrace`; the framework stops at **every interesting
system call before the kernel executes it** and shows you what it is about to
do, decoded:

```
  [NETWORK] connect(sockfd=3, addr=<sockaddr_in sin_port=4444, sin_addr=185.220.101.47>, addrlen=16)
    [a]llow  [d]rop  [A]llow-all-this-class  [D]rop-all-this-class
    [g]allow-all-remaining  [q]uit(kill target)
```

Choosing **drop** neutralizes the call: the syscall number is rewritten to an
invalid one so the kernel never runs it, and a clean error (e.g. `EACCES`) is
returned to the program instead of letting it crash. So you can let a sample run
but block it from phoning home, spawning a shell, or writing to disk, and watch
what it does without those actions. "Interesting" syscalls are network, exec,
process control (incl. `ptrace`), file-modifying, memory-protection, and
privilege calls; everything else is auto-allowed so the program runs at speed.

Standing decisions are remembered (drop every `connect`, allow all file writes,
etc.). Requires `python-ptrace` and a Linux x86-64 / aarch64 host.

## The entropy map (`--entropy-check`)

Splits the file into fixed-size blocks ("sectors") and computes Shannon entropy
(0–8 bits/byte) for each, then prints a table with a color bar:

```
 offset        entropy  level
 0x00000000  ··································  0.00   <- null padding
 0x00001000  ████████████████████████████████··  7.58   <- random/encrypted
 0x00002000  ███████████████████···············  4.49   <- ASCII text
 legend: low  structured  dense  >=7.2 packed/encrypted
```

Blocks at or above 7.2 bits/byte are compressed/encrypted/packed data; a flat 0
is padding; code and text sit in the middle. Sustained high-entropy runs become
findings (with their offset range and share of the file), so appended payloads
and whole-file packing stand out at the raw byte level — independent of the ELF
section view. Block size auto-scales to the file so the table stays readable;
override it with `--block-size N` (e.g. `--block-size 512` for disk-sector
granularity). The full per-block series is always in `report.json`.

## Malformed-ELF hardening (`robustness`, default)

pyelftools largely trusts the structures it reads, and anti-analysis authors
exploit exactly that — corrupting metadata to crash or mislead tools. This stage
re-parses the header, program headers, and section headers at the raw byte level
with `struct`, independent of pyelftools, and checks the format's invariants:

- header table offsets/sizes actually fit inside the file; `e_ehsize`/
  `e_phentsize`/`e_shentsize` match the class; `e_shstrndx` in range;
- every segment's `p_offset+p_filesz` is within the file and `p_filesz<=p_memsz`;
- every section's `sh_offset+sh_size` is within the file; sections don't overlap;
- the "hidden section count" trick (`e_shnum==0` with `e_shoff!=0`);
- **cross-view consistency**: the entry point lands in an executable `PT_LOAD`
  segment, and allocated sections map into some loadable segment — i.e. the
  section view and the segment view agree.

It runs by default and stays silent on well-formed binaries, so it won't add
noise to normal files, but lights up on corrupt or deliberately obfuscated ones.

## Disassembly signals (`--disasm`)

Linear-sweep disassembly (Capstone) of the executable sections, used to surface
behavior that imports and strings can't show. It writes a full `disasm.txt` and
flags:

- **direct syscall instructions** (`syscall` / `int 0x80` / `svc`) — code
  talking to the kernel without libc, typical of shellcode and evasion;
- **anti-analysis / VM-detection instructions** (`rdtsc`, `cpuid`, and the
  `sidt`/`sgdt`/`sldt`/`smsw` "red pills", `in`/`out`);
- **get-PC prologues** (`call $+5; pop`) — position-independent shellcode;
- **indirect control-flow density** (register/memory `call`/`jmp`) — obfuscation
  or dynamic dispatch;
- **undecodable-byte ratio** — a code section that won't disassemble cleanly is a
  strong packing/encryption signal;
- **XOR density** — possible in-code decryption stubs.

Linear sweep is used on purpose: it's robust and fast. Its weakness (misreading
data-in-code) is itself reported via the undecodable ratio. x86/x86-64, ARM64,
ARM, and MIPS are supported. Work is capped for very large binaries.

## Network emulation (`--netsim`, executes the sample)

Samples that wait on a C2 often do nothing observable because their connections
fail. `--netsim` runs the target under ptrace, and at each `connect()` it reads
the destination out of the sample's memory, **records where it was trying to
go**, then rewrites the sockaddr in place to point at a local fake service so the
call succeeds:

```
  connect -> 185.220.101.47:8080  [redirected to local fake-tcp]
```

A loopback fake answers: HTTP requests get a canned `200 OK`, other protocols get
a generic banner-then-echo, and a fake DNS server resolves every name to
loopback so libc resolution succeeds and the follow-on connect is caught too. The
report lists the unique outbound destinations (the real intel — C2 IPs, ports,
resolved domains) and the request bytes the sample sent (e.g. the beacon URI and
`Host:` header), all saved to `netsim.log`.

This is **emulation, not containment**: it answers connect()-based flows (the
common case) but does not stop the sample doing other things, and pure
`sendto()`/`sendmsg()` datagram or raw-socket traffic is logged by strace rather
than answered here. Run it in a VM or disposable container.

## What the static analysis covers

| Stage         | What it does                                                        |
|---------------|---------------------------------------------------------------------|
| `fileid`      | `file(1)` identification (magic fallback if absent)                 |
| `hashes`      | MD5 + SHA256 and size                                               |
| `header`      | class/arch/endianness, type, entry, interpreter, PIE/static/stripped |
| `robustness`  | raw-parse integrity + cross-view consistency; flags malformed/obfuscated ELFs (default) |
| `mitigations` | NX, PIE, RELRO, stack canary, FORTIFY, RPATH/RUNPATH (`--mitigations`) |
| `entropy`     | Shannon entropy per section; flags likely packed/encrypted regions  |
| `entropy_map` | `--entropy-check`: Shannon entropy per fixed-size file block, as a visual table over raw offsets; flags sustained high-entropy regions |
| `packing`     | UPX detection (optional `--unpack` to unpack and re-scan)          |
| `strings`     | categorized strings: URLs, IPs, domains, tmp paths, shell, crypto, persistence |
| `imports`     | undefined dynamic symbols bucketed by behavior (network/exec/anti-debug/...) |
| `anomalies`   | entry point outside `.text`, RWX segments, removed section headers, odd names |
| `disasm`      | `--disasm`: Capstone linear sweep; direct syscalls, VM/anti-debug insns, get-PC prologues, indirect-CF and XOR density, undecodable ratio |

### Suspicion score

Every finding carries a severity (`low`/`medium`/`high`) with a weight. The
weights are summed into a score and mapped to a verdict:

```
MINIMAL (0-2)   LOW (3-7)   MEDIUM (8-17)   HIGH (18+)
```

It is a triage aid, not a verdict on maliciousness. A clean statically linked
binary can score a few points; the bands are tuned so ordinary system binaries
land in MINIMAL/LOW and network+exec+RWX+packing stacks land in HIGH.

## Output

Each run writes to a report directory (auto-named `elf-report-<name>-<stamp>/`
unless `--outdir` is given):

- `report.json` — the full structured result (every stage's data + findings)
- `strings.txt` — the complete strings dump
- `strace.log`, `ltrace.log`, `capture.pcap`, `mem_<pid>.bin`, `supervise.log`,
  `gdbinit.local` — whichever dynamic/interactive stages ran

`--json-only` suppresses the terminal summary; `--no-color` disables ANSI color.

## Safety notes

- Static stages never execute the sample. `ldd` is intentionally **not** used
  for dependency resolution (it can run code); imports come from the ELF
  dynamic section instead.
- `--dynamic`, `--supervise`, `--gdb`, `--memdump`, `--tcpdump`, `--netsim`, and
  `--all` execute the binary. They prompt for confirmation unless `-y` is given.
- `--netsim` is network *emulation*, not isolation — it fakes responses but does
  not sandbox the process. Run it somewhere disposable.
- `tcpdump` and `--memdump` generally need root (packet capture / `/proc/<pid>/mem`).
- `--batch` is static-only by design.

## Layout

```
elf-analyzer/
├── install.sh              venv + pip deps
├── start.sh                launcher (activates venv, runs the package)
├── requirements.txt
└── elfanalyzer/
    ├── cli.py              argument parsing + stage orchestration
    ├── tools.py            external tool detection + apt mapping
    ├── static_analysis.py  hashes/header/entropy/strings/imports/anomalies/packing
    ├── robustness.py       raw-parse integrity + cross-view checks
    ├── disasm.py           Capstone disassembly + behavioral signals
    ├── dynamic_analysis.py  strace / ltrace / tcpdump / memdump
    ├── supervisor.py       interactive ptrace syscall gate
    ├── netsim.py           fake network services + connect() redirection
    ├── interactive.py      gdb launcher
    ├── report.py           JSON + scored terminal summary
    └── util.py             findings model, colors, subprocess helper
```
