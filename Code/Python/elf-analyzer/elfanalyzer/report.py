"""Report assembly: JSON file + colored terminal summary + suspicion score."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List

from .util import Severity, SEVERITY_WEIGHT, StageResult, make_color


# Score thresholds -> verdict label.
def _verdict(score: int) -> str:
    if score >= 18:
        return "HIGH"
    if score >= 8:
        return "MEDIUM"
    if score >= 3:
        return "LOW"
    return "MINIMAL"


class Report:
    def __init__(self, target: str, outdir: str):
        self.target = target
        self.outdir = outdir
        self.stages: List[StageResult] = []
        self.created = datetime.now(timezone.utc).isoformat()

    def add(self, stage: StageResult):
        if stage is not None:
            self.stages.append(stage)

    # ---- scoring ---------------------------------------------------------- #
    def score(self) -> int:
        total = 0
        for stage in self.stages:
            for f in stage.findings:
                total += SEVERITY_WEIGHT.get(f.severity, 0)
        return total

    def all_findings(self):
        for stage in self.stages:
            for f in stage.findings:
                yield stage.name, f

    # ---- JSON ------------------------------------------------------------- #
    def to_dict(self) -> dict:
        score = self.score()
        return {
            "target": self.target,
            "created_utc": self.created,
            "suspicion_score": score,
            "verdict": _verdict(score),
            "stages": [s.to_dict() for s in self.stages],
        }

    def write_json(self) -> str:
        path = os.path.join(self.outdir, "report.json")
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2, default=str)
        return path

    # ---- terminal --------------------------------------------------------- #
    def print_summary(self, color_force=None):
        c = make_color(color_force)
        score = self.score()
        verdict = _verdict(score)

        print()
        print(c.bold("=" * 70))
        print(c.bold(f" ELF ANALYSIS SUMMARY — {os.path.basename(self.target)}"))
        print(c.bold("=" * 70))

        # Header facts, if available.
        hdr = self._stage("header")
        hashes = self._stage("hashes")
        if hashes and hashes.data:
            print(f" sha256 : {hashes.data.get('sha256')}")
            print(f" md5    : {hashes.data.get('md5')}")
            print(f" size   : {hashes.data.get('size_human')}")
        if hdr and hdr.data:
            d = hdr.data
            flags = []
            flags.append("PIE" if d.get("pie") else "no-PIE")
            flags.append("static" if d.get("statically_linked") else "dynamic")
            flags.append("stripped" if d.get("stripped") else "symbols")
            print(f" type   : {d.get('class')} {d.get('machine')} "
                  f"{d.get('type_desc')} [{', '.join(flags)}]")
            print(f" entry  : {d.get('entry_point')}")

        # Mitigations line, if run.
        mit = self._stage("mitigations")
        if mit and mit.data:
            m = mit.data
            def onoff(v): return c.green("on") if v else c.red("off")
            print(f" mitig. : NX={onoff(m.get('nx'))} PIE={onoff(m.get('pie'))} "
                  f"RELRO={m.get('relro')} canary={onoff(m.get('stack_canary'))} "
                  f"fortify={onoff(m.get('fortify_source'))}")

        # Verdict.
        vcolor = {"HIGH": c.red, "MEDIUM": c.yellow,
                  "LOW": c.cyan, "MINIMAL": c.green}[verdict]
        print()
        print(f" suspicion score: {vcolor(str(score))}  -> {vcolor(verdict)}")

        # Findings grouped by severity (skip pure INFO noise at the top).
        order = [Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        sev_color = {Severity.HIGH: c.red, Severity.MEDIUM: c.yellow,
                     Severity.LOW: c.cyan, Severity.INFO: c.dim}
        findings = list(self.all_findings())
        shown = False
        for sev in order:
            group = [(s, f) for s, f in findings if f.severity == sev]
            if not group:
                continue
            shown = True
            print()
            print(c.bold(f" {sev.value.upper()} findings:"))
            for stage_name, f in group:
                tag = sev_color[sev](f"[{sev.value}]")
                print(f"   {tag} ({stage_name}/{f.category}) {f.title}")
                if f.detail:
                    print(c.dim(f"        {f.detail}"))
        if not shown:
            print(c.green("\n No notable static findings."))

        # Errors.
        errs = [(s.name, s.error) for s in self.stages if s.error]
        if errs:
            print()
            print(c.bold(" stage errors:"))
            for name, err in errs:
                print(c.dim(f"   {name}: {err}"))

        print()
        print(c.dim(f" full report: {os.path.join(self.outdir, 'report.json')}"))
        print(c.dim(f" artifacts  : {self.outdir}/"))
        print(c.bold("=" * 70))

    def print_entropy_map(self, color_force=None, bar_width: int = 34,
                          max_rows: int = 160):
        """Render the --entropy-check block map as a table with a visual bar."""
        stage = self._stage("entropy_map")
        if not stage or stage.error or not stage.data:
            if stage and stage.error:
                c = make_color(color_force)
                print(c.dim(f" entropy map: {stage.error}"))
            return
        c = make_color(color_force)
        d = stage.data
        blocks = d["blocks"]

        print()
        print(c.bold("=" * 70))
        print(c.bold(f" ENTROPY MAP — {os.path.basename(self.target)}"))
        print(c.bold("=" * 70))
        print(f" block size : {d['block_size']} bytes   "
              f"blocks: {d['num_blocks']}   file: {d['file_size']} bytes")
        print(f" entropy    : min {d['min_entropy']:.2f}  "
              f"mean {d['mean_entropy']:.2f}  max {d['max_entropy']:.2f}  "
              "(bits/byte, 0-8)")
        print(c.dim(" offset        entropy  level"))

        # Downsample display if there are a lot of blocks (findings already use
        # the full-resolution series; this only trims the printed table).
        step = max(1, (len(blocks) + max_rows - 1) // max_rows)
        if step > 1:
            print(c.dim(f" (showing every {step}th block; full data in report.json)"))

        for i in range(0, len(blocks), step):
            b = blocks[i]
            ent = b["entropy"]
            filled = int(round((ent / 8.0) * bar_width))
            bar = "█" * filled + "·" * (bar_width - filled)
            # Color the bar by band.
            if ent >= 7.2:
                bar = c.red(bar)
            elif ent >= 6.5:
                bar = c.yellow(bar)
            elif ent >= 5.0:
                bar = c.cyan(bar)
            else:
                bar = c.green(bar)
            print(f" {b['offset']:#010x}  {bar} {ent:5.2f}")

        print(c.dim(" legend: "
                    + c.green("low") + "  "
                    + c.cyan("structured") + "  "
                    + c.yellow("dense") + "  "
                    + c.red(">=7.2 packed/encrypted")))
        print(c.bold("=" * 70))

    def _stage(self, name: str):
        for s in self.stages:
            if s.name == name:
                return s
        return None
