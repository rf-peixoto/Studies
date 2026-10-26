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
./start.sh <elf> --only strings,imports     # run a subset of static stages
./start.sh <elf> --dynamic -y       # strace + ltrace (executes the sample)
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

## What the static analysis covers

| Stage         | What it does                                                        |
|---------------|---------------------------------------------------------------------|
| `fileid`      | `file(1)` identification (magic fallback if absent)                 |
| `hashes`      | MD5 + SHA256 and size                                               |
| `header`      | class/arch/endianness, type, entry, interpreter, PIE/static/stripped |
| `mitigations` | NX, PIE, RELRO, stack canary, FORTIFY, RPATH/RUNPATH (`--mitigations`) |
| `entropy`     | Shannon entropy per section; flags likely packed/encrypted regions  |
| `packing`     | UPX detection (optional `--unpack` to unpack and re-scan)          |
| `strings`     | categorized strings: URLs, IPs, domains, tmp paths, shell, crypto, persistence |
| `imports`     | undefined dynamic symbols bucketed by behavior (network/exec/anti-debug/...) |
| `anomalies`   | entry point outside `.text`, RWX segments, removed section headers, odd names |

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
- `--dynamic`, `--supervise`, `--gdb`, `--memdump`, `--tcpdump`, and `--all`
  execute the binary. They prompt for confirmation unless `-y` is given.
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
    ├── static_analysis.py  all static stages (no execution)
    ├── dynamic_analysis.py  strace / ltrace / tcpdump / memdump
    ├── supervisor.py       interactive ptrace syscall gate
    ├── interactive.py      gdb launcher
    ├── report.py           JSON + scored terminal summary
    └── util.py             findings model, colors, subprocess helper
```
