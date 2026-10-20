# envcheck

A small, inspect-only C library that reports whether your compiled program is
running inside a VM, sandbox, debugger, or on a dedicated reverse-engineering
machine. It **only reports** — it never kills the process, changes your logic,
hides itself, or phones home. You read the result struct (or its JSON) and
decide what to do.

> **It's a speed bump, not a wall.** It raises the cost of casual analysis and
> defeats many automated sandboxes. A skilled analyst on bare metal, or one who
> patches the checks out, will get through. Several signals also fire on
> legitimate hosts (cloud dev boxes, WSL, containers, CI runners, low-spec
> laptops), so weigh the **aggregate scores** — never act on a single flag.

## Files

| File | Purpose |
|------|---------|
| `envcheck.h` | Public API and the `env_report_t` struct. |
| `envcheck.c` | Implementation (no `main`; drop into your project). |
| `example.c`  | Minimal driver that prints the report as JSON. |
| `report.c`   | Test harness: per-signal breakdown, scores, and a VM/controlled-env percentage. |
| `build.sh`   | One-command Linux build of the `report` harness. |

## Build

```sh
# Library only, into your project:
cc -O2 -c envcheck.c                 # Linux
cl /O2 /c envcheck.c                 # Windows (MSVC recommended)

# With the example driver:
cc -O2 example.c envcheck.c -o envcheck      # Linux
cl /O2 example.c envcheck.c                  # Windows
```

Supported: Linux and Windows on x86/x86-64. MSVC is recommended on Windows — the
SEH debugger traps compile only under MSVC, and the VMware backdoor probe needs
MSVC x86 (see caveats).

## Usage

```c
#include "envcheck.h"

env_report_t r = env_inspect(NULL);          /* NULL => default options */
env_layout_matches(&r, "pt", 0x0416);        /* optional market check (pt / pt-BR) */

if (r.analysis_score >= 6 || r.vm_score >= 8) {
    /* your policy — refuse to run, reduce functionality, log, phone a license
       server, whatever. The library does none of this for you, by design. */
}
```

Options (pass an `env_options_t*` instead of `NULL` to change them):

| Option | Default | Notes |
|--------|---------|-------|
| `run_ptrace_self` | 1 | Linux `PTRACE_TRACEME` probe. Changes process state (see caveats). |
| `run_io_backdoor` | 1 | VMware backdoor port probe. Raises+catches a CPU fault. |
| `run_sleep_skew`  | 0 | Sleeps ~200 ms and measures; adds latency, so off by default. |

## Important caveats (read these)

1. **`run_ptrace_self` and `run_io_backdoor` are mutually exclusive per process.**
   `PTRACE_TRACEME` has persistent, process-wide side effects: once it has run
   (even with a matching `PTRACE_DETACH`), the next synchronous `SIGSEGV`/`SIGILL`
   is delivered as a trace-stop, which would make the fault-based backdoor probe
   self-stop the process. `env_inspect()` enforces this automatically — it runs
   the backdoor only while ptrace-self has never run, and never after — so you
   don't have to. But know that on Linux, with both enabled (the default), the
   backdoor runs on the **first** `env_inspect()` call and is then disabled for
   the life of the process.

2. **The backdoor probe makes an *interactive* debugger break on SIGSEGV.**
   The probe deliberately faults, and tools like gdb stop on the first-chance
   SIGSEGV. That's harmless (and arguably useful friction), but if you ever
   debug your own release build, set `run_io_backdoor = 0` first — or in gdb:
   `handle SIGSEGV nostop pass`.

3. **SEH traps are MSVC-only.** `seh_int3` and `closehandle` compile to no-ops
   under MinGW/Clang on Windows, so their `false` there means "not tested", not
   "no debugger".

4. **The VMware backdoor needs inline asm.** It runs on Linux (GCC/Clang x86/x64)
   and Windows MSVC **x86**. On MSVC x64 it is a no-op (`vmware_backdoor` stays
   `false`), because MSVC x64 has no inline assembler.

5. **Keyboard layout on Linux is a locale approximation** (`LANG`/`LC_*`). For
   the real active X11/Wayland layout you'd add `libxkbcommon`.

## JSON fields and scoring weights

`env_report_to_json()` emits the object below. Each flag that feeds a score is
shown with the points it contributes. `vm_score` and `analysis_score` are simple
weighted sums; pick your own thresholds.

### `vm` — virtualization / controlled host

