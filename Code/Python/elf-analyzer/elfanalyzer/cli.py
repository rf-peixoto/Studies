"""Command-line interface and stage orchestration."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional

from . import __version__
from . import static_analysis as S
from . import dynamic_analysis as D
from . import tools as T
from .report import Report
from .util import make_color

# Static stage name -> callable(path, tools, outdir) wrapper key.
STATIC_STAGES = [
    "fileid", "hashes", "header", "entropy", "packing",
    "strings", "imports", "anomalies",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="elfanalyzer",
        description="Modular ELF analysis framework. Static by default; "
                    "dynamic and interactive stages are opt-in.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    p.add_argument("target", nargs="?", help="ELF file to analyze")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # Stage selection.
    g = p.add_argument_group("stages")
    g.add_argument("--static", action="store_true",
                   help="run static analysis (default when no stage is given)")
    g.add_argument("--mitigations", action="store_true",
                   help="add checksec-style mitigation analysis (static)")
    g.add_argument("--entropy-check", action="store_true", dest="entropy_check",
                   help="static: block-by-block entropy map with a table")
    g.add_argument("--dynamic", action="store_true",
                   help="EXECUTE sample: strace + ltrace (+ optional capture)")
    g.add_argument("--supervise", action="store_true",
                   help="EXECUTE sample under the interactive syscall gate")
    g.add_argument("--gdb", action="store_true",
                   help="launch gdb on the target")
    g.add_argument("--memdump", action="store_true",
                   help="dynamic: snapshot process memory while it runs")
    g.add_argument("--tcpdump", action="store_true",
                   help="dynamic: capture packets while it runs (needs root)")
    g.add_argument("--all", action="store_true",
                   help="run everything, including interactive stages")
    g.add_argument("--only", metavar="LIST",
                   help="comma-separated static stages to run exclusively "
                        f"(choices: {','.join(STATIC_STAGES)},mitigations)")

    # Dynamic / behavior options.
    d = p.add_argument_group("execution options")
    d.add_argument("--args", nargs=argparse.REMAINDER, default=[],
                   help="arguments passed to the sample (must be last)")
    d.add_argument("--timeout", type=int, default=20,
                   help="per-stage timeout for dynamic runs (s, default 20)")
    d.add_argument("--block-size", type=int, default=0, dest="block_size",
                   help="--entropy-check block size in bytes (0 = auto-scale "
                        "to the file so the table stays readable)")
    d.add_argument("--unpack", action="store_true",
                   help="if UPX-packed and upx is present, unpack and re-run "
                        "static analysis on the unpacked copy")
    d.add_argument("-y", "--yes", action="store_true",
                   help="assume yes: skip execution confirmation prompts")

    # Tooling / output.
    o = p.add_argument_group("output / tooling")
    o.add_argument("--outdir", help="report directory (default: auto-named)")
    o.add_argument("--json-only", action="store_true",
                   help="suppress terminal summary; just write report.json")
    o.add_argument("--no-color", action="store_true", help="disable colored output")
    o.add_argument("--check-tools", action="store_true",
                   help="report external tool availability and exit")
    o.add_argument("--install-deps", action="store_true",
                   help="apt-install missing tools without prompting (trixie)")
    o.add_argument("--batch", metavar="DIR",
                   help="analyze every ELF in DIR (static only)")
    return p


_EPILOG = """\
examples:
  elfanalyzer sample                 static analysis only (safe)
  elfanalyzer sample --mitigations   add checksec-style mitigations
  elfanalyzer sample --only strings,imports
  elfanalyzer sample --supervise     interactive syscall gate (executes it!)
  elfanalyzer sample --dynamic --tcpdump --timeout 30
  elfanalyzer sample --all -y        everything, no prompts
  elfanalyzer --batch ./samples      static sweep of a directory
  elfanalyzer --check-tools          what's installed / how to install
