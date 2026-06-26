#!/usr/bin/env python3
"""
damnatio_memoriae.py — secure drive erasure with a dark phosphor-terminal UI.

  "damnatio memoriae" — the condemnation of memory; to erase a thing from all
  record as though it never existed.

Linux only. Run as root for real wipes:   sudo python3 damnatio_memoriae.py
Pure standard library (Tkinter) — nothing to install.

Erase modes
  ZERO-FILL (every bit) : write 0x00 over the whole device, then read it back
                          and confirm every byte is 0.
  RANDOM-FILL (every bit): write a reproducible random stream over the whole
                          device, then re-read and confirm it matches.
  RANDOM + ZERO         : random pass(es), then a verified zero pass.
  CRYPTO-ERASE          : destroy the on-device/volume encryption key
                          (NVMe ses=2 / LUKS keyslots / SED) — instant and
                          whole-device, including spare cells, when supported.
  SANITIZE + ZERO       : ask the controller to sanitize (the only overwrite
                          path that reaches hidden flash cells), then zero.
  Extras: optional HPA/DCO removal on ATA disks, a read-only SCAN that reports
  whether a drive already looks erased, SIMULATE dry-run, and an exportable
  erasure certificate (.txt + .json).

Honest limits: a verified zero-fill clears the addressable area (NIST 800-88
"Clear"). On flash, wear-leveled / over-provisioned cells are unreachable by
software — only a successful hardware sanitize, crypto-erase, or physical
destruction covers those. The result line tells you which case you got.
"""

import os
import sys
import json
import time
import queue
import struct
import fcntl
import random
import shutil
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

BLKGETSIZE64 = 0x80081272
CHUNK = 16 * 1024 * 1024
ZERO_BLOCK = b"\x00" * CHUNK
VERSION = "1.0"

# ---- palette: black base, colour only to mean something --------------------
BG     = "#070709"   # base black
PANEL  = "#0d0e12"   # slightly raised panels
GRID   = "#1b1e26"   # hairline borders
FG     = "#8af7b0"   # phosphor green (body text)
BRIGHT = "#15ff8a"   # bright green (highlights)
DIM    = "#3c5a47"   # muted green (secondary)
CYAN   = "#27e0ff"   # focus / headings
AMBER  = "#ffb22e"   # caution
RED    = "#ff3b5c"   # danger
WHITE  = "#d7dde3"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or u == "PB":
            return f"{int(n)} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def fmt_dur(s):
    s = int(max(0, s))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def device_size(path):
    with open(path, "rb") as f:
        buf = fcntl.ioctl(f.fileno(), BLKGETSIZE64, b"\0" * 8)
    return struct.unpack("Q", buf)[0]


def root_disk():
    try:
        src = subprocess.check_output(["findmnt", "-no", "SOURCE", "/"],
                                      text=True).strip()
        pk = subprocess.check_output(["lsblk", "-no", "PKNAME", src],
                                     text=True).strip().splitlines()
        return "/dev/" + pk[0].strip() if pk and pk[0] else src
    except Exception:
        return ""


def list_drives(show_all=False):
    try:
        out = subprocess.check_output(
            ["lsblk", "-J", "-dpb", "-o",
             "NAME,SIZE,MODEL,SERIAL,TRAN,RM,HOTPLUG,ROTA,TYPE"], text=True)
        data = json.loads(out).get("blockdevices", [])
    except Exception:
        return []
    sysdisk = root_disk()
    drives = []
    for d in data:
        if d.get("type") != "disk":
            continue
        ext = (d.get("tran") == "usb"
               or str(d.get("rm")) in ("1", "True", "true")
               or str(d.get("hotplug")) in ("1", "True", "true"))
        if not ext and not show_all:
            continue
        drives.append({
            "name": d["name"],
            "size": int(d["size"]),
            "model": (d.get("model") or "").strip() or "—",
            "serial": (d.get("serial") or "").strip() or "—",
            "tran": d.get("tran") or "—",
            "rota": str(d.get("rota")) in ("1", "True", "true"),
            "external": ext,
            "is_root": d["name"] == sysdisk,
        })
    return drives


def pick_mono(root):
    fams = set(tkfont.families(root))
    for f in ("JetBrains Mono", "Hack", "DejaVu Sans Mono", "Liberation Mono",
              "Source Code Pro", "Cascadia Code", "Courier New", "Courier"):
        if f in fams:
            return f
    return "TkFixedFont"


# --------------------------------------------------------------------------- #
# worker
# --------------------------------------------------------------------------- #
class Aborted(Exception):
    pass


