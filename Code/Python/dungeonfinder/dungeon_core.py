#!/usr/bin/env python3
"""
DungeonFinder - core analysis engine.

Detects and identifies "code caves" (contiguous runs of padding bytes) in
executable files, and reports the surrounding structure: format, architecture,
entry point, section table, per-section entropy, cryptographic hashes, cave
statistics and a size distribution.

This module performs READ-ONLY analysis. It never modifies, patches or injects
into any binary. It is intended for reverse-engineering, malware-analysis
training and binary forensics.

(Derived from the detection half of the "escavator" CLI; the shellcode
injection, entry-point redirection, certificate stripping and checksum-patching
features were intentionally left out.)
"""
from __future__ import annotations

import hashlib
import io
import mmap
import os
import statistics
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import lief
except ImportError:  # pragma: no cover
    lief = None

try:
    from capstone import (
        Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64,
        CS_ARCH_ARM, CS_MODE_ARM, CS_ARCH_ARM64,
    )
    CAPSTONE_AVAILABLE = True
except ImportError:  # pragma: no cover
    CAPSTONE_AVAILABLE = False


# --------------------------------------------------------------------------- #
#  Format detection / validation
# --------------------------------------------------------------------------- #

# Magic signatures used for a cheap first-pass validation independent of LIEF.
_MAGIC = {
    b"MZ": "PE",            # DOS/PE stub
    b"\x7fELF": "ELF",
    b"\xfe\xed\xfa\xce": "MACHO",   # Mach-O 32 BE
    b"\xfe\xed\xfa\xcf": "MACHO",   # Mach-O 64 BE
    b"\xce\xfa\xed\xfe": "MACHO",   # Mach-O 32 LE
    b"\xcf\xfa\xed\xfe": "MACHO",   # Mach-O 64 LE
    b"\xca\xfe\xba\xbe": "MACHO",   # Fat/Universal
}

# Extension -> set of acceptable detected formats. Used by the web layer to
# force extension matching ("the bytes must agree with the name").
EXT_FORMAT = {
    ".exe": {"PE"}, ".dll": {"PE"}, ".sys": {"PE"}, ".scr": {"PE"},
    ".ocx": {"PE"}, ".cpl": {"PE"}, ".efi": {"PE"},
    ".elf": {"ELF"}, ".so": {"ELF"}, ".o": {"ELF", "MACHO"}, ".ko": {"ELF"},
    ".axf": {"ELF"}, ".bin": {"PE", "ELF", "MACHO"},
    ".dylib": {"MACHO"}, ".macho": {"MACHO"},
}

ALLOWED_EXTENSIONS = sorted(EXT_FORMAT.keys())


def sniff_magic(head: bytes) -> Optional[str]:
    """Return 'PE'/'ELF'/'MACHO' from the leading bytes, or None."""
    for sig, fmt in _MAGIC.items():
        if head.startswith(sig):
            return fmt
    return None


class ValidationError(Exception):
    """Raised when an uploaded file fails extension/magic validation."""


