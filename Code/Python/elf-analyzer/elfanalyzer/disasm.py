"""Disassembly and disassembly-based signals (Capstone).

Linear-sweep disassembly of the executable sections, used to extract behavioral
signals that import/string analysis cannot see:

  * direct syscall instructions (syscall / int 0x80 / svc) -- code talking to
    the kernel without going through libc, typical of shellcode and evasive
    malware;
  * anti-analysis / VM-detection instructions (rdtsc, cpuid, sidt/sgdt/sldt,
    smsw, in/out) used for timing checks and "red pill" sandbox detection;
  * get-PC / position-independent shellcode prologues (call $+5; pop reg);
  * indirect call/jump density (obfuscation, dynamic dispatch);
  * undecodable-byte ratio in a section that claims to be code (a strong packing
    / encryption signal -- real code decodes cleanly).

Linear sweep (not recursive-descent) is used deliberately: it is robust and
fast, at the cost of occasional misalignment in data-in-code regions -- which is
itself surfaced via the undecodable ratio. Disassembly is bounded in size.

Nothing here executes the target. Requires the `capstone` package.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from .util import Severity, StageResult

try:
    import capstone
    from capstone import Cs, CsError
    HAVE_CAPSTONE = True
except ImportError:
    HAVE_CAPSTONE = False

try:
    from elftools.elf.elffile import ELFFile
    from elftools.common.exceptions import ELFError
except ImportError:  # guarded at CLI level
    ELFFile = None


# ELF e_machine -> (capstone arch, mode). Only the reliably-supported ones.
def _cs_for_machine(machine: str, elfclass: int, little: bool):
    if not HAVE_CAPSTONE:
        return None
    endian = capstone.CS_MODE_LITTLE_ENDIAN if little else capstone.CS_MODE_BIG_ENDIAN
    if machine in ("EM_X86_64", "x64"):
        return Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    if machine in ("EM_386", "EM_IAMCU"):
        return Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    if machine == "EM_AARCH64":
        return Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM | endian)
    if machine == "EM_ARM":
        return Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM | endian)
    if machine == "EM_MIPS":
        mode = (capstone.CS_MODE_MIPS64 if elfclass == 64 else capstone.CS_MODE_MIPS32)
        return Cs(capstone.CS_ARCH_MIPS, mode | endian)
    return None


# Instruction sets of interest, by architecture family.
_SYSCALL_MNEMONICS = {"syscall", "sysenter", "svc", "swi"}
_VM_ANTIDBG = {"rdtsc", "rdtscp", "cpuid", "sidt", "sgdt", "sldt", "smsw",
               "in", "out", "ins", "outs", "vmcall", "vmmcall"}
_INT_MNEMONIC = {"int"}

# Register-operand indirect control flow (x86 + arm variants).
_INDIRECT_CF = {"call", "jmp", "blr", "br", "bx", "blx"}

MAX_DISASM_BYTES = 4 * 1024 * 1024  # cap work for huge binaries


def _is_indirect(insn) -> bool:
    m = insn.mnemonic
    if m not in _INDIRECT_CF:
        return False
    op = insn.op_str.strip()
    if not op:
        return False
    # Indirect if the target is a register or memory ([...]), not an immediate.
    if op.startswith("0x") or op.lstrip("#").lstrip().startswith("0x"):
        return False
    if op.startswith("[") or op.startswith("*"):
        return True
    # bare register operand (rax, x0, r3, ...)
    first = op.split(",")[0].strip()
    return not first.startswith("0x") and not first.startswith("#")


def _disassemble_section(md, code: bytes, addr: int) -> Tuple[List, int]:
    """Linear sweep with skipdata so undecodable bytes don't stop the sweep.

    Returns (instructions, skipped_bytes). Skipped bytes are emitted by capstone
    as a pseudo-instruction when md.skipdata is on; we count their size.
    """
    md.skipdata = True
    insns = []
    skipped = 0
    try:
        for insn in md.disasm(code, addr):
            # capstone's skipdata pseudo-insn uses mnemonic ".byte".
            if insn.mnemonic == ".byte":
                skipped += insn.size
            else:
                insns.append(insn)
    except CsError:
        pass
    return insns, skipped


def analyze_disasm(path: str, outdir: Optional[str] = None,
                   dump: bool = True) -> StageResult:
    res = StageResult("disasm")
    if not HAVE_CAPSTONE:
        res.error = ("capstone not installed; run install.sh "
                     "(pip install capstone).")
        return res
    if ELFFile is None:
        res.error = "pyelftools missing"
        return res

    try:
        fh = open(path, "rb")
        elf = ELFFile(fh)
    except (OSError, Exception) as exc:  # noqa: BLE001 - malformed input tolerated
        res.error = f"could not open ELF for disassembly: {exc}"
        return res

    machine = elf.header["e_machine"]
    md = _cs_for_machine(machine, elf.elfclass, elf.little_endian)
    if md is None:
        res.error = f"unsupported architecture for disassembly: {machine}"
        fh.close()
        return res
    md.detail = False

    totals = {
        "instructions": 0, "skipped_bytes": 0, "code_bytes": 0,
        "syscalls": 0, "int80": 0, "vm_antidbg": {}, "indirect_cf": 0,
        "xor": 0, "getpc": 0, "int3": 0,
    }
    exec_sections = []
    dump_lines: List[str] = []
    budget = MAX_DISASM_BYTES

    try:
        for sec in elf.iter_sections():
            flags = sec["sh_flags"]
            if not (flags & 0x4):  # SHF_EXECINSTR
                continue
            if sec["sh_type"] == "SHT_NOBITS" or sec["sh_size"] == 0:
                continue
            code = sec.data()
            if budget <= 0:
                break
            if len(code) > budget:
                code = code[:budget]
            budget -= len(code)
            addr = sec["sh_addr"]

            insns, skipped = _disassemble_section(md, code, addr)
            totals["code_bytes"] += len(code)
            totals["skipped_bytes"] += skipped
            totals["instructions"] += len(insns)
            exec_sections.append({
                "name": sec.name, "addr": hex(addr), "size": len(code),
                "instructions": len(insns), "undecodable_bytes": skipped,
            })

            prev = None
            for insn in insns:
                m = insn.mnemonic
                if m in _SYSCALL_MNEMONICS:
                    totals["syscalls"] += 1
                elif m in _INT_MNEMONIC:
                    if insn.op_str.strip() == "0x80":
                        totals["int80"] += 1
                        totals["syscalls"] += 1
                    elif insn.op_str.strip() in ("3", "0x3"):
                        totals["int3"] += 1
                elif m == "int3":  # some decoders emit this directly
                    totals["int3"] += 1
                elif m in _VM_ANTIDBG:
                    totals["vm_antidbg"][m] = totals["vm_antidbg"].get(m, 0) + 1
                elif m == "xor":
                    # self-xor (zeroing) excluded: operands differ => real xor
                    ops = [o.strip() for o in insn.op_str.split(",")]
                    if len(ops) == 2 and ops[0] != ops[1]:
                        totals["xor"] += 1
                if _is_indirect(insn):
                    totals["indirect_cf"] += 1
                # get-PC shellcode prologue: call to the immediately-following
                # instruction, usually followed by a pop.
                if m == "call":
                    op = insn.op_str.strip()
                    if op.startswith("0x"):
                        try:
                            if int(op, 16) == insn.address + insn.size:
                                totals["getpc"] += 1
                        except ValueError:
                            pass
                if dump and len(dump_lines) < 200000:
                    dump_lines.append(
                        f"{insn.address:#010x}:  {m:<8} {insn.op_str}")
                prev = insn
    except Exception as exc:  # noqa: BLE001 - never crash on crafted input
        res.data["partial_error"] = str(exc)
    finally:
        fh.close()

    # Write the disassembly artifact.
    dump_path = None
    if dump and outdir and dump_lines:
        dump_path = os.path.join(outdir, "disasm.txt")
        with open(dump_path, "w", errors="replace") as out:
            out.write("\n".join(dump_lines))

    code_bytes = totals["code_bytes"] or 1
    undecodable_ratio = totals["skipped_bytes"] / code_bytes
    res.data.update({
        "architecture": machine,
        "exec_sections": exec_sections,
        "instructions": totals["instructions"],
        "undecodable_bytes": totals["skipped_bytes"],
        "undecodable_ratio": round(undecodable_ratio, 4),
        "direct_syscalls": totals["syscalls"],
        "int80_syscalls": totals["int80"],
        "vm_antidebug_instructions": totals["vm_antidbg"],
        "indirect_control_flow": totals["indirect_cf"],
        "real_xor_instructions": totals["xor"],
        "getpc_prologues": totals["getpc"],
        "int3_count": totals["int3"],
        "disasm_file": dump_path,
    })

    # --- signals ----------------------------------------------------------- #
    if totals["syscalls"] >= 1:
        sev = Severity.MEDIUM if totals["syscalls"] >= 3 else Severity.LOW
        res.add(sev, "disasm", f"{totals['syscalls']} direct syscall instruction(s)",
                "Code invokes the kernel without going through libc "
                "(shellcode/evasion-shaped).")
    if totals["vm_antidbg"]:
        names = ", ".join(f"{k}×{v}" for k, v in totals["vm_antidbg"].items())
        # sidt/sgdt/sldt/smsw are classic VM red-pills -> higher severity.
        redpill = any(k in totals["vm_antidbg"] for k in ("sidt", "sgdt", "sldt", "smsw"))
        res.add(Severity.HIGH if redpill else Severity.MEDIUM, "disasm",
                "Anti-analysis / VM-detection instructions", names)
    if totals["getpc"]:
        res.add(Severity.MEDIUM, "disasm",
                f"{totals['getpc']} get-PC prologue(s)",
                "call/pop position-independent code pattern (shellcode).")
    if undecodable_ratio >= 0.30 and code_bytes > 512:
        sev = Severity.HIGH if undecodable_ratio >= 0.6 else Severity.MEDIUM
        res.add(sev, "disasm",
                f"{undecodable_ratio*100:.0f}% of code is undecodable",
                "Executable section does not disassemble cleanly — likely "
                "packed, encrypted, or data-in-code.")
    if totals["instructions"] and totals["indirect_cf"] / max(1, totals["instructions"]) >= 0.08:
        res.add(Severity.LOW, "disasm",
                "High indirect control-flow density",
                f"{totals['indirect_cf']} register/memory call|jmp "
                "(obfuscation or dynamic dispatch).")
    if totals["instructions"] and totals["xor"] / max(1, totals["instructions"]) >= 0.10:
        res.add(Severity.LOW, "disasm",
                "XOR-heavy code",
                f"{totals['xor']} non-zeroing xor instructions "
                "(possible in-code decryption).")

    return res