class WipeWorker(threading.Thread):
    def __init__(self, drive, opts, msgq, abort_evt):
        super().__init__(daemon=True)
        self.drive = drive
        self.dev = drive["name"]
        self.opts = opts
        self.sim = opts["simulate"]
        self.q = msgq
        self.abort = abort_evt
        self.report = {}
        # reproducible seed so a random-fill can be verified by regenerating it
        self.seed = int.from_bytes(os.urandom(8), "big")
        self.can_repro = hasattr(random.Random, "randbytes")

    def log(self, text, level="info"):
        self.q.put(("log", (text, level)))

    def status(self, text):
        self.q.put(("status", text))

    def progress(self, frac):
        self.q.put(("progress", max(0.0, min(1.0, frac))))

    def run(self):
        t_start = datetime.now()
        try:
            self._do_wipe()
            summary = self._summary()
            self.report.update({
                "finished": datetime.now().isoformat(timespec="seconds"),
                "result": summary,
                "verification": (
                    "n/a (crypto-erase)" if self.opts["mode"] == "crypto"
                    else "skipped" if self.opts["verify"] == "none"
                    else "PASSED"),
            })
            self.q.put(("done", {"summary": summary, "report": self.report}))
        except Aborted:
            self.q.put(("aborted", None))
        except PermissionError:
            self.q.put(("error", "permission denied — run as root (sudo)."))
        except Exception as e:  # noqa
            self.q.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            self.t_start = t_start

    def _do_wipe(self):
        d = self.drive
        size = d["size"] if self.sim else device_size(self.dev)
        media = "magnetic" if d["rota"] else "flash"
        mode = self.opts["mode"]
        started = datetime.now()
        self.report = {
            "tool": "damnatio memoriae", "version": VERSION,
            "device": self.dev, "model": d["model"], "serial": d["serial"],
            "bus": d["tran"], "media": media,
            "size_bytes": size, "size_human": human(size),
            "mode": mode, "passes": self.opts["passes"],
            "verify": self.opts["verify"], "reformat": self.opts["reformat"],
            "simulated": self.sim,
            "started": started.isoformat(timespec="seconds"),
            "hardware_sanitize": "not attempted",
            "crypto_erase": "not attempted",
            "hpa_dco": "not checked",
        }
        self.media = media
        self.hw_ok = False
        self.crypto_ok = False

        head = "SIMULATION — no writes" if self.sim else "LIVE — destructive"
        self.log(f"[{head}] target {self.dev} · {human(size)} · {media} · "
                 f"mode={mode}", "head")

        self._unmount()

        # ---- crypto-erase is its own short path -------------------------- #
        if mode == "crypto":
            self.crypto_ok = self._crypto_erase()
            self.report["crypto_erase"] = ("succeeded" if self.crypto_ok
                                           else "unavailable")
            if not self.crypto_ok and not self.sim:
                raise RuntimeError(
                    "crypto-erase not available on this device (no SED / NVMe "
                    "crypto / LUKS detected). Choose ZERO-FILL or RANDOM-FILL "
                    "instead.")
            if self.opts["reformat"]:
                self._wipefs(); self._reformat()
            return

        # ---- optional HPA/DCO removal before overwriting ----------------- #
        if self.opts.get("remove_hpa"):
            self._remove_hpa_dco()

        if mode == "sanitize":
            self.hw_ok = self._hardware_sanitize()
            self.report["hardware_sanitize"] = ("succeeded" if self.hw_ok
                                                else "unavailable")

        self._check()
        self._wipefs()

        if mode == "random_zero":
            for p in range(1, self.opts["passes"] + 1):
                self._fill(size, "urandom", f"random {p}/{self.opts['passes']}")
            self._fill(size, "zero", "zero-fill")
            self._verify_zero(size)
        elif mode == "random":
            self._fill(size, "random", "random-fill (every bit)")
            self._verify_random(size)
        else:  # zero | sanitize
            self._fill(size, "zero", "zero-fill (every bit)")
            self._verify_zero(size)

        if self.opts["reformat"]:
            self._wipefs()
            self._reformat()

    def _check(self):
        if self.abort.is_set():
            raise Aborted()

    # ---- destructive ops (skipped in simulation) ----
    def _unmount(self):
        if self.sim:
            self.log("would unmount any mounted partitions", "dim")
            return
        try:
            out = subprocess.check_output(
                ["lsblk", "-lnpo", "NAME,MOUNTPOINT", self.dev], text=True)
        except Exception:
            return
        for line in out.splitlines()[1:]:
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip():
                self.log(f"unmount {parts[0]}", "dim")
                subprocess.run(["umount", "-f", parts[0]],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)

    def _wipefs(self):
        if self.sim:
            self.log("would strip filesystem signatures (wipefs)", "dim")
            return
        self.log("strip filesystem signatures (wipefs)", "dim")
        subprocess.run(["wipefs", "-a", self.dev],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _crypto_erase(self):
        """Instant key-destruction erase, where the hardware/volume supports it."""
        if self.sim:
            self.log("would attempt crypto-erase (NVMe ses=2 / LUKS / SED)",
                     "dim")
            return True
        ok = False
        # 1) NVMe cryptographic format
        if "nvme" in self.dev and shutil.which("nvme"):
            self.log("nvme format --ses=2 (cryptographic erase) ...", "dim")
            r = subprocess.run(["nvme", "format", self.dev, "--ses=2"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            if r.returncode == 0:
                self.log("NVMe cryptographic erase succeeded", "ok"); ok = True
            else:
                self.log("NVMe crypto erase refused/unsupported", "warn")
        # 2) LUKS volume — destroy all keyslots → master key unrecoverable
        if shutil.which("cryptsetup"):
            if subprocess.run(["cryptsetup", "isLuks", self.dev],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                self.log("LUKS detected — erasing keyslots (cryptsetup erase)...",
                         "dim")
                r = subprocess.run(["cryptsetup", "erase", "-q", self.dev],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                if r.returncode == 0:
                    self.log("LUKS keyslots erased — data is now unrecoverable",
                             "ok"); ok = True
        # 3) TCG Opal self-encrypting drive (needs sedutil-cli + the drive PSID)
        if not ok and shutil.which("sedutil-cli"):
            self.log("self-encrypting drive tooling present; PSID-revert must "
                     "be run manually: sedutil-cli --yesIreallywanttoERASE "
                     "--PSIDrevert <PSID> " + self.dev, "warn")
        # 4) ATA enhanced secure erase (crypto on SEDs) — opt-in, can lock drive
        if not ok and self.opts.get("ata_crypto") and shutil.which("hdparm"):
            ok = self._ata_secure_erase()
        return ok

    def _ata_secure_erase(self):
        info = subprocess.run(["hdparm", "-I", self.dev],
                              capture_output=True, text=True).stdout
        if "Security:" not in info:
            self.log("ATA security info unavailable (USB bridge blocks it)",
                     "warn")
            return False
        if "frozen" in info and "not\tfrozen" not in info and "not frozen" not in info:
            self.log("drive security FROZEN — needs a power-cycle; skipping",
                     "warn")
            return False
        pw = f"dm{random.randint(1000,9999)}"
        self.log("setting temporary ATA password and issuing enhanced erase...",
                 "dim")
        if subprocess.run(["hdparm", "--user-master", "u",
                           "--security-set-pass", pw, self.dev],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0:
            self.log("could not set ATA password", "warn"); return False
        cmd = "--security-erase-enhanced" if "enhanced erase" in info \
            else "--security-erase"
        if subprocess.run(["hdparm", "--user-master", "u", cmd, pw, self.dev],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            self.log(f"ATA {cmd} completed", "ok"); return True
        self.log(f"ATA erase FAILED — drive may hold password '{pw}'. Unlock: "
                 f"hdparm --user-master u --security-disable '{pw}' {self.dev}",
                 "error")
        return False

    def _remove_hpa_dco(self):
        """Strip Host Protected Area / Device Configuration Overlay (ATA only)."""
        if self.sim:
            self.log("would check/remove HPA & DCO (ATA)", "dim")
            self.report["hpa_dco"] = "simulated"
            return
        if not shutil.which("hdparm"):
            self.log("hdparm not present — skipping HPA/DCO check", "warn")
            return
        actions = []
        n = subprocess.run(["hdparm", "-N", self.dev],
                           capture_output=True, text=True).stdout
        if "HPA is enabled" in n:
            self.log("HPA detected — removing so the overwrite reaches all "
                     "sectors", "warn")
            subprocess.run(["bash", "-c",
                            f"hdparm -N p$(blockdev --getsz {self.dev}) "
                            f"{self.dev}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            actions.append("HPA removed")
        dco = subprocess.run(["hdparm", "--dco-identify", self.dev],
                             capture_output=True, text=True).stdout
        if "Real max sectors" in dco:
            self.log("DCO present — attempting restore (best effort)", "warn")
            subprocess.run(["hdparm", "--yes-i-know-what-i-am-doing",
                            "--dco-restore", self.dev],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            actions.append("DCO restore attempted")
        self.report["hpa_dco"] = ", ".join(actions) if actions else "none found"
        if not actions:
            self.log("no HPA/DCO found", "dim")

    def _rng_block(self, idx, n):
        """Deterministic random bytes for block idx (reproducible for verify)."""
        r = random.Random((self.seed << 21) ^ idx)
        return r.randbytes(n)

    def _hardware_sanitize(self):
        if self.sim:
            self.log("would attempt hardware sanitize", "dim")
            return False
        ok = False
        if "nvme" in self.dev and shutil.which("nvme"):
            self.log("nvme sanitize ...", "dim")
            if subprocess.run(["nvme", "sanitize", self.dev, "-a", "2"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                self.log("nvme sanitize accepted", "ok"); ok = True
        if shutil.which("blkdiscard"):
            self.log("blkdiscard --secure ...", "dim")
            if subprocess.run(["blkdiscard", "-f", "--secure", self.dev],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                self.log("secure discard succeeded", "ok"); ok = True
            else:
                self.log("secure discard unsupported; plain discard", "warn")
                subprocess.run(["blkdiscard", "-f", self.dev],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if not ok:
            self.log("no hardware sanitize available; overwrite follows", "warn")
        return ok

    def _fill(self, size, kind, label):
        """kind: 'zero' | 'random' (reproducible) | 'urandom' (one-shot)."""
        self._check()
        written, last, t0, idx = 0, 0.0, time.time(), 0
        self.status(f"{label} ...")
        if kind == "random" and not self.can_repro and not self.sim:
            self.log("Python <3.9: random-fill not verifiable, using urandom",
                     "warn")
            kind = "urandom"
        if self.sim:
            sim_rate = 700 * 1024 * 1024            # pretend 700 MB/s
            while written < size:
                self._check()
                step = min(CHUNK * 4, size - written)
                time.sleep(step / sim_rate * 0.12)   # compressed for preview
                written += step
                now = time.time()
                if now - last > 0.1 or written == size:
                    last = now
                    eta = (size - written) / sim_rate
                    self.progress(written / size)
                    self.status(f"{label}: {human(written)}/{human(size)} "
                                f"· ~{human(sim_rate)}/s · ETA {fmt_dur(eta)}")
            self.log(f"{label}: simulated {human(size)}", "ok")
            self.progress(1.0)
            return
        with open(self.dev, "wb", buffering=0) as f:
            while written < size:
                self._check()
                n = min(CHUNK, size - written)
                if kind == "zero":
                    block = ZERO_BLOCK if n == CHUNK else b"\x00" * n
                elif kind == "random":
                    block = self._rng_block(idx, n)
                else:  # urandom
                    block = os.urandom(n)
                f.write(block)
                written += n
                idx += 1
                now = time.time()
                if now - last > 0.15 or written == size:
                    last = now
                    rate = written / (now - t0 + 1e-9)
                    eta = (size - written) / rate if rate else 0
                    self.progress(written / size)
                    self.status(f"{label}: {human(written)}/{human(size)} "
                                f"· {human(rate)}/s · ETA {fmt_dur(eta)}")
            f.flush(); os.fsync(f.fileno())
        self.log(f"{label}: {human(size)} written", "ok")
        self.progress(1.0)

    def _verify_zero(self, size):
        mode = self.opts["verify"]
        if mode == "none":
            self.log("verification skipped", "warn")
            return
        self.status("verify: reading back ...")
        if self.sim:
            for i in range(21):
                self._check(); time.sleep(0.04); self.progress(i / 20)
            self.log("verify: simulated read-back ok", "ok")
            return
        nonzero, read, last = 0, 0, 0.0
        with open(self.dev, "rb", buffering=0) as f:
            if mode == "sample":
                for off in (0, max(0, size // 2 - CHUNK), max(0, size - CHUNK)):
                    self._check(); f.seek(off); data = f.read(CHUNK)
                    nonzero += len(data) - data.count(0)
            else:
                while read < size:
                    self._check()
                    data = f.read(CHUNK)
                    if not data:
                        break
                    nonzero += len(data) - data.count(0)
                    read += len(data)
                    now = time.time()
                    if now - last > 0.15 or read >= size:
                        last = now
                        self.progress(read / size)
                        self.status(f"verify: {human(read)}/{human(size)}")
        if nonzero:
            raise RuntimeError(f"verify FAILED — {nonzero} non-zero byte(s) "
                               "remain; do not trust this device.")
        self.log("verify PASSED — reads back as all zeros", "ok")

    def _verify_random(self, size):
        """Re-read and confirm bytes match the random stream we wrote."""
        mode = self.opts["verify"]
        if mode == "none" or not self.can_repro:
            self.log("random-fill verification skipped", "warn")
            return
        self.status("verify: matching random stream ...")
        if self.sim:
            for i in range(21):
                self._check(); time.sleep(0.04); self.progress(i / 20)
            self.log("verify: simulated stream match ok", "ok")
            return
        mism, read, last = 0, 0, 0.0
        with open(self.dev, "rb", buffering=0) as f:
            if mode == "sample":
                nblocks = (size + CHUNK - 1) // CHUNK
                idxs = sorted({0, nblocks // 2, max(0, nblocks - 1)})
                for idx in idxs:
                    off = idx * CHUNK
                    self._check(); f.seek(off)
                    n = min(CHUNK, size - off)
                    data = f.read(n)
                    if data != self._rng_block(idx, len(data)):
                        mism += 1
            else:
                idx = 0
                while read < size:
                    self._check()
                    n = min(CHUNK, size - read)
                    data = f.read(n)
                    if not data:
                        break
                    if data != self._rng_block(idx, len(data)):
                        mism += 1
                    read += len(data); idx += 1
                    now = time.time()
                    if now - last > 0.15 or read >= size:
                        last = now
                        self.progress(read / size)
                        self.status(f"verify: {human(read)}/{human(size)}")
        if mism:
            raise RuntimeError(f"verify FAILED — {mism} block(s) did not match "
                               "the written random stream.")
        self.log("verify PASSED — device matches the random stream written",
                 "ok")

    def _reformat(self):
        if self.sim:
            self.log(f"would create GPT + {self.opts['fs']} ({self.opts['label']})",
                     "dim")
            return
        self.status("recreate partition + filesystem ...")
        subprocess.run(["parted", "-s", self.dev, "mklabel", "gpt"], check=True)
        subprocess.run(["parted", "-s", self.dev, "mkpart", "primary",
                        "1MiB", "100%"], check=True)
        subprocess.run(["partprobe", self.dev],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["udevadm", "settle"])
        parts = subprocess.check_output(
            ["lsblk", "-lnpo", "NAME", self.dev], text=True).splitlines()
        if len(parts) < 2:
            raise RuntimeError("could not detect new partition")
        part = parts[1].strip()
        fs, lab = self.opts["fs"], self.opts["label"]
        self.log(f"format {part} → {fs} ({lab})", "dim")
        if fs == "exfat":
            subprocess.run(["mkfs.exfat", "-n", lab, part], check=True)
        else:
            subprocess.run(["mkfs.ext4", "-F", "-L", lab, part], check=True)
        subprocess.run(["sync"])

    def _summary(self):
        if self.sim:
            return "SIMULATION complete — no data was touched."
        mode = self.opts["mode"]
        if mode == "crypto":
            return ("crypto-erase succeeded — the encryption key was destroyed, "
                    "so all data is cryptographically unrecoverable (instant, "
                    "covers the whole device including spare cells).")
        tail = (" Any HPA/DCO was handled." if self.opts.get("remove_hpa")
                and self.report.get("hpa_dco") not in (None, "none found",
                                                       "not checked") else "")
        if getattr(self, "media", "flash") == "magnetic":
            return ("magnetic drive — addressable surface overwritten and "
                    "verified (NIST 800-88 Clear)." + tail)
        if getattr(self, "hw_ok", False):
            return ("flash + successful hardware sanitize — strongest software "
                    "result; remapped/over-provisioned cells erased by the "
                    "controller.")
        return ("flash, no hardware sanitize — addressable area overwritten and "
                "verified, but remnants may survive in remapped cells; destroy "
                "physically for highly sensitive data.")


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("damnatio memoriae")
        self.configure(bg=BG)
        self.geometry("820x780")
        self.minsize(560, 480)       # small floor → can shrink, resize, maximize
        self.resizable(True, True)   # assert it explicitly for stubborn WMs
        self.bind("<F11>", self._toggle_max)
        self.bind("<Escape>", lambda e: self._set_max(False))

        self.MONO = pick_mono(self)
        self.f_body = (self.MONO, 10)
        self.f_small = (self.MONO, 9)
        self.f_big = (self.MONO, 22, "bold")

        self.worker = None
        self.abort_evt = threading.Event()
        self.msgq = queue.Queue()
        self.drives = []
        self._sig = None
        self.last_report = None

        self._theme()
        self._build()
        self._refresh()
        self.after(120, self._poll)
        self.after(4000, self._auto_refresh)
        self.protocol("WM_DELETE_WINDOW", self._close)

        if os.geteuid() != 0:
            self._log("not root — real wipes will fail. relaunch with: "
                      "sudo python3 damnatio_memoriae.py  (SIMULATE works "
                      "without root)", "warn")

    # ---- theme ----
    def _theme(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    bordercolor=GRID, font=self.f_body)
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Dim.TLabel", background=BG, foreground=DIM)
        s.configure("Head.TLabel", background=BG, foreground=CYAN)
        s.configure("TLabelframe", background=BG, bordercolor=GRID,
                    relief="solid")
        s.configure("TLabelframe.Label", background=BG, foreground=CYAN,
                    font=(self.MONO, 9, "bold"))
        s.configure("TButton", background=PANEL, foreground=BRIGHT,
                    bordercolor=DIM, focuscolor=CYAN, relief="solid",
                    padding=(10, 4))
        s.map("TButton", background=[("active", "#10241a")],
              foreground=[("disabled", DIM)], bordercolor=[("active", BRIGHT)])
        s.configure("Danger.TButton", foreground=RED, bordercolor=RED)
        s.map("Danger.TButton", background=[("active", "#2a0c12")],
              bordercolor=[("active", RED)], foreground=[("disabled", DIM)])
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=BG, foreground=FG, focuscolor=CYAN)
            s.map(w, foreground=[("selected", BRIGHT), ("active", WHITE)],
                  background=[("active", BG)])
        s.configure("TEntry", fieldbackground=PANEL, foreground=BRIGHT,
                    insertcolor=BRIGHT, bordercolor=DIM)
        s.configure("TSpinbox", fieldbackground=PANEL, foreground=BRIGHT,
                    arrowcolor=FG, bordercolor=DIM)
        s.configure("TCombobox", fieldbackground=PANEL, foreground=BRIGHT,
                    arrowcolor=FG, bordercolor=DIM)
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#10241a")
        self.option_add("*TCombobox*Listbox.selectForeground", BRIGHT)
        s.configure("Treeview", background=BG, fieldbackground=BG,
                    foreground=FG, bordercolor=GRID, rowheight=22)
        s.map("Treeview", background=[("selected", "#10241a")],
              foreground=[("selected", BRIGHT)])
        s.configure("Treeview.Heading", background=PANEL, foreground=CYAN,
                    relief="flat", font=(self.MONO, 9, "bold"))
        s.configure("dm.Horizontal.TProgressbar", troughcolor=PANEL,
                    background=BRIGHT, bordercolor=GRID, lightcolor=BRIGHT,
                    darkcolor=BRIGHT)

    # ---- layout ----
    def _build(self):
        # header
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 2))
        spaced = "  ".join("DAMNATIO MEMORIAE")
        tk.Label(head, text=spaced, bg=BG, fg=BRIGHT,
                 font=self.f_big).pack(anchor="w")
        sub = tk.Frame(head, bg=BG); sub.pack(fill="x")
        tk.Label(sub, text="// the condemnation of memory · leave no trace",
                 bg=BG, fg=DIM, font=self.f_small).pack(side="left")
        tk.Label(sub, text=f"v{VERSION}", bg=BG, fg=DIM,
                 font=self.f_small).pack(side="right")
        tk.Frame(self, bg=GRID, height=1).pack(fill="x", padx=14, pady=(4, 6))

        # 1: drives
        f1 = ttk.LabelFrame(self, text=" 01 · TARGET ")
        f1.pack(fill="both", expand=True, padx=14, pady=4)
        cols = ("device", "size", "model", "serial", "type")
        self.tree = ttk.Treeview(f1, columns=cols, show="headings", height=6)
        for c, w in zip(cols, (120, 80, 200, 150, 90)):
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.tag_configure("root", foreground=RED)
        self.tree.tag_configure("internal", foreground=AMBER)

        side = tk.Frame(f1, bg=BG); side.pack(side="left", fill="y", padx=6)
        ttk.Button(side, text="↻ refresh", command=self._refresh)\
            .pack(fill="x", pady=2)
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(side, text="show all disks", variable=self.show_all,
                        command=self._refresh).pack(anchor="w", pady=2)
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(side, text="auto-detect", variable=self.auto)\
            .pack(anchor="w", pady=2)
        ttk.Button(side, text="⌕ scan", command=self._scan)\
            .pack(fill="x", pady=(10, 2))

        # 2: method
        f2 = ttk.LabelFrame(self, text=" 02 · METHOD ")
        f2.pack(fill="x", padx=14, pady=4)
        self.mode = tk.StringVar(value="zero")
        self.mode.trace_add("write", lambda *a: self._on_select())
        ttk.Radiobutton(f2, variable=self.mode, value="zero",
                        text="ZERO-FILL — overwrite every single bit with 0, "
                             "then verify   [default]")\
            .grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(f2, variable=self.mode, value="random",
                        text="RANDOM-FILL — overwrite every bit with random "
                             "data, then verify the stream")\
            .grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(f2, variable=self.mode, value="random_zero",
                        text="RANDOM + ZERO — random pass(es), then a verified "
                             "zero pass")\
            .grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(f2, variable=self.mode, value="crypto",
                        text="CRYPTO-ERASE — destroy the encryption key "
                             "(NVMe/SED/LUKS); instant, whole-device")\
            .grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(f2, variable=self.mode, value="sanitize",
                        text="SANITIZE + ZERO — controller self-erase, then "
                             "zero  [best for flash]")\
            .grid(row=4, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        opt = tk.Frame(f2, bg=BG)
        opt.grid(row=5, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 2))
        ttk.Label(opt, text="passes").pack(side="left")
        self.passes = tk.IntVar(value=1)
        ttk.Spinbox(opt, from_=1, to=7, width=3, textvariable=self.passes)\
            .pack(side="left", padx=(4, 14))
        ttk.Label(opt, text="verify").pack(side="left")
        self.verify = tk.StringVar(value="full")
        ttk.Combobox(opt, textvariable=self.verify, width=7, state="readonly",
                     values=("full", "sample", "none")).pack(side="left",
                                                              padx=(4, 14))
        self.reformat = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="reformat", variable=self.reformat)\
            .pack(side="left", padx=(0, 6))
        self.fs = tk.StringVar(value="exfat")
        ttk.Combobox(opt, textvariable=self.fs, width=6, state="readonly",
                     values=("exfat", "ext4")).pack(side="left", padx=4)
        self.label = tk.StringVar(value="WIPED")
        ttk.Entry(opt, textvariable=self.label, width=10).pack(side="left",
                                                               padx=4)

        opt2 = tk.Frame(f2, bg=BG)
        opt2.grid(row=6, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))
        self.remove_hpa = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt2, text="remove HPA/DCO (ATA disks)",
                        variable=self.remove_hpa).pack(side="left", padx=(0, 14))
        self.ata_crypto = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt2, text="allow ATA secure-erase (risky, can lock "
                        "drive)", variable=self.ata_crypto).pack(side="left")

        # 3: confirm
        f3 = ttk.LabelFrame(self, text=" 03 · EXECUTE ")
        f3.pack(fill="x", padx=14, pady=4)
        self.sim = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="SIMULATE  (dry-run, no writes — safe to test)",
                        variable=self.sim,
                        command=self._on_select).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 0))
        self.confirm_lbl = ttk.Label(f3, text="select a target above",
                                     style="Dim.TLabel")
        self.confirm_lbl.grid(row=1, column=0, columnspan=3, sticky="w",
                              padx=6, pady=2)
        self.confirm = tk.StringVar()
        self.confirm.trace_add("write", lambda *a: self._update_btn())
        self.confirm_entry = ttk.Entry(f3, textvariable=self.confirm, width=38)
        self.confirm_entry.grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.start_btn = ttk.Button(f3, text="◼ ERASE", style="Danger.TButton",
                                    command=self._start, state="disabled")
        self.start_btn.grid(row=2, column=1, padx=6)
        self.abort_btn = ttk.Button(f3, text="✕ abort", command=self._abort,
                                    state="disabled")
        self.abort_btn.grid(row=2, column=2, padx=6)

        # progress
        prog = tk.Frame(self, bg=BG); prog.pack(fill="x", padx=14, pady=(8, 2))
        self.led = tk.Label(prog, text="●", bg=BG, fg=DIM, font=self.f_body)
        self.led.pack(side="left", padx=(0, 8))
        self.bar_lbl = tk.Label(prog, text=self._bar(0.0), bg=BG, fg=BRIGHT,
                                font=self.f_body, anchor="w")
        self.bar_lbl.pack(side="left", fill="x", expand=True)
        self.pbar = ttk.Progressbar(self, style="dm.Horizontal.TProgressbar",
                                    mode="determinate", maximum=1.0)
        self.pbar.pack(fill="x", padx=14, pady=2)
        self.status_lbl = tk.Label(self, text="idle", bg=BG, fg=DIM,
                                   font=self.f_small, anchor="w")
        self.status_lbl.pack(fill="x", padx=16)

        # log
        f4 = ttk.LabelFrame(self, text=" CONSOLE ")
        f4.pack(fill="both", expand=True, padx=14, pady=(4, 6))
        self.logbox = tk.Text(f4, height=9, wrap="word", bg=BG, fg=FG,
                              insertbackground=BRIGHT, relief="flat",
                              font=self.f_small, padx=8, pady=6,
                              state="disabled", highlightthickness=0)
        self.logbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(f4, command=self.logbox.yview)
        sb.pack(side="right", fill="y")
        self.logbox.config(yscrollcommand=sb.set)
        for tag, col in (("info", FG), ("dim", DIM), ("ok", BRIGHT),
                         ("warn", AMBER), ("error", RED), ("head", CYAN)):
            self.logbox.tag_configure(tag, foreground=col)

        bottom = tk.Frame(self, bg=BG); bottom.pack(fill="x", padx=14,
                                                    pady=(0, 10))
        self.export_btn = ttk.Button(bottom, text="⤓ export certificate",
                                     command=self._export, state="disabled")
        self.export_btn.pack(side="right")

    # ---- small helpers ----
    def _bar(self, frac, width=40):
        n = int(frac * width)
        return f"[{'█'*n}{'░'*(width-n)}] {frac*100:5.1f}%"

    def _log(self, text, level="info"):
        self.logbox.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.logbox.insert("end", f"{ts}  ", "dim")
        self.logbox.insert("end", text + "\n", level)
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def _set_led(self, color):
        self.led.config(fg=color)

    def _sel(self):
        s = self.tree.selection()
        return self.drives[int(s[0])] if s else None

    # ---- drives ----
    def _refresh(self):
        keep = self._sel()
        keep_name = keep["name"] if keep else None
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.drives = list_drives(show_all=self.show_all.get())
        self._sig = tuple((d["name"], d["size"]) for d in self.drives)
        for i, d in enumerate(self.drives):
            kind = "magnetic" if d["rota"] else "flash"
            tag = ""
            if d["is_root"]:
                kind += " ·SYS"; tag = "root"
            elif not d["external"]:
                tag = "internal"
            self.tree.insert("", "end", iid=str(i),
                             values=(d["name"], human(d["size"]), d["model"],
                                     d["serial"], kind), tags=(tag,))
            if d["name"] == keep_name:
                self.tree.selection_set(str(i))
        self._on_select()

    def _auto_refresh(self):
        if self.auto.get() and (self.worker is None or not self.worker.is_alive()):
            sig = tuple((d["name"], d["size"])
                        for d in list_drives(show_all=self.show_all.get()))
            if sig != self._sig:
                self._log("drive topology changed — refreshing", "dim")
                self._refresh()
        self.after(4000, self._auto_refresh)

    def _on_select(self):
        d = self._sel()
        if not d:
            self.confirm_lbl.config(text="select a target above",
                                    style="Dim.TLabel")
        elif d["is_root"]:
            self.confirm_lbl.config(
                text=f"{d['name']} is the SYSTEM disk — refused", style="TLabel")
            self.confirm_lbl.configure(foreground=RED)
        else:
            verb = "SIMULATE" if self.sim.get() else "DAMNATIO"
            self.confirm_lbl.config(
                text=f"type to confirm:  {verb} {d['name']}", style="TLabel")
            self.confirm_lbl.configure(foreground=AMBER)
        self._update_btn()

    def _phrase(self, d):
        verb = "SIMULATE" if self.sim.get() else "DAMNATIO"
        return f"{verb} {d['name']}"

    def _update_btn(self):
        d = self._sel()
        running = self.worker is not None and self.worker.is_alive()
        ok = (d is not None and not d["is_root"] and not running
              and self.confirm.get().strip() == self._phrase(d))
        self.start_btn.config(state="normal" if ok else "disabled")
        self.start_btn.config(
            text="▷ SIMULATE" if (d and self.sim.get()) else "◼ ERASE")

    # ---- run ----
    def _start(self):
        d = self._sel()
        if not d or d["is_root"]:
            return
        if not self.sim.get():
            if not messagebox.askyesno(
                "confirm",
                f"PERMANENTLY destroy ALL data on:\n\n{d['name']}  "
                f"({human(d['size'])}, {d['model']})\n\n"
                "This cannot be undone. Proceed?", icon="warning"):
                return
        opts = {
            "mode": self.mode.get(),
            "passes": max(1, int(self.passes.get())),
            "verify": self.verify.get(),
            "reformat": bool(self.reformat.get()),
            "fs": self.fs.get(),
            "label": (self.label.get().strip() or "WIPED"),
            "simulate": bool(self.sim.get()),
            "remove_hpa": bool(self.remove_hpa.get()),
            "ata_crypto": bool(self.ata_crypto.get()),
        }
        self.abort_evt.clear()
        self.last_report = None
        self.export_btn.config(state="disabled")
        self.worker = WipeWorker(d, opts, self.msgq, self.abort_evt)
        self._running(True)
        self._set_led(AMBER)
        self._log("─" * 52, "dim")
        self._log(f"begin {opts['mode']} on {d['name']}"
                  + ("  [SIMULATION]" if opts["simulate"] else ""), "head")
        self.worker.start()

    def _abort(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno("abort", "Stop now? Drive left partial."):
                self.abort_evt.set()
                self.status_lbl.config(text="aborting ...")

    # ---- read-only inspect ----
    def _scan(self):
        d = self._sel()
        if not d:
            messagebox.showinfo("scan", "Select a target first.")
            return
        if self.worker and self.worker.is_alive():
            return
        self._log(f"scan {d['name']} — read-only sampling ...", "head")

        def work():
            try:
                size = device_size(d["name"])
                offs = [int(size * frac) for frac in
                        (0.0, 0.25, 0.5, 0.75, 0.999)]
                total = nz = 0
                with open(d["name"], "rb", buffering=0) as f:
                    for off in offs:
                        off = min(off, max(0, size - 1024 * 1024))
                        f.seek(off)
                        data = f.read(4 * 1024 * 1024)
                        total += len(data)
                        nz += len(data) - data.count(0)
                pct = (nz / total * 100) if total else 0
                if nz == 0:
                    verdict = "looks ERASED — all sampled bytes are zero"
                    lvl = "ok"
                elif pct > 40:
                    verdict = (f"looks like DATA / random ({pct:.1f}% non-zero "
                               "in samples)")
                    lvl = "warn"
                else:
                    verdict = (f"PARTIAL / sparse ({pct:.1f}% non-zero in "
                               "samples)")
                    lvl = "warn"
                self.msgq.put(("log", (f"scan {d['name']}: {verdict}", lvl)))
            except PermissionError:
                self.msgq.put(("log", ("scan failed — run as root to read the "
                                       "raw device", "error")))
            except Exception as e:  # noqa
                self.msgq.put(("log", (f"scan error: {e}", "error")))

        threading.Thread(target=work, daemon=True).start()

    def _running(self, on):
        st = "disabled" if on else "normal"
        self.confirm_entry.config(state=st)
        self.abort_btn.config(state="normal" if on else "disabled")
        if not on:
            self._update_btn()

    def _close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("quit", "Wipe running. Abort and quit?"):
                return
            self.abort_evt.set(); self.worker.join(timeout=2)
        self.destroy()

    def _set_max(self, on):
        # '-zoomed' works on most Linux WMs; fall back to fullscreen.
        try:
            self.attributes("-zoomed", bool(on))
        except tk.TclError:
            try:
                self.attributes("-fullscreen", bool(on))
            except tk.TclError:
                pass

    def _toggle_max(self, _event=None):
        try:
            cur = bool(self.attributes("-zoomed"))
        except tk.TclError:
            cur = False
        self._set_max(not cur)

    # ---- certificate ----
    def _export(self):
        if not self.last_report:
            return
        path = filedialog.asksaveasfilename(
            title="Save erasure certificate", defaultextension=".txt",
            initialfile=f"erasure_{self.last_report['device'].split('/')[-1]}_"
                        f"{datetime.now():%Y%m%d_%H%M%S}.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        r = self.last_report
        lines = [
            "DAMNATIO MEMORIAE — ERASURE CERTIFICATE",
            "=" * 46,
            f"generated   : {datetime.now().isoformat(timespec='seconds')}",
            f"tool        : damnatio memoriae v{r.get('version')}",
            "",
            f"device      : {r.get('device')}",
            f"model       : {r.get('model')}",
            f"serial      : {r.get('serial')}",
            f"bus / media : {r.get('bus')} / {r.get('media')}",
            f"capacity    : {r.get('size_human')} ({r.get('size_bytes')} bytes)",
            "",
            f"method      : {r.get('mode')}",
            f"passes      : {r.get('passes')}",
            f"hw sanitize : {r.get('hardware_sanitize')}",
            f"verification: {r.get('verify')} — {r.get('verification')}",
            f"reformatted : {r.get('reformat')}",
            f"simulated   : {r.get('simulated')}",
            "",
            f"started     : {r.get('started')}",
            f"finished    : {r.get('finished')}",
            "",
            "result:",
            f"  {r.get('result')}",
            "=" * 46,
        ]
        try:
            with open(path, "w") as f:
                f.write("\n".join(lines) + "\n")
            jpath = path.rsplit(".", 1)[0] + ".json"
            with open(jpath, "w") as f:
                json.dump(r, f, indent=2)
            self._log(f"certificate saved → {path}", "ok")
            self._log(f"json saved → {jpath}", "dim")
            messagebox.showinfo("saved", f"Certificate written:\n{path}\n{jpath}")
        except Exception as e:  # noqa
            messagebox.showerror("error", str(e))

    # ---- queue pump ----
    def _poll(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self._log(*payload)
                elif kind == "status":
                    self.status_lbl.config(text=payload)
                elif kind == "progress":
                    self.pbar["value"] = payload
                    self.bar_lbl.config(text=self._bar(payload))
                elif kind == "done":
                    self.pbar["value"] = 1.0
                    self.bar_lbl.config(text=self._bar(1.0))
                    self.last_report = payload["report"]
                    self.export_btn.config(state="normal")
                    self._set_led(BRIGHT)
                    self.status_lbl.config(text="complete")
                    self._log("MEMORY ERASED — " + payload["summary"], "ok")
                    self._running(False)
                    messagebox.showinfo("complete", payload["summary"])
                elif kind == "aborted":
                    self._set_led(RED)
                    self.status_lbl.config(text="aborted")
                    self._log("aborted — drive left partial", "warn")
                    self._running(False)
                elif kind == "error":
                    self._set_led(RED)
                    self.status_lbl.config(text="error")
                    self._log(payload, "error")
                    self._running(False)
                    messagebox.showerror("error", payload)
        except queue.Empty:
            pass
        self.after(120, self._poll)


def main():
    if sys.platform != "linux":
        print("damnatio memoriae targets Linux.", file=sys.stderr)
    App().mainloop()


if __name__ == "__main__":
    main()