def human_size(n: int) -> str:
    """Human-readable byte count, e.g. 36072 -> '35.2 KB'."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def validate_upload(filename: str, head: bytes, *, force_ext: bool = True) -> str:
    """
    Validate an upload by its magic bytes, and (when force_ext is on) reject a
    file whose *recognized* extension names a different format than its bytes.

    The file's real format is always decided by the leading bytes, so:
      * no extension        -> accepted if the bytes are a valid executable
                               (the common case for Linux ELF binaries),
      * unknown extension   -> accepted on magic bytes alone,
      * recognized extension-> must agree with the detected format.

    Returns the detected format string. Raises ValidationError otherwise.
    """
    fmt = sniff_magic(head)
    if fmt is None:
        raise ValidationError(
            "File does not begin with a recognized executable signature "
            "(PE 'MZ', ELF, or Mach-O)."
        )
    ext = os.path.splitext(filename)[1].lower()
    if force_ext and ext in EXT_FORMAT and fmt not in EXT_FORMAT[ext]:
        raise ValidationError(
            f"Extension '{ext}' claims a different format than the file's "
            f"actual bytes ({fmt}). Rename it or upload the correct file."
        )
    return fmt


# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #

@dataclass
class Cave:
    pattern: str
    offset: int
    size: int
    section: str = "<unknown>"
    is_code: Optional[bool] = None   # set when disasm filter runs

    def to_dict(self):
        d = asdict(self)
        d["offset_hex"] = hex(self.offset)
        d["end"] = self.offset + self.size
        d["end_hex"] = hex(self.offset + self.size)
        return d


@dataclass
class SectionInfo:
    name: str
    offset: int
    size: int
    virtual_address: int
    entropy: float
    flags: str = ""

    def to_dict(self):
        d = asdict(self)
        d["offset_hex"] = hex(self.offset)
        d["virtual_address_hex"] = hex(self.virtual_address)
        return d


@dataclass
class AnalysisResult:
    filename: str
    size: int
    fmt: str
    architecture: str
    bits: int
    entrypoint: int
    section_alignment: int
    sections: list = field(default_factory=list)
    caves: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "filename": self.filename,
            "size": self.size,
            "size_hex": hex(self.size),
            "size_human": human_size(self.size),
            "format": self.fmt,
            "architecture": self.architecture,
            "bits": self.bits,
            "entrypoint": hex(self.entrypoint),
            "section_alignment": self.section_alignment,
            "sections": [s.to_dict() for s in self.sections],
            "caves": [c.to_dict() for c in self.caves],
            "stats": self.stats,
            "hashes": self.hashes,
            "patterns": self.patterns,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
#  Hashing
# --------------------------------------------------------------------------- #

def compute_hashes(path: str) -> dict:
    algos = {
        "md5": hashlib.md5(),
        "sha256": hashlib.sha256(),
        "sha512": hashlib.sha512(),
        "blake2b": hashlib.blake2b(),
    }
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            for h in algos.values():
                h.update(chunk)
    return {k: v.hexdigest() for k, v in algos.items()}


# --------------------------------------------------------------------------- #
#  Metadata extraction (LIEF 1.x)
# --------------------------------------------------------------------------- #

def _arch_name(binary, fmt: str) -> tuple[str, int]:
    """Return (arch_name, bits)."""
    try:
        if fmt == "PE":
            name = binary.header.machine.name
        else:
            name = binary.header.machine_type.name
    except Exception:
        name = "UNKNOWN"
    name = name.upper()
    bits = 32
    if any(t in name for t in ("X86_64", "AMD64", "ARM64", "AARCH64", "PPC64", "RISCV64", "IA64")):
        bits = 64
    elif fmt == "PE":
        try:
            bits = 64 if binary.optional_header.magic == lief.PE.PE_TYPE.PE32_PLUS else 32
        except Exception:
            pass
    return name, bits


def extract_metadata(path: str):
    if lief is None:
        raise RuntimeError("LIEF is not installed.")
    binary = lief.parse(path)
    if binary is None:
        raise ValidationError("LIEF could not parse this file as an executable.")

    raw_fmt = binary.format.name.upper()
    if raw_fmt.startswith("PE"):
        fmt = "PE"
    elif raw_fmt.startswith("ELF"):
        fmt = "ELF"
    elif raw_fmt.startswith("MACHO"):
        fmt = "MACHO"
    else:
        fmt = raw_fmt

    arch, bits = _arch_name(binary, fmt)

    section_alignment = 1
    try:
        if fmt == "PE":
            section_alignment = binary.optional_header.section_alignment
        elif fmt == "ELF":
            # ELF has no single "section alignment"; use max section alignment.
            section_alignment = max((s.alignment or 1) for s in binary.sections) if list(binary.sections) else 1
    except Exception:
        pass

    sections = []
    for sec in binary.sections:
        if fmt == "PE":
            offset = sec.pointerto_raw_data
            size = sec.sizeof_raw_data
        else:
            offset = sec.offset
            size = sec.size
        try:
            entropy = round(float(sec.entropy), 4)
        except Exception:
            entropy = 0.0
        flags = ""
        try:
            if fmt == "PE":
                flags = ",".join(str(c).split(".")[-1] for c in sec.characteristics_lists)
            else:
                flags = ",".join(str(c).split(".")[-1] for c in sec.flags_list)
        except Exception:
            pass
        sections.append(SectionInfo(
            name=sec.name or "<noname>",
            offset=int(offset),
            size=int(size),
            virtual_address=int(getattr(sec, "virtual_address", 0)),
            entropy=entropy,
            flags=flags,
        ))

    meta = AnalysisResult(
        filename=os.path.basename(path),
        size=os.path.getsize(path),
        fmt=fmt,
        architecture=arch,
        bits=bits,
        entrypoint=int(binary.entrypoint),
        section_alignment=int(section_alignment or 1),
        sections=sections,
    )
    return binary, meta


# --------------------------------------------------------------------------- #
#  Cave scanning
# --------------------------------------------------------------------------- #

def _section_for_offset(sections: list, offset: int) -> str:
    for s in sections:
        if s.offset <= offset < s.offset + s.size:
            return s.name
    return "<outside>"


def find_caves_in_region(mm, pattern: bytes, min_size: int,
                         region_start: int, region_end: int):
    """
    Find maximal runs of *pattern* repeated end-to-end, at least *min_size*
    bytes long, within [region_start, region_end).
    """
    runs = []
    if region_end <= region_start or not pattern:
        return runs
    plen = len(pattern)
    # Number of whole repetitions needed to reach min_size.
    reps = max(1, -(-min_size // plen))  # ceil division
    seq = pattern * reps
    seqlen = len(seq)
    pos = region_start
    while pos < region_end:
        idx = mm.find(seq, pos, region_end)
        if idx == -1:
            break
        start = idx
        end = idx + seqlen
        # Extend the run one pattern-width at a time.
        while end + plen <= region_end and mm[end:end + plen] == pattern:
            end += plen
        runs.append((start, end - start))
        pos = end
    return runs


def _capstone_engine(arch_name: str, bits: int, fmt: str):
    if not CAPSTONE_AVAILABLE:
        return None
    n = arch_name.upper()
    if "X86_64" in n or "AMD64" in n:
        return Cs(CS_ARCH_X86, CS_MODE_64)
    if "I386" in n or "I686" in n or ("X86" in n and bits == 32):
        return Cs(CS_ARCH_X86, CS_MODE_32)
    if "ARM64" in n or "AARCH64" in n:
        return Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    if "ARM" in n:
        return Cs(CS_ARCH_ARM, CS_MODE_ARM)
    # Fallback by bit-width (best effort).
    return Cs(CS_ARCH_X86, CS_MODE_64 if bits == 64 else CS_MODE_32)


def classify_runs(runs: list, mm, arch_name: str, bits: int, fmt: str,
                  sample_cap: int = 4096):
    """
    Mark each run as code/non-code by attempting disassembly across the whole
    run (capped at *sample_cap* bytes). A run is 'code' if a meaningful fraction
    disassembles into valid instructions. Returns runs with .is_code set.
    """
    cs = _capstone_engine(arch_name, bits, fmt)
    if cs is None:
        return runs
    cs.skipdata = False
    for r in runs:
        sample_len = min(r.size, sample_cap)
        data = bytes(mm[r.offset:r.offset + sample_len])
        # A run of a single repeated byte is padding by definition, even though
        # some such bytes (e.g. 0x00 on x86 -> "add [rax],al") disassemble into
        # nominally valid instructions. Don't call that code.
        if len(set(data)) <= 1:
            r.is_code = False
            continue
        decoded = 0
        for _ in cs.disasm(data, r.offset):
            decoded += 1
            if decoded >= 8:   # enough valid instructions to call it code
                break
        r.is_code = decoded >= 8
    return runs


# --------------------------------------------------------------------------- #
#  Statistics
# --------------------------------------------------------------------------- #

def _safe_quantile(sizes_sorted, q):
    """Percentile q in [0,1] with safe handling of tiny lists."""
    n = len(sizes_sorted)
    if n == 0:
        return 0
    if n == 1:
        return sizes_sorted[0]
    idx = min(int(round(q * (n - 1))), n - 1)
    return sizes_sorted[idx]


def compute_stats(caves: list) -> dict:
    sizes = sorted(c.size for c in caves)
    if not sizes:
        return {}
    stats = {
        "count": len(sizes),
        "total_bytes": sum(sizes),
        "min": sizes[0],
        "max": sizes[-1],
        "mean": round(statistics.mean(sizes), 2),
        "median": int(statistics.median(sizes)),
        "percentiles": {
            "25": int(_safe_quantile(sizes, 0.25)),
            "50": int(_safe_quantile(sizes, 0.50)),
            "75": int(_safe_quantile(sizes, 0.75)),
            "90": int(_safe_quantile(sizes, 0.90)),
        },
        "histogram": [],
    }
    bins = 10
    bin_counts = [0] * bins
    rmin, rmax = stats["min"], stats["max"]
    span = (rmax - rmin) or 1
    for s in sizes:
        idx = min((s - rmin) * bins // span, bins - 1)
        bin_counts[idx] += 1
    for i, count in enumerate(bin_counts):
        bmin = rmin + i * span // bins
        bmax = rmin + ((i + 1) * span // bins)
        stats["histogram"].append({"range": [bmin, bmax], "count": count})
    return stats


# --------------------------------------------------------------------------- #
#  Pattern parsing
# --------------------------------------------------------------------------- #

def parse_pattern(text: str) -> bytes:
    """
    Turn a user pattern into bytes. Accepts:
      - escape form:  \\x00 , \\xcc\\x90
      - hex form:     00 , cc90 , 0xCC
    """
    t = text.strip()
    if not t:
        raise ValueError("Empty pattern")
    if "\\x" in t:
        return bytes(t, "utf-8").decode("unicode_escape").encode("latin-1")
    cleaned = t.lower().replace("0x", "").replace(" ", "").replace(",", "")
    if all(ch in "0123456789abcdef" for ch in cleaned) and len(cleaned) % 2 == 0:
        return bytes.fromhex(cleaned)
    # Treat as literal latin-1 bytes.
    return t.encode("latin-1", "ignore")


# --------------------------------------------------------------------------- #
#  Top-level analysis
# --------------------------------------------------------------------------- #

@dataclass
class ScanOptions:
    patterns: list = field(default_factory=lambda: ["\\x00"])
    min_size: int = 32
    scan_sections: Optional[list] = None
    skip_sections: Optional[list] = None
    min_offset: Optional[int] = None
    max_offset: Optional[int] = None
    align: Optional[int] = None
    disasm_filter: bool = False
    exclude_code: bool = False     # when disasm_filter: drop runs that look like code
    top: Optional[int] = None


def analyze(path: str, opts: ScanOptions) -> AnalysisResult:
    binary, meta = extract_metadata(path)
    meta.hashes = compute_hashes(path)

    pattern_bytes = []
    for p in opts.patterns or ["\\x00"]:
        try:
            raw = parse_pattern(p)
            if raw:
                pattern_bytes.append({"text": p, "bytes": raw})
        except Exception:
            meta.warnings.append(f"Ignored invalid pattern: {p!r}")
    if not pattern_bytes:
        pattern_bytes = [{"text": "\\x00", "bytes": b"\x00"}]
    meta.patterns = [pb["text"] for pb in pattern_bytes]

    longest = max(len(pb["bytes"]) for pb in pattern_bytes)
    if opts.min_size < longest:
        opts.min_size = longest
        meta.warnings.append(f"min_size raised to {longest} (longest pattern length)")

    # Build scan regions.
    sections = meta.sections
    if opts.scan_sections:
        regions = [s for s in sections if s.name in opts.scan_sections]
    elif opts.skip_sections:
        regions = [s for s in sections if s.name not in opts.skip_sections]
    else:
        regions = None  # whole file

    caves: list[Cave] = []
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            scan_targets = (
                [(s.name, s.offset, s.offset + s.size) for s in regions]
                if regions is not None
                else [("<entire>", 0, meta.size)]
            )
            for pb in pattern_bytes:
                for name, start_off, end_off in scan_targets:
                    start_off = max(0, start_off)
                    end_off = min(meta.size, end_off)
                    found = find_caves_in_region(mm, pb["bytes"], opts.min_size,
                                                 start_off, end_off)
                    for off, sz in found:
                        sec = name if name != "<entire>" else _section_for_offset(sections, off)
                        caves.append(Cave(pattern=pb["text"], offset=off, size=sz, section=sec))

            caves.sort(key=lambda c: c.offset)

            # Offset / alignment filters.
            if opts.min_offset is not None:
                caves = [c for c in caves if c.offset >= opts.min_offset]
            if opts.max_offset is not None:
                caves = [c for c in caves if c.offset <= opts.max_offset]
            if opts.align:
                caves = [c for c in caves if c.offset % opts.align == 0]

            # Disassembly classification.
            if opts.disasm_filter:
                if not CAPSTONE_AVAILABLE:
                    meta.warnings.append("Capstone unavailable: disasm filter skipped.")
                else:
                    classify_runs(caves, mm, meta.architecture, meta.bits, meta.fmt)
                    if opts.exclude_code:
                        caves = [c for c in caves if not c.is_code]
        finally:
            mm.close()

    meta.stats = compute_stats(caves)
    if opts.top:
        caves = sorted(caves, key=lambda c: c.size, reverse=True)[:opts.top]
        caves.sort(key=lambda c: c.offset)
    meta.caves = caves
    return meta
