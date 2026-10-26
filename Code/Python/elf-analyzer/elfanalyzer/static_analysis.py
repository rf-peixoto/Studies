"""Static analysis stages. None of these execute the target binary.

Each public ``analyze_*`` function returns a StageResult. ELF parsing uses
pyelftools; a few stages shell out to binutils where that is simplest, always
in a read-only way (no execution of the sample).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import struct
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .tools import ToolStatus
from .util import Severity, StageResult, run_tool, human_size

try:
    from elftools.elf.elffile import ELFFile
    from elftools.elf.sections import SymbolTableSection
    from elftools.elf.dynamic import DynamicSection
    from elftools.elf.constants import P_FLAGS
    from elftools.common.exceptions import ELFError
    HAVE_PYELFTOOLS = True
except ImportError:  # pragma: no cover - guarded at CLI level
    HAVE_PYELFTOOLS = False


# --------------------------------------------------------------------------- #
# Hashes                                                                       #
# --------------------------------------------------------------------------- #
def analyze_hashes(path: str) -> StageResult:
    res = StageResult("hashes")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            md5.update(chunk)
            sha256.update(chunk)
            size += len(chunk)
    res.data = {
        "size_bytes": size,
        "size_human": human_size(size),
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }
    return res


# --------------------------------------------------------------------------- #
# Header summary                                                               #
# --------------------------------------------------------------------------- #
_ELF_TYPE_NAMES = {
    "ET_NONE": "none", "ET_REL": "relocatable", "ET_EXEC": "executable",
    "ET_DYN": "shared-object/PIE", "ET_CORE": "core",
}


def _elf(path: str) -> "ELFFile":
    return ELFFile(open(path, "rb"))


def analyze_header(path: str) -> StageResult:
    res = StageResult("header")
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            hdr = elf.header
            e_type = hdr["e_type"]
            ident = hdr["e_ident"]

            has_interp = any(seg["p_type"] == "PT_INTERP"
                             for seg in elf.iter_segments())
            interp = None
            if has_interp:
                for seg in elf.iter_segments():
                    if seg["p_type"] == "PT_INTERP":
                        interp = seg.get_interp_name()
                        break

            is_dyn_linked = any(seg["p_type"] == "PT_DYNAMIC"
                                for seg in elf.iter_segments())
            # PIE = ET_DYN *with* an interpreter (an executable), as opposed to
            # a plain shared library (ET_DYN, no interp).
            is_pie = (e_type == "ET_DYN") and has_interp
            stripped = elf.get_section_by_name(".symtab") is None

            data = {
                "class": "ELF64" if elf.elfclass == 64 else "ELF32",
                "endianness": "little" if elf.little_endian else "big",
                "machine": hdr["e_machine"],
                "type": e_type,
                "type_desc": _ELF_TYPE_NAMES.get(e_type, e_type),
                "entry_point": hex(hdr["e_entry"]),
                "os_abi": ident["EI_OSABI"],
                "interpreter": interp,
                "statically_linked": not is_dyn_linked,
                "pie": is_pie,
                "stripped": stripped,
                "num_sections": elf.num_sections(),
                "num_segments": elf.num_segments(),
            }
            res.data = data

            if not is_dyn_linked:
                res.add(Severity.LOW, "header", "Statically linked",
                        "No dynamic linker; harder to resolve behavior via imports.")
            if stripped:
                res.add(Severity.LOW, "header", "Symbol table stripped",
                        "No .symtab; reversing will be harder.")
            if interp and not re.search(r"ld-(linux|musl|uClibc)", interp):
                res.add(Severity.MEDIUM, "header", "Unusual interpreter",
                        f"PT_INTERP = {interp}")
    except (ELFError, OSError) as exc:
        res.error = f"header parse failed: {exc}"
    return res


# --------------------------------------------------------------------------- #
# Security mitigations (checksec-style)                                        #
# --------------------------------------------------------------------------- #
def analyze_mitigations(path: str) -> StageResult:
    res = StageResult("mitigations")
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)

            nx = True  # default assume on; flip off if GNU_STACK is executable
            relro = "none"
            bind_now = False
            for seg in elf.iter_segments():
                t = seg["p_type"]
                if t == "PT_GNU_STACK":
                    nx = not bool(seg["p_flags"] & P_FLAGS.PF_X)
                elif t == "PT_GNU_RELRO":
                    relro = "partial"

            e_type = elf.header["e_type"]
            has_interp = any(s["p_type"] == "PT_INTERP" for s in elf.iter_segments())
            pie = (e_type == "ET_DYN") and has_interp

            # Symbols: canary / FORTIFY are inferred from imported symbol names.
            symbol_names = set()
            for secname in (".dynsym", ".symtab"):
                sec = elf.get_section_by_name(secname)
                if isinstance(sec, SymbolTableSection):
                    for sym in sec.iter_symbols():
                        if sym.name:
                            symbol_names.add(sym.name)

            canary = "__stack_chk_fail" in symbol_names
            fortify = any(n.endswith("_chk") for n in symbol_names)

            rpath, runpath = [], []
            dyn = elf.get_section_by_name(".dynamic")
            if isinstance(dyn, DynamicSection):
                for tag in dyn.iter_tags():
                    if tag.entry.d_tag == "DT_BIND_NOW":
                        bind_now = True
                    elif tag.entry.d_tag == "DT_FLAGS" and (tag.entry.d_val & 0x8):
                        bind_now = True  # DF_BIND_NOW
                    elif tag.entry.d_tag == "DT_FLAGS_1" and (tag.entry.d_val & 0x1):
                        bind_now = True  # DF_1_NOW
                    elif tag.entry.d_tag == "DT_RPATH":
                        rpath.append(getattr(tag, "rpath", "?"))
                    elif tag.entry.d_tag == "DT_RUNPATH":
                        runpath.append(getattr(tag, "runpath", "?"))

            if relro == "partial" and bind_now:
                relro = "full"

            res.data = {
                "nx": nx,
                "pie": pie,
                "relro": relro,
                "stack_canary": canary,
                "fortify_source": fortify,
                "rpath": rpath,
                "runpath": runpath,
            }

            # Findings: these matter for the "audit your own build" use case.
            if not nx:
                res.add(Severity.MEDIUM, "mitigation", "NX disabled",
                        "Stack/heap is executable (RWX GNU_STACK).")
            if not pie and e_type == "ET_EXEC":
                res.add(Severity.LOW, "mitigation", "No PIE",
                        "Fixed load address; weaker ASLR.")
            if relro == "none":
                res.add(Severity.LOW, "mitigation", "No RELRO",
                        "GOT is writable throughout execution.")
            if not canary:
                res.add(Severity.LOW, "mitigation", "No stack canary",
                        "No __stack_chk_fail detected.")
            if rpath:
                res.add(Severity.MEDIUM, "mitigation", "RPATH set",
                        f"Hard-coded library search path: {rpath}")
    except (ELFError, OSError) as exc:
        res.error = f"mitigations parse failed: {exc}"
    return res


# --------------------------------------------------------------------------- #
# Per-section entropy                                                          #
# --------------------------------------------------------------------------- #
def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    ent = -sum((c / length) * math.log2(c / length) for c in counts.values())
    return abs(ent)  # normalize -0.0 -> 0.0 (entropy is always >= 0)


# --------------------------------------------------------------------------- #
# Block entropy map (--entropy-check)                                          #
# --------------------------------------------------------------------------- #
# Classify a Shannon entropy value (bits/byte, range 0..8) into a label. These
# bands are the conventional interpretation used by entropy-mapping tools:
#   ~0        : runs of a single byte (null padding, filler)
#   up to ~5  : structured data (code, tables, ASCII)
#   ~5-6.5    : mixed / lightly compressed
#   ~6.5-7.2  : high (compressed or dense)
#   >=7.2     : very high -> compressed / encrypted / packed payload
ENTROPY_BANDS = [
    (0.50, "null/padding"),
    (5.00, "low (structured)"),
    (6.50, "medium"),
    (7.20, "high"),
    (8.01, "very high (packed/encrypted)"),
]

VERY_HIGH_ENTROPY = 7.2  # threshold for "likely packed/encrypted" blocks


def classify_entropy(value: float) -> str:
    for ceiling, label in ENTROPY_BANDS:
        if value < ceiling:
            return label
    return ENTROPY_BANDS[-1][1]


def _pick_block_size(filesize: int, requested: Optional[int],
                     target_rows: int) -> int:
    """Choose a block size.

    If the caller requested one, honor it. Otherwise auto-scale so the map has
    roughly ``target_rows`` rows (minimum 256 bytes/block), which keeps the
    printed table readable for files of any size.
    """
    if requested and requested > 0:
        return requested
    if filesize <= 0:
        return 256
    size = max(256, math.ceil(filesize / max(1, target_rows)))
    # Round up to a tidy power-of-two-ish boundary for nicer offsets.
    tidy = 256
    while tidy < size:
        tidy *= 2
    return tidy


def analyze_block_entropy(path: str, block_size: Optional[int] = None,
                          target_rows: int = 96) -> StageResult:
    """Compute Shannon entropy over fixed-size file blocks ("sectors").

    Produces a per-block entropy series plus findings for sustained high-entropy
    regions, which is how packed/encrypted payloads and appended data reveal
    themselves at the raw byte-offset level (independent of ELF sections).
    """
    res = StageResult("entropy_map")
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        res.error = f"entropy map read failed: {exc}"
        return res

    filesize = len(blob)
    if filesize == 0:
        res.error = "empty file"
        return res

    bs = _pick_block_size(filesize, block_size, target_rows)

    blocks = []
    values = []
    for off in range(0, filesize, bs):
        chunk = blob[off:off + bs]
        ent = shannon_entropy(chunk)
        values.append(ent)
        blocks.append({
            "offset": off,
            "size": len(chunk),
            "entropy": round(ent, 4),
            "label": classify_entropy(ent),
        })

    mean = sum(values) / len(values)
    res.data = {
        "block_size": bs,
        "num_blocks": len(blocks),
        "file_size": filesize,
        "min_entropy": round(min(values), 4),
        "max_entropy": round(max(values), 4),
        "mean_entropy": round(mean, 4),
        "blocks": blocks,
    }

    # --- findings: contiguous runs of very-high entropy --------------------- #
    runs = []  # (start_offset, end_offset, nblocks)
    run_start = None
    for i, ent in enumerate(values):
        if ent >= VERY_HIGH_ENTROPY:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                runs.append((run_start, i - 1))
                run_start = None
    if run_start is not None:
        runs.append((run_start, len(values) - 1))

    high_bytes = 0
    for start_i, end_i in runs:
        start_off = blocks[start_i]["offset"]
        end_off = blocks[end_i]["offset"] + blocks[end_i]["size"]
        span = end_off - start_off
        high_bytes += span
        # A single high block can be a coincidence; a sustained run is not.
        if (end_i - start_i + 1) >= 2 or span >= 2048:
            frac = span / filesize
            sev = Severity.HIGH if frac >= 0.40 else Severity.MEDIUM
            res.add(sev, "entropy",
                    f"High-entropy region {start_off:#x}-{end_off:#x}",
                    f"{span} bytes (~{frac*100:.0f}% of file) at/above "
                    f"{VERY_HIGH_ENTROPY} bits/byte — likely "
                    "compressed/encrypted/packed.")

    if filesize and (high_bytes / filesize) >= 0.85:
        res.add(Severity.HIGH, "entropy",
                "Almost the whole file is high-entropy",
                "Consistent with a packed or encrypted binary.")

    return res


# Section names expected in ordinary toolchain output. Anything else is "odd".
_KNOWN_SECTIONS = {
    "", ".interp", ".note.ABI-tag", ".note.gnu.build-id", ".note.gnu.property",
    ".gnu.hash", ".hash", ".dynsym", ".dynstr", ".gnu.version", ".gnu.version_r",
    ".gnu.version_d", ".rela.dyn", ".rela.plt", ".rel.dyn", ".rel.plt", ".init",
    ".plt", ".plt.got", ".plt.sec", ".text", ".fini", ".rodata", ".eh_frame_hdr",
    ".eh_frame", ".gcc_except_table", ".init_array", ".fini_array", ".dynamic",
    ".got", ".got.plt", ".data", ".bss", ".comment", ".symtab", ".strtab",
    ".shstrtab", ".tbss", ".tdata", ".data.rel.ro", ".note.stapsdt",
    ".debug_info", ".debug_abbrev", ".debug_line", ".debug_str",
    ".debug_aranges", ".debug_ranges", ".debug_loc", ".annobin",
}

HIGH_ENTROPY = 7.2  # bits/byte; above this a section looks compressed/encrypted


def analyze_entropy(path: str) -> StageResult:
    res = StageResult("entropy")
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            overall = shannon_entropy(open(path, "rb").read())
            sections = []
            for sec in elf.iter_sections():
                if sec["sh_type"] == "SHT_NOBITS" or sec["sh_size"] == 0:
                    continue
                data = sec.data()
                ent = shannon_entropy(data)
                entry = {
                    "name": sec.name,
                    "size": sec["sh_size"],
                    "entropy": round(ent, 3),
                }
                sections.append(entry)
                if ent >= HIGH_ENTROPY and sec["sh_size"] >= 256:
                    sev = Severity.HIGH if ent >= 7.8 else Severity.MEDIUM
                    res.add(sev, "entropy",
                            f"High entropy section {sec.name!r}",
                            f"entropy={ent:.2f} size={sec['sh_size']} "
                            f"(possible packing/encryption)")
            res.data = {
                "overall_entropy": round(overall, 3),
                "sections": sorted(sections, key=lambda s: -s["entropy"]),
            }
    except (ELFError, OSError) as exc:
        res.error = f"entropy failed: {exc}"
    return res


# --------------------------------------------------------------------------- #
# UPX / packer detection                                                       #
# --------------------------------------------------------------------------- #
def analyze_packing(path: str, tools: ToolStatus) -> StageResult:
    res = StageResult("packing")
    packer = None
    section_names = []
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            section_names = [s.name for s in elf.iter_sections()]
    except (ELFError, OSError):
        pass

    if any(n.startswith("UPX") or n in {"UPX0", "UPX1", "UPX2"}
           for n in section_names):
        packer = "UPX"
    else:
        # Fall back to signature in the raw bytes.
        with open(path, "rb") as fh:
            blob = fh.read()
        if b"UPX!" in blob:
            packer = "UPX"

    res.data = {"packer": packer, "packed": packer is not None}
    if packer:
        res.add(Severity.HIGH, "packing", f"{packer}-packed binary",
                "Static analysis sees only the stub; unpack to inspect the "
                "real payload (upx -d).")
    return res


def unpack_upx(path: str, tools: ToolStatus, outdir: str) -> Optional[str]:
    """Attempt ``upx -d`` into outdir. Returns the unpacked path or None."""
    if not tools.has("upx"):
        return None
    dst = os.path.join(outdir, os.path.basename(path) + ".unpacked")
    import shutil as _sh
    _sh.copyfile(path, dst)
    cp = run_tool([tools.path("upx"), "-d", dst], timeout=60)
    return dst if cp.returncode == 0 else None


# --------------------------------------------------------------------------- #
# Interesting strings                                                          #
# --------------------------------------------------------------------------- #
_PATTERNS: Dict[str, re.Pattern] = {
    "url": re.compile(rb"https?://[^\s\"'<>|]{4,}"),
    "ipv4": re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "domain": re.compile(
        rb"\b(?:[a-zA-Z0-9-]{1,63}\.)+(?:com|net|org|ru|cn|io|xyz|top|info|biz|"
        rb"onion|tk|ml|ga|cf|gq|pw|cc|su)\b"),
    "path_tmp": re.compile(rb"/(?:tmp|dev/shm|var/tmp|run)/[^\s\"']{1,64}"),
    "shell": re.compile(rb"(?:/bin/(?:sh|bash|dash)|\bsystem\(|\bpopen\(|"
                        rb"\bexecve\b|/bin/-?[a-z]{0,3}sh\b)"),
    "crypto": re.compile(rb"\b(?:AES|RC4|XOR|base64|RSA|-----BEGIN)\b", re.I),
    "persistence": re.compile(rb"(?:crontab|/etc/rc\.local|\.bashrc|systemd|"
                              rb"LD_PRELOAD|/etc/ld\.so\.preload)"),
}

_MIN_STR = 5


def _extract_strings(path: str, tools: ToolStatus) -> List[Tuple[int, bytes]]:
    """Return (offset, bytes) printable runs. Uses `strings` if present."""
    results: List[Tuple[int, bytes]] = []
    if tools.has("strings"):
        cp = run_tool([tools.path("strings"), "-a", "-t", "d",
                       f"-n{_MIN_STR}", path], timeout=120)
        if cp.returncode == 0:
            for line in cp.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    results.append((int(parts[0]), parts[1].encode("utf-8", "replace")))
            return results
    # Pure-python fallback.
    with open(path, "rb") as fh:
        blob = fh.read()
    cur = bytearray()
    start = 0
    for i, b in enumerate(blob):
        if 32 <= b < 127:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= _MIN_STR:
                results.append((start, bytes(cur)))
            cur = bytearray()
    if len(cur) >= _MIN_STR:
        results.append((start, bytes(cur)))
    return results


def analyze_strings(path: str, tools: ToolStatus, outdir: Optional[str] = None,
                    max_hits: int = 400) -> StageResult:
    res = StageResult("strings")
    all_strings = _extract_strings(path, tools)

    # Persist the full dump; keep only categorized hits in the report.
    if outdir:
        dump = os.path.join(outdir, "strings.txt")
        with open(dump, "w", errors="replace") as fh:
            for off, s in all_strings:
                fh.write(f"{off:#010x}\t{s.decode('utf-8', 'replace')}\n")

    hits: Dict[str, List[dict]] = {k: [] for k in _PATTERNS}
    seen: Dict[str, set] = {k: set() for k in _PATTERNS}
    for off, s in all_strings:
        for name, pat in _PATTERNS.items():
            for m in pat.finditer(s):
                val = m.group(0).decode("utf-8", "replace")
                if val in seen[name]:
                    continue
                seen[name].add(val)
                if len(hits[name]) < max_hits:
                    hits[name].append({"offset": off, "value": val})

    res.data = {
        "total_strings": len(all_strings),
        "categories": {k: v for k, v in hits.items() if v},
        "dump_file": (os.path.join(outdir, "strings.txt") if outdir else None),
    }

    # Findings scaled by category.
    # URLs/domains are common in benign binaries (license text, help URLs), so
    # they are LOW on their own; IPv4 literals and shell/persistence markers are
    # the higher-signal ones.
    sev_map = {
        "url": Severity.LOW, "ipv4": Severity.MEDIUM, "domain": Severity.LOW,
        "path_tmp": Severity.LOW, "shell": Severity.MEDIUM,
        "crypto": Severity.LOW, "persistence": Severity.HIGH,
    }
    for name, items in hits.items():
        if not items:
            continue
        sample = ", ".join(i["value"] for i in items[:5])
        res.add(sev_map[name], "strings",
                f"{len(items)} {name} string(s)", sample)
    return res


# --------------------------------------------------------------------------- #
# Suspicious imports                                                           #
# --------------------------------------------------------------------------- #
# Imported symbol -> behavior bucket. Two match kinds:
#   "exact"  -> the import name must equal one of these (avoids matching
#               bindtextdomain as the network call bind, etc.)
#   "prefix" -> the import name starts with one of these (for C++/OpenSSL-style
#               families like EVP_* where the suffix varies).
# Presence alone is not proof, but the mix is informative for triage.
_IMPORT_BUCKETS: Dict[str, Dict[str, List[str]]] = {
    "network": {"exact": ["socket", "connect", "bind", "listen", "accept",
                          "accept4", "send", "sendto", "sendmsg", "recv",
                          "recvfrom", "recvmsg", "gethostbyname", "getaddrinfo",
                          "inet_addr", "inet_pton", "inet_ntoa", "setsockopt",
                          "getpeername"],
                "prefix": []},
    "exec": {"exact": ["execve", "execv", "execvp", "execvpe", "execl",
                       "execlp", "execle", "system", "popen", "posix_spawn",
                       "posix_spawnp", "fork", "vfork", "clone"],
             "prefix": []},
    "anti_debug": {"exact": ["ptrace", "personality", "prctl"], "prefix": []},
    "filesystem": {"exact": ["unlink", "unlinkat", "remove", "rename",
                             "renameat", "chmod", "fchmod", "chown", "mkdir",
                             "creat", "truncate", "symlink", "link"],
                   "prefix": []},
    "process_inspect": {"exact": ["kill", "setuid", "setgid", "setreuid",
                                  "setresuid", "setsid"], "prefix": []},
    "dyn_loading": {"exact": ["dlopen", "dlsym", "mmap", "mprotect",
                              "memfd_create"], "prefix": []},
    "crypto_api": {"exact": [], "prefix": ["EVP_", "AES_", "RSA_", "CRYPTO_",
                                           "MD5_", "SHA1_", "SHA256_", "RC4"]},
}


def analyze_imports(path: str) -> StageResult:
    res = StageResult("imports")
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            imports: List[str] = []
            dynsym = elf.get_section_by_name(".dynsym")
            if isinstance(dynsym, SymbolTableSection):
                for sym in dynsym.iter_symbols():
                    # Undefined symbols with a name are imports.
                    if sym.name and sym["st_shndx"] == "SHN_UNDEF":
                        imports.append(sym.name)
            imports = sorted(set(imports))

            buckets: Dict[str, List[str]] = {}
            for bucket, needles in _IMPORT_BUCKETS.items():
                exact = set(needles["exact"])
                prefixes = tuple(needles["prefix"])
                matched = [imp for imp in imports
                           if imp in exact
                           or (prefixes and imp.startswith(prefixes))]
                if matched:
                    buckets[bucket] = sorted(set(matched))

            res.data = {
                "total_imports": len(imports),
                "imports": imports,
                "buckets": buckets,
            }

            sev = {
                "network": Severity.MEDIUM, "exec": Severity.MEDIUM,
                "anti_debug": Severity.HIGH, "filesystem": Severity.LOW,
                "process_inspect": Severity.LOW, "dyn_loading": Severity.MEDIUM,
                "crypto_api": Severity.LOW,
            }
            for bucket, matched in buckets.items():
                res.add(sev[bucket], "imports",
                        f"{bucket} imports present",
                        ", ".join(matched[:8]))

            # Classic high-signal combo.
            if "network" in buckets and "exec" in buckets:
                res.add(Severity.HIGH, "imports",
                        "Network + exec capability",
                        "Binary can both talk over the network and spawn "
                        "processes (backdoor-shaped).")
    except (ELFError, OSError) as exc:
        res.error = f"imports failed: {exc}"
    return res


# --------------------------------------------------------------------------- #
# Structural anomalies                                                         #
# --------------------------------------------------------------------------- #
def analyze_anomalies(path: str) -> StageResult:
    res = StageResult("anomalies")
    try:
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            entry = elf.header["e_entry"]

            # 1. Entry point should land in an executable section.
            entry_section = None
            for sec in elf.iter_sections():
                addr = sec["sh_addr"]
                size = sec["sh_size"]
                if addr and addr <= entry < addr + size:
                    entry_section = sec.name
                    break
            if entry_section is None:
                res.add(Severity.MEDIUM, "anomaly",
                        "Entry point not in any section",
                        f"e_entry={entry:#x} maps to no section (packed/"
                        "unusual layout).")
            elif entry_section != ".text":
                res.add(Severity.MEDIUM, "anomaly",
                        "Entry point outside .text",
                        f"e_entry is in {entry_section!r}, not .text.")

            # 2. Writable + executable segments.
            wx = []
            for seg in elf.iter_segments():
                if seg["p_type"] == "PT_LOAD":
                    f = seg["p_flags"]
                    if (f & P_FLAGS.PF_W) and (f & P_FLAGS.PF_X):
                        wx.append(hex(seg["p_vaddr"]))
            if wx:
                res.add(Severity.HIGH, "anomaly",
                        "Writable+executable segment",
                        f"RWX PT_LOAD at {', '.join(wx)} (self-modifying?).")

            # 3. Section header count sanity.
            if elf.num_sections() == 0 and elf.num_segments() > 0:
                res.add(Severity.MEDIUM, "anomaly",
                        "Section headers removed",
                        "Zero sections but loadable segments exist "
                        "(deliberately stripped layout).")

            # 4. Unusual section names.
            odd = [s.name for s in elf.iter_sections()
                   if s.name and s.name not in _KNOWN_SECTIONS
                   and not s.name.startswith(".debug")
                   and not s.name.startswith(".note")]
            if odd:
                res.add(Severity.LOW, "anomaly",
                        "Unusual section names",
                        ", ".join(odd[:10]))

            res.data = {
                "entry_section": entry_section,
                "wx_segments": wx,
                "odd_sections": odd,
            }
    except (ELFError, OSError) as exc:
        res.error = f"anomalies failed: {exc}"
    return res


# --------------------------------------------------------------------------- #
# file(1) identification                                                       #
# --------------------------------------------------------------------------- #
def analyze_fileid(path: str, tools: ToolStatus) -> StageResult:
    res = StageResult("fileid")
    if tools.has("file"):
        cp = run_tool([tools.path("file"), "-b", path], timeout=20)
        res.data = {"description": cp.stdout.strip() if cp.returncode == 0 else None}
    else:
        # Minimal magic check without file(1).
        with open(path, "rb") as fh:
            magic = fh.read(4)
        res.data = {"description": "ELF" if magic == b"\x7fELF" else "unknown",
                    "note": "file(1) not installed; magic-only identification"}
    return res


def is_elf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False
