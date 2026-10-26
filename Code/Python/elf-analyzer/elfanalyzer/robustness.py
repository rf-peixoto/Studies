"""Malformed-ELF hardening: raw integrity and cross-view consistency checks.

Anti-analysis authors deliberately corrupt ELF metadata to crash or mislead
parsers (overlapping headers, out-of-file offsets, lying section/segment views,
hidden real section counts, bogus entry points). pyelftools largely trusts what
it reads, so this stage parses the headers at the raw byte level with `struct`
-- independent of pyelftools -- and checks the invariants the format guarantees.

Every inconsistency is a finding. A file that triggers several of these is
either corrupt or intentionally obfuscated; both are worth flagging loudly.

Nothing here executes the target.
"""
from __future__ import annotations

import struct
from typing import Dict, List, Optional, Tuple

from .util import Severity, StageResult


# Expected fixed sizes per ELF class.
_EXPECT = {
    64: {"ehsize": 64, "phentsize": 56, "shentsize": 64},
    32: {"ehsize": 52, "phentsize": 32, "shentsize": 40},
}

_PT_LOAD = 1
_PT_INTERP = 3
_PT_PHDR = 6
_PT_DYNAMIC = 2
_SHT_NOBITS = 8
_SHT_NULL = 0


class _Raw:
    """Minimal raw ELF reader. Never raises on bad data; records problems."""

    def __init__(self, blob: bytes):
        self.blob = blob
        self.size = len(blob)
        self.ok = False
        self.problems: List[Tuple[Severity, str, str]] = []
        self.ident = blob[:16] if len(blob) >= 16 else b""
        self.ei_class = 0
        self.endian = "<"
        self.header: Dict[str, int] = {}
        self.phdrs: List[Dict[str, int]] = []
        self.shdrs: List[Dict[str, int]] = []
        self._parse()

    def _flag(self, sev, title, detail=""):
        self.problems.append((sev, title, detail))

    def _parse(self):
        b = self.blob
        if self.size < 16 or b[:4] != b"\x7fELF":
            self._flag(Severity.HIGH, "Not an ELF / bad magic",
                       "e_ident does not start with 0x7f 'ELF'.")
            return

        ei_class = b[4]
        ei_data = b[5]
        ei_version = b[6]
        if ei_class not in (1, 2):
            self._flag(Severity.HIGH, "Invalid EI_CLASS", f"value={ei_class}")
            return
        self.ei_class = 64 if ei_class == 2 else 32
        if ei_data not in (1, 2):
            self._flag(Severity.MEDIUM, "Invalid EI_DATA", f"value={ei_data}")
        self.endian = ">" if ei_data == 2 else "<"
        if ei_version != 1:
            self._flag(Severity.LOW, "Unexpected EI_VERSION", f"value={ei_version}")

        e = self.endian
        is64 = self.ei_class == 64
        try:
            if is64:
                (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff,
                 e_flags, e_ehsize, e_phentsize, e_phnum, e_shentsize,
                 e_shnum, e_shstrndx) = struct.unpack_from(
                    e + "HHIQQQIHHHHHH", b, 16)
            else:
                (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff,
                 e_flags, e_ehsize, e_phentsize, e_phnum, e_shentsize,
                 e_shnum, e_shstrndx) = struct.unpack_from(
                    e + "HHIIIIIHHHHHH", b, 16)
        except struct.error as exc:
            self._flag(Severity.HIGH, "Truncated ELF header", str(exc))
            return

        self.header = dict(
            e_type=e_type, e_machine=e_machine, e_version=e_version,
            e_entry=e_entry, e_phoff=e_phoff, e_shoff=e_shoff, e_flags=e_flags,
            e_ehsize=e_ehsize, e_phentsize=e_phentsize, e_phnum=e_phnum,
            e_shentsize=e_shentsize, e_shnum=e_shnum, e_shstrndx=e_shstrndx,
        )
        self.ok = True
        self._check_header()
        self._parse_phdrs()
        self._parse_shdrs()

    # ---- header-level checks --------------------------------------------- #
    def _check_header(self):
        h = self.header
        exp = _EXPECT[self.ei_class]
        if h["e_ehsize"] != exp["ehsize"]:
            self._flag(Severity.MEDIUM, "Wrong e_ehsize",
                       f"{h['e_ehsize']} (expected {exp['ehsize']})")
        if h["e_phnum"] and h["e_phentsize"] != exp["phentsize"]:
            self._flag(Severity.MEDIUM, "Wrong e_phentsize",
                       f"{h['e_phentsize']} (expected {exp['phentsize']})")
        if h["e_shnum"] and h["e_shentsize"] != exp["shentsize"]:
            self._flag(Severity.MEDIUM, "Wrong e_shentsize",
                       f"{h['e_shentsize']} (expected {exp['shentsize']})")

        # Program header table must lie within the file.
        if h["e_phoff"]:
            end = h["e_phoff"] + h["e_phnum"] * h["e_phentsize"]
            if end > self.size:
                self._flag(Severity.HIGH, "Program header table out of bounds",
                           f"phoff+phnum*phentsize={end} > file size {self.size}")
        # Section header table must lie within the file.
        if h["e_shoff"]:
            end = h["e_shoff"] + h["e_shnum"] * h["e_shentsize"]
            if end > self.size:
                self._flag(Severity.HIGH, "Section header table out of bounds",
                           f"shoff+shnum*shentsize={end} > file size {self.size}")
        # shstrndx must be a valid section index.
        if h["e_shnum"] and h["e_shstrndx"] >= h["e_shnum"] and h["e_shstrndx"] < 0xff00:
            self._flag(Severity.MEDIUM, "e_shstrndx out of range",
                       f"{h['e_shstrndx']} >= e_shnum {h['e_shnum']}")
        # Entry of 0 for an executable/PIE is suspicious (but legal for some).
        if h["e_type"] in (2, 3) and h["e_entry"] == 0:
            self._flag(Severity.LOW, "Zero entry point",
                       "e_entry=0 for an executable/shared object.")

    # ---- program headers -------------------------------------------------- #
    def _parse_phdrs(self):
        h = self.header
        if not h["e_phoff"] or not h["e_phnum"]:
            return
        b, e = self.blob, self.endian
        is64 = self.ei_class == 64
        for i in range(h["e_phnum"]):
            off = h["e_phoff"] + i * h["e_phentsize"]
            if off + h["e_phentsize"] > self.size:
                break
            try:
                if is64:
                    (p_type, p_flags, p_offset, p_vaddr, p_paddr,
                     p_filesz, p_memsz, p_align) = struct.unpack_from(
                        e + "IIQQQQQQ", b, off)
                else:
                    (p_type, p_offset, p_vaddr, p_paddr, p_filesz,
                     p_memsz, p_flags, p_align) = struct.unpack_from(
                        e + "IIIIIIII", b, off)
            except struct.error:
                self._flag(Severity.MEDIUM, "Truncated program header", f"index {i}")
                break
            ph = dict(p_type=p_type, p_flags=p_flags, p_offset=p_offset,
                      p_vaddr=p_vaddr, p_paddr=p_paddr, p_filesz=p_filesz,
                      p_memsz=p_memsz, p_align=p_align)
            self.phdrs.append(ph)

            if p_offset + p_filesz > self.size:
                self._flag(Severity.HIGH, "Segment data past end of file",
                           f"PT index {i}: offset+filesz="
                           f"{p_offset + p_filesz} > {self.size}")
            if p_filesz > p_memsz:
                self._flag(Severity.MEDIUM, "Segment filesz > memsz",
                           f"PT index {i}: {p_filesz} > {p_memsz}")
            if p_align > 1 and (p_vaddr % p_align) != (p_offset % p_align):
                self._flag(Severity.LOW, "Segment vaddr/offset misaligned",
                           f"PT index {i}: p_align={p_align}")

        types = [p["p_type"] for p in self.phdrs]
        if not any(t == _PT_LOAD for t in types) and self.phdrs:
            self._flag(Severity.MEDIUM, "No PT_LOAD segment",
                       "Program headers present but nothing loadable.")
        if types.count(_PT_PHDR) > 1:
            self._flag(Severity.MEDIUM, "Multiple PT_PHDR", "Only one is valid.")
        if types.count(_PT_INTERP) > 1:
            self._flag(Severity.MEDIUM, "Multiple PT_INTERP segments", "")

    # ---- section headers -------------------------------------------------- #
    def _parse_shdrs(self):
        h = self.header
        # The "hidden section count" trick: e_shnum==0 while e_shoff!=0 means the
        # real count lives in section[0].sh_size.
        if h["e_shoff"] and h["e_shnum"] == 0:
            self._flag(Severity.MEDIUM, "Extended section count",
                       "e_shnum=0 with e_shoff set; real count is in "
                       "section[0].sh_size (valid, but often used to hide "
                       "sections from naive tools).")

        if not h["e_shoff"] or not h["e_shnum"]:
            if not h["e_shoff"]:
                self._flag(Severity.LOW, "No section header table",
                           "Section headers removed (common in packed/obfuscated "
                           "binaries; loader does not need them).")
            return

        b, e = self.blob, self.endian
        is64 = self.ei_class == 64
        file_ranges: List[Tuple[int, int, int]] = []  # (start,end,index)
        for i in range(h["e_shnum"]):
            off = h["e_shoff"] + i * h["e_shentsize"]
            if off + h["e_shentsize"] > self.size:
                break
            try:
                if is64:
                    (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
                     sh_link, sh_info, sh_addralign, sh_entsize) = \
                        struct.unpack_from(e + "IIQQQQIIQQ", b, off)
                else:
                    (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
                     sh_link, sh_info, sh_addralign, sh_entsize) = \
                        struct.unpack_from(e + "IIIIIIIIII", b, off)
            except struct.error:
                self._flag(Severity.MEDIUM, "Truncated section header", f"index {i}")
                break
            sh = dict(sh_name=sh_name, sh_type=sh_type, sh_flags=sh_flags,
                      sh_addr=sh_addr, sh_offset=sh_offset, sh_size=sh_size,
                      sh_entsize=sh_entsize, index=i)
            self.shdrs.append(sh)

            if sh_type not in (_SHT_NOBITS, _SHT_NULL) and sh_size:
                if sh_offset + sh_size > self.size:
                    self._flag(Severity.HIGH, "Section data past end of file",
                               f"section {i}: offset+size="
                               f"{sh_offset + sh_size} > {self.size}")
                else:
                    file_ranges.append((sh_offset, sh_offset + sh_size, i))

        # Overlapping section file ranges (legitimate layouts don't overlap
        # non-NOBITS allocated sections).
        file_ranges.sort()
        for (s1, e1, i1), (s2, e2, i2) in zip(file_ranges, file_ranges[1:]):
            if s2 < e1:
                self._flag(Severity.MEDIUM, "Overlapping sections",
                           f"section {i1} [{s1:#x}-{e1:#x}] overlaps "
                           f"section {i2} [{s2:#x}-{e2:#x}]")

    # ---- cross-view ------------------------------------------------------- #
    def cross_view_checks(self):
        """Entry point and section-vs-segment consistency."""
        h = self.header
        loads = [p for p in self.phdrs if p["p_type"] == _PT_LOAD]
        entry = h["e_entry"]

        # Entry must fall inside an executable PT_LOAD segment.
        if loads and entry:
            in_exec = any(
                p["p_vaddr"] <= entry < p["p_vaddr"] + p["p_memsz"]
                and (p["p_flags"] & 0x1)  # PF_X
                for p in loads)
            in_any = any(p["p_vaddr"] <= entry < p["p_vaddr"] + p["p_memsz"]
                         for p in loads)
            if not in_any:
                self._flag(Severity.HIGH, "Entry point outside all segments",
                           f"e_entry={entry:#x} is in no PT_LOAD segment.")
            elif not in_exec:
                self._flag(Severity.HIGH, "Entry point in non-executable segment",
                           f"e_entry={entry:#x} lands in a non-X segment "
                           "(shellcode/packer trampoline?).")

        # Allocated sections should map into some PT_LOAD segment.
        if loads:
            for sh in self.shdrs:
                if not (sh["sh_flags"] & 0x2):  # SHF_ALLOC
                    continue
                if sh["sh_size"] == 0 or sh["sh_addr"] == 0:
                    continue
                a0 = sh["sh_addr"]
                a1 = sh["sh_addr"] + sh["sh_size"]
                covered = any(p["p_vaddr"] <= a0 and a1 <= p["p_vaddr"] + p["p_memsz"]
                              for p in loads)
                if not covered:
                    self._flag(Severity.MEDIUM, "Allocated section outside segments",
                               f"section {sh['index']} vaddr {a0:#x} not inside "
                               "any PT_LOAD (section/segment views disagree).")
                    break  # one example is enough


def analyze_robustness(path: str) -> StageResult:
    res = StageResult("robustness")
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        res.error = f"read failed: {exc}"
        return res

    raw = _Raw(blob)
    if raw.ok:
        raw.cross_view_checks()

    res.data = {
        "parsed": raw.ok,
        "class": raw.ei_class,
        "num_program_headers": len(raw.phdrs),
        "num_section_headers": len(raw.shdrs),
        "integrity_issues": len(raw.problems),
    }
    for sev, title, detail in raw.problems:
        res.add(sev, "integrity", title, detail)

    if raw.ok and not raw.problems:
        # Clean bill of structural health is itself useful signal.
        res.data["note"] = "no structural inconsistencies detected"
    return res