"""


def _auto_outdir(target: str) -> str:
    base = os.path.basename(target.rstrip("/")) or "elf"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.abspath(f"elf-report-{base}-{stamp}")


def _ensure_tools(needed, install: bool, assume_yes: bool) -> T.ToolStatus:
    status = T.detect()
    missing = status.missing(needed)
    if missing:
        if install:
            T.offer_install(missing, assume_yes=True)
            status = T.detect()
        elif sys.stdin.isatty():
            T.offer_install(missing, assume_yes=False)
            status = T.detect()
        else:
            c = make_color(False)
            print(c.dim(f"note: missing tools {missing}; stages will degrade. "
                        f"{T.apt_command(missing)}"))
    return status


def run_static(target: str, tools, outdir: str, report: Report,
               selected: Optional[List[str]], do_mitigations: bool):
    sel = set(selected) if selected else set(STATIC_STAGES)
    if "fileid" in sel:
        report.add(S.analyze_fileid(target, tools))
    if "hashes" in sel:
        report.add(S.analyze_hashes(target))
    if "header" in sel:
        report.add(S.analyze_header(target))
    if do_mitigations or (selected and "mitigations" in selected):
        report.add(S.analyze_mitigations(target))
    if "entropy" in sel:
        report.add(S.analyze_entropy(target))
    if "packing" in sel:
        report.add(S.analyze_packing(target, tools))
    if "strings" in sel:
        report.add(S.analyze_strings(target, tools, outdir))
    if "imports" in sel:
        report.add(S.analyze_imports(target))
    if "anomalies" in sel:
        report.add(S.analyze_anomalies(target))


def analyze_one(target: str, args, tools, outdir: str) -> Report:
    os.makedirs(outdir, exist_ok=True)
    report = Report(target, outdir)

    selected = None
    if args.only:
        selected = [s.strip() for s in args.only.split(",") if s.strip()]

    # --- static (default on unless an exclusive non-static stage chosen) --- #
    want_static = (args.static or args.all or args.only or args.mitigations
                   or args.entropy_check
                   or not (args.dynamic or args.supervise or args.gdb
                           or args.memdump or args.tcpdump))

    # Block entropy map is its own opt-in stage (not in the default set).
    if args.entropy_check or args.all:
        report.add(S.analyze_block_entropy(target, block_size=args.block_size))

    # If entropy-check is the ONLY static thing asked for, don't also run the
    # whole default static suite -- just the map (plus anything else requested).
    only_entropy = (args.entropy_check and not (args.static or args.all
                    or args.only or args.mitigations))
    run_full_static = want_static and not only_entropy

    if run_full_static:
        run_static(target, tools, outdir, report, selected,
                   do_mitigations=args.mitigations or args.all)

        # Optional UPX unpack + re-scan.
        packing = report._stage("packing")
        if args.unpack and packing and packing.data.get("packed"):
            unpacked = S.unpack_upx(target, tools, outdir)
            if unpacked:
                print(f"  unpacked -> {unpacked}; re-running static analysis")
                sub = Report(unpacked, outdir)
                run_static(unpacked, tools, outdir, sub, selected,
                           do_mitigations=args.mitigations or args.all)
                for st in sub.stages:
                    st.name = f"unpacked:{st.name}"
                    report.add(st)

    # --- dynamic suite ----------------------------------------------------- #
    if args.dynamic or args.all:
        for st in D.run_dynamic_suite(
            target, args.args, tools, outdir, args.timeout,
            assume_yes=args.yes,
            do_tcpdump=args.tcpdump or args.all,
            do_memdump=args.memdump or args.all,
        ):
            report.add(st)
    else:
        # Allow tcpdump/memdump without the full suite.
        if args.tcpdump:
            report.add(D.run_tcpdump(target, args.args, tools, outdir, args.timeout))
        if args.memdump:
            report.add(D.run_memdump(target, args.args, outdir, args.timeout))

    # --- interactive syscall gate ------------------------------------------ #
    if args.supervise or args.all:
        from . import supervisor
        report.add(supervisor.supervise(target, args.args, outdir,
                                         auto_allow_all=False))

    # --- gdb (last; it takes over the terminal) ---------------------------- #
    if args.gdb or args.all:
        from . import interactive
        report.add(interactive.launch_gdb(target, args.args, tools, outdir))

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    color_force = False if args.no_color else None

    # --check-tools short-circuit.
    if args.check_tools:
        status = T.detect()
        print(T.report_tools(status))
        return 0

    # Decide which tools matter for the requested stages.
    needed = ["file", "readelf", "objdump", "nm", "strings"]
    if args.dynamic or args.all:
        needed += ["strace", "ltrace"]
    if args.tcpdump or args.all:
        needed += ["tcpdump"]
    if args.gdb or args.all:
        needed += ["gdb"]
    if args.unpack:
        needed += ["upx"]

    # --- batch mode -------------------------------------------------------- #
    if args.batch:
        if not os.path.isdir(args.batch):
            parser.error(f"--batch: not a directory: {args.batch}")
        tools = _ensure_tools(needed, args.install_deps, args.yes)
        root_out = args.outdir or os.path.abspath(
            f"elf-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        os.makedirs(root_out, exist_ok=True)
        count = 0
        for name in sorted(os.listdir(args.batch)):
            fpath = os.path.join(args.batch, name)
            if not os.path.isfile(fpath) or not S.is_elf(fpath):
                continue
            count += 1
            sub_out = os.path.join(root_out, name)
            # Batch is static-only for safety.
            batch_args = argparse.Namespace(**vars(args))
            batch_args.dynamic = batch_args.supervise = batch_args.gdb = False
            batch_args.memdump = batch_args.tcpdump = batch_args.all = False
            rep = analyze_one(fpath, batch_args, tools, sub_out)
            rep.write_json()
            if not args.json_only:
                rep.print_entropy_map(color_force)
                rep.print_summary(color_force)
        print(f"\nBatch complete: {count} ELF file(s). Reports under {root_out}/")
        return 0

    # --- single file ------------------------------------------------------- #
    if not args.target:
        parser.error("a target ELF file is required (or use --batch / --check-tools)")
    if not os.path.isfile(args.target):
        parser.error(f"not a file: {args.target}")
    if not S.is_elf(args.target):
        c = make_color(color_force)
        print(c.yellow(f"warning: {args.target} does not start with the ELF "
                       "magic; analyzing anyway."))

    if not S.HAVE_PYELFTOOLS:
        print("error: pyelftools is required. Run ./install.sh first.",
              file=sys.stderr)
        return 2

    tools = _ensure_tools(needed, args.install_deps, args.yes)
    outdir = args.outdir or _auto_outdir(args.target)
    report = analyze_one(args.target, args, tools, outdir)

    json_path = report.write_json()
    if args.json_only:
        print(json_path)
    else:
        report.print_entropy_map(color_force)
        report.print_summary(color_force)
    return 0