| Field | Weight | Meaning |
|-------|:------:|---------|
| `hypervisor_bit` | 1 | CPUID.1 ECX[31] set. True on most cloud/dev hosts too. |
| `hypervisor_vendor` | 2 | CPUID 0x40000000 vendor (`KVMKVMKVM`, `VMwareVMware`, …). |
| `cpu_brand_virtual` | 2 | CPU brand string contains QEMU/Virtual/KVM. |
| `mac_prefix` | 2 | NIC MAC OUI belongs to a VM vendor. |
| `dmi_string` | 3 | DMI/registry manufacturer/product looks virtual. |
| `artifact_present` | 3 | Guest-tool device/driver/module/service present. |
| `vmware_backdoor` | 3 | VMware I/O port `0x5658` responded with its magic. |
| `cpuinfo_hypervisor` | 1 | Linux `/proc/cpuinfo` hypervisor flag. |
| `wine` | 2 | Running under Wine. |
| `wsl` | 1 | Running under WSL. |
| `container` / `container_type` | 2 | docker / lxc / k8s. |
| `firmware_table` / `firmware_hit` | 3 | ACPI/SMBIOS firmware tables name a VM (`VBOX`, `QEMU`, `BXPC`…). Hard to scrub. |
| `pci_device` / `pci_id` | 3 | PCI vendor ID is a VM vendor (VMware 15ad, VBox 80ee, virtio 1af4, QEMU 1234, Xen 5853, Parallels 1ab8). |
| `disk_model` | 2 | Disk model string / virtio `vd*` device looks virtual. |
| `gpu_model` / `gpu_name` | 2 | Display adapter / DRM driver is virtual (vmwgfx, virtio, vboxvideo, qxl, "Microsoft Basic Render"). |
| `no_thermal_sensor` | 1 | No thermal sensors (Linux). Weak — servers lack them too. |
| `named_pipe` | 2 | Windows VM/sandbox named pipe present (`\\.\VBoxMiniRdrDN`, `\\.\pipe\cuckoo`…). |
| `no_battery` | **0** | Reported but **not scored** — fires on ordinary desktops/servers, too noisy to weight. |

### `sandbox_env` — Linux controlled-environment tells

| Field | Weight | Meaning |
|-------|:------:|---------|
| `seccomp_active` | 2 | A seccomp filter is installed (common in sandboxes). |
| `unusual_namespace` | 1 | Process is in a non-init PID namespace (containerized). |
| `yama_ptrace_scope` | — | Yama ptrace-scope value (0–3). Reported, not scored. |

### `debugger` — active analysis

| Field | Weight | Meaning |
|-------|:------:|---------|
| `present` | 3 | Any debugger/tracer signal below rolled up. |
| `kernel_debugger` | 3 | Windows kernel debugger enabled (bare-metal KD/WinDbg). |
| `hw_breakpoints` | 2 | Debug registers Dr0–Dr3/Dr7 set. |
| `peb_ntglobalflag` | 1 | PEB NtGlobalFlag heap-debug bits. |
| `ld_preload_set` | 1 | `LD_PRELOAD` present (hooking vector). |
| `ld_audit_set` | 1 | `LD_AUDIT` present (hooking vector). |
| `ptrace_self_blocked` | 2 | `PTRACE_TRACEME` failed → already traced. |
| `seh_int3` | 3 | SEH `int 3` swallowed by a debugger (MSVC). |
| `closehandle` | 3 | Invalid-handle exception (MSVC). |
| `tracer_pid`, `peb_being_debugged`, `debug_port_set` | — | Reported; folded into `present`. |

### `analysis` — tooling, hooks, instrumentation, launcher

| Field | Weight | Meaning |
|-------|:------:|---------|
| `tool_running` / `tool_running_name` | 3 | IDA, Ghidra, x64dbg, radare2, gdb, Wireshark… running. |
| `tool_installed` / `tool_installed_name` | 2 | RE tool on disk / in PATH — dedicated RE box. |
| `hook_dll_loaded` / `hook_dll_name` | 3 | Sandbox/monitor DLL in-process (Sandboxie, Cuckoo…). |
| `instrumentation` / `instrumentation_name` | 3 | Frida / Pin / DynamoRIO / Qiling — by process, injected lib in `maps`, Frida thread names (`gum-js-loop`, `gmain`) or default port 27042. |
| `parent_suspicious` / `parent_name` | 3 | Launched by a debugger/analysis tool. |

### `resources` — sandbox / unattended heuristics

| Field | Weight | Meaning |
|-------|:------:|---------|
| `low_cpu` | 1 | < 2 cores. |
| `low_ram` | 1 | < 2 GB. |
| `small_disk` | 1 | < 60 GB. |
| `short_uptime` | 1 | < 5 min (freshly booted sandbox). |
| `suspicious_identity` | 2 | Host/user name like `sandbox`, `cuckoo`, `malware`… |
| `small_screen` | 1 | ≤ 1024×768 (default sandbox resolution; Windows). |
| `no_user_input` | 1 | > 10 min input idle (Windows). |
| `sleep_skew_suspicious` | 2 | Sleep was fast-forwarded (time-acceleration sandbox). |

### `timing`, `keyboard`, `scores`

- `timing.cpuid_cycles` / `suspicious` (weight 1): serialising CPUID far slower
  than bare metal → VM-exit overhead.
- `keyboard.primary_langid` / `layout_name` / `matches_target`: coarse market
  signal from `env_layout_matches()`. Not scored.
- `scores.vm_score`, `scores.analysis_score`: the two weighted sums. Current
  maxima are **49** (VM) and **33** (analysis), **82** combined — but several
  signals are platform-specific or mutually exclusive, so no single run reaches
  the max. The `report` harness prints the live maxima and the percentage.

## License / intent

This is defensive software-protection code for guarding *your own* binaries.
It is written to be auditable: nothing is obfuscated, and every probe is named
and commented.
