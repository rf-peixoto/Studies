#!/usr/bin/env python3
"""
Hybrid hardware/human entropy collector and cryptographically secure generator.

Security model
--------------
* The operating-system CSPRNG is mandatory. The program aborts if it cannot
  obtain secure OS random bytes.
* Hardware, environmental and human-derived observations are auxiliary inputs.
  They are health-tested where meaningful, domain-separated, conditioned, and
  mixed into an HMAC-DRBG stream.
* Final output is the XOR of fresh OS-CSPRNG bytes and the HMAC-DRBG stream.
  Therefore, auxiliary inputs cannot reduce the security of a sound OS CSPRNG.
* This is not a validated SP 800-90B entropy source and does not claim that a
  generic microphone, camera, timer, disk or human event has a certified amount
  of min-entropy.

The program performs:
* SP 800-90B-style Repetition Count and Adaptive Proportion health checks on
  raw pre-conditioning samples.
* A broad built-in statistical battery on the generated output.
* Optional full NIST SP 800-22 testing through the third-party `nistrng`
  package when installed.
* Optional external `rngtest`, `dieharder`, `ent`, and PractRand execution when
  the corresponding commands are installed.

Statistical tests can expose defects but cannot prove that entropy exists.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import platform
import re
import secrets
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore[assignment]

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    from pynput import mouse as pynput_mouse
except ImportError:
    pynput_mouse = None  # type: ignore[assignment]

try:
    import serial
except ImportError:
    serial = None  # type: ignore[assignment]


PROGRAM_VERSION = "3.0"
DOMAIN = b"HYBRID-HARDWARE-HUMAN-ENTROPY-v3\x00"
ALPHA = 0.01
HEALTH_ALPHA = 2.0 ** -20
HEALTH_ASSUMED_H = 0.25  # cutoff parameter only; not an entropy claim
MIN_HEALTH_SAMPLES = 1024
MAX_SOURCE_SYMBOLS = 1_048_576
MAX_OUTPUT_BYTES = 1024 * 1024 * 1024
OUTPUT_CHUNK = 1024 * 1024


class Console:
    GREEN = "\033[92m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    def __init__(self, color: bool = True, quiet: bool = False) -> None:
        self.color = color
        self.quiet = quiet

    def _paint(self, color: str, text: str) -> str:
        return f"{color}{text}{self.RESET}" if self.color else text

    def info(self, text: str) -> None:
        if not self.quiet:
            print(self._paint(self.BLUE, text))

    def good(self, text: str) -> None:
        if not self.quiet:
            print(self._paint(self.GREEN, text))

    def warn(self, text: str) -> None:
        if not self.quiet:
            print(self._paint(self.YELLOW, text), file=sys.stderr)

    def error(self, text: str) -> None:
        print(self._paint(self.RED, text), file=sys.stderr)

    def section(self, text: str) -> None:
        if not self.quiet:
            print("\n" + self._paint(self.CYAN, f"== {text} =="))


@dataclass
class HealthTestResult:
    name: str
    status: str
    observed: Optional[float] = None
    threshold: Optional[float] = None
    details: str = ""


@dataclass
class SourceResult:
    name: str
    status: str
    sample_count: int = 0
    alphabet_size: int = 0
    digest_sha3_512: str = ""
    observed_mcv_min_entropy: Optional[float] = None
    health_tests: list[HealthTestResult] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    symbols: bytes = field(default=b"", repr=False)
    transcript_digest: bytes = field(default=b"", repr=False)

    def report_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("symbols", None)
        result.pop("transcript_digest", None)
        return result


@dataclass
class StatisticalTestResult:
    name: str
    status: str
    p_value: Optional[float] = None
    statistic: Optional[float] = None
    details: str = ""
    suite: str = "built-in"


@dataclass
class GenerationReport:
    program_version: str
    created_utc: str
    platform: str
    python_version: str
    output_path: str
    output_bytes: int
    output_sha256: str
    tested_bytes: int
    tested_full_output: bool
    sources: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    external_tools: dict[str, Any]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Framing and cryptographic construction
# ---------------------------------------------------------------------------


def frame(label: bytes, payload: bytes) -> bytes:
    if len(label) > 65535:
        raise ValueError("frame label too long")
    return struct.pack(">H", len(label)) + label + struct.pack(">Q", len(payload)) + payload


class HmacDrbgSha512:
    """One-shot HMAC-DRBG using SHA-512, following the SP 800-90A state update."""

    def __init__(self, seed_material: bytes) -> None:
        if not seed_material:
            raise ValueError("seed material must not be empty")
        self._k = b"\x00" * 64
        self._v = b"\x01" * 64
        self._update(seed_material)

    def _mac(self, data: bytes) -> bytes:
        return hmac.new(self._k, data, hashlib.sha512).digest()

    def _update(self, provided_data: bytes = b"") -> None:
        self._k = hmac.new(self._k, self._v + b"\x00" + provided_data, hashlib.sha512).digest()
        self._v = hmac.new(self._k, self._v, hashlib.sha512).digest()
        if provided_data:
            self._k = hmac.new(self._k, self._v + b"\x01" + provided_data, hashlib.sha512).digest()
            self._v = hmac.new(self._k, self._v, hashlib.sha512).digest()

    def generate(self, size: int, additional_input: bytes = b"") -> bytes:
        if size < 0:
            raise ValueError("size must be non-negative")
        if additional_input:
            self._update(additional_input)
        out = bytearray()
        while len(out) < size:
            self._v = self._mac(self._v)
            out.extend(self._v)
        self._update(additional_input)
        return bytes(out[:size])


def secure_os_seed() -> bytes:
    """Acquire and sanity-check independent OS-CSPRNG blocks."""
    first = secrets.token_bytes(64)
    second = secrets.token_bytes(64)
    if first == second:
        raise RuntimeError("catastrophic OS CSPRNG duplicate-block failure")
    if len(set(first + second)) < 2:
        raise RuntimeError("catastrophic OS CSPRNG constant-output failure")
    return first + second


def xor_bytes(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("XOR operands must have equal lengths")
    return bytes(a ^ b for a, b in zip(left, right))


# ---------------------------------------------------------------------------
# SP 800-90B-style raw-source health tests
# ---------------------------------------------------------------------------


def repetition_cutoff(min_entropy_per_sample: float, alpha: float) -> int:
    if min_entropy_per_sample <= 0.0:
        raise ValueError("min entropy must be positive")
    return 1 + math.ceil(-math.log2(alpha) / min_entropy_per_sample)


def binomial_tail(n: int, p: float, cutoff: int) -> float:
    if cutoff <= 0:
        return 1.0
    if cutoff > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    logs: list[float] = []
    lp = math.log(p)
    lq = math.log1p(-p)
    for k in range(cutoff, n + 1):
        logs.append(
            math.lgamma(n + 1)
            - math.lgamma(k + 1)
            - math.lgamma(n - k + 1)
            + k * lp
            + (n - k) * lq
        )
    maximum = max(logs)
    return math.exp(maximum) * math.fsum(math.exp(value - maximum) for value in logs)


def adaptive_cutoff(window: int, min_entropy_per_sample: float, alpha: float) -> int:
    p_max = 2.0 ** (-min_entropy_per_sample)
    for cutoff in range(1, window + 1):
        if binomial_tail(window, p_max, cutoff) <= alpha:
            return cutoff
    return window + 1


def raw_source_health_tests(symbols: bytes) -> tuple[list[HealthTestResult], Optional[float], int]:
    if not symbols:
        return [HealthTestResult("Source non-empty", "FAIL", details="No samples were collected")], None, 0

    counts = Counter(symbols)
    alphabet_size = len(counts)
    p_mcv = max(counts.values()) / len(symbols)
    observed_h = -math.log2(p_mcv)

    tests: list[HealthTestResult] = []
    if len(symbols) < MIN_HEALTH_SAMPLES:
        tests.append(
            HealthTestResult(
                "Startup sample count",
                "INCONCLUSIVE",
                observed=float(len(symbols)),
                threshold=float(MIN_HEALTH_SAMPLES),
                details="Too few samples for the configured continuous health checks",
            )
        )
        return tests, observed_h, alphabet_size

    rct_limit = repetition_cutoff(HEALTH_ASSUMED_H, HEALTH_ALPHA)
    longest = 1
    current = 1
    previous = symbols[0]
    for value in symbols[1:]:
        if value == previous:
            current += 1
            longest = max(longest, current)
        else:
            previous = value
            current = 1
    tests.append(
        HealthTestResult(
            "Repetition Count Test",
            "PASS" if longest < rct_limit else "FAIL",
            observed=float(longest),
            threshold=float(rct_limit),
            details=f"Cutoff uses H={HEALTH_ASSUMED_H} bits/sample and alpha=2^-20; it is not a certified entropy estimate",
        )
    )

    window = 512
    apt_limit = adaptive_cutoff(window, HEALTH_ASSUMED_H, HEALTH_ALPHA)
    maximum_reference_count = 0
    windows = 0
    for start in range(0, len(symbols) - window + 1, window):
        block = symbols[start : start + window]
        reference = block[0]
        count = block.count(reference)
        maximum_reference_count = max(maximum_reference_count, count)
        windows += 1
    if windows == 0:
        tests.append(HealthTestResult("Adaptive Proportion Test", "INCONCLUSIVE", details="No complete window"))
    else:
        tests.append(
            HealthTestResult(
                "Adaptive Proportion Test",
                "PASS" if maximum_reference_count < apt_limit else "FAIL",
                observed=float(maximum_reference_count),
                threshold=float(apt_limit),
                details=f"{windows} non-overlapping windows of {window} symbols",
            )
        )

    tests.append(
        HealthTestResult(
            "Alphabet diversity",
            "PASS" if alphabet_size >= 2 else "FAIL",
            observed=float(alphabet_size),
            threshold=2.0,
        )
    )
    return tests, observed_h, alphabet_size


def build_source(
    name: str,
    symbols: bytes,
    transcript_digest: bytes,
    details: Optional[dict[str, Any]] = None,
    permit_inconclusive: bool = True,
) -> SourceResult:
    symbols = symbols[:MAX_SOURCE_SYMBOLS]
    health, observed_h, alphabet_size = raw_source_health_tests(symbols)
    hard_failure = any(item.status == "FAIL" for item in health)
    inconclusive = any(item.status == "INCONCLUSIVE" for item in health)
    if hard_failure:
        status = "REJECTED"
    elif inconclusive and permit_inconclusive:
        status = "MIXED_UNCREDITED"
    elif inconclusive:
        status = "REJECTED"
    else:
        status = "ACCEPTED"
    digest = hashlib.sha3_512(
        DOMAIN
        + frame(b"source-name", name.encode("utf-8"))
        + frame(b"transcript-digest", transcript_digest)
        + frame(b"symbols", symbols)
    ).digest()
    return SourceResult(
        name=name,
        status=status,
        sample_count=len(symbols),
        alphabet_size=alphabet_size,
        digest_sha3_512=digest.hex(),
        observed_mcv_min_entropy=observed_h,
        health_tests=health,
        details=details or {},
        symbols=symbols,
        transcript_digest=digest,
    )


def skipped_source(name: str, reason: str) -> SourceResult:
    return SourceResult(name=name, status="SKIPPED", error=reason)


def rejected_source(name: str, reason: str) -> SourceResult:
    return SourceResult(name=name, status="REJECTED", error=reason)


# ---------------------------------------------------------------------------
# Entropy collectors
# ---------------------------------------------------------------------------


def collect_cpu_scheduler_jitter(samples: int, workers: int) -> SourceResult:
    samples = max(samples, MIN_HEALTH_SAMPLES)
    workers = max(1, min(workers, 16))
    per_worker = math.ceil(samples / workers)
    all_symbols: list[bytes] = [b""] * workers
    digests: list[bytes] = [b""] * workers
    barrier = threading.Barrier(workers)

    def worker(index: int) -> None:
        symbols = bytearray()
        h = hashlib.sha3_512()
        state = (0x9E3779B97F4A7C15 ^ (index << 32)) & ((1 << 64) - 1)
        barrier.wait()
        previous = time.perf_counter_ns()
        for i in range(per_worker):
            start = time.perf_counter_ns()
            state ^= (state << 13) & ((1 << 64) - 1)
            state ^= state >> 7
            state ^= (state << 17) & ((1 << 64) - 1)
            hashlib.blake2s(struct.pack(">QQI", state, start, i), digest_size=16).digest()
            if (i & 31) == 0:
                time.sleep(0)
            now = time.perf_counter_ns()
            elapsed = now - start
            interarrival = now - previous
            previous = now
            thread_cpu = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            packed = struct.pack(">QQQQ", now, elapsed, interarrival, thread_cpu)
            h.update(packed)
            symbols.append((elapsed ^ interarrival ^ thread_cpu ^ state) & 0xFF)
        all_symbols[index] = bytes(symbols)
        digests[index] = h.digest()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    symbols = b"".join(all_symbols)[:samples]
    transcript = hashlib.sha3_512(b"".join(digests)).digest()
    return build_source(
        "CPU and scheduler timing jitter",
        symbols,
        transcript,
        {"workers": workers, "requested_samples": samples},
    )


def collect_disk_timing_jitter(iterations: int, directory: Optional[Path]) -> SourceResult:
    iterations = max(64, iterations)
    symbols = bytearray()
    transcript = hashlib.sha3_512()
    temp_path: Optional[Path] = None
    payload = bytes((i * 73 + 19) & 0xFF for i in range(4096))
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix="entropy-jitter-", delete=False) as handle:
            temp_path = Path(handle.name)
        for i in range(iterations):
            start_open = time.perf_counter_ns()
            with temp_path.open("r+b", buffering=0) as handle:
                opened = time.perf_counter_ns()
                handle.seek(0)
                start_write = time.perf_counter_ns()
                handle.write(payload)
                after_write = time.perf_counter_ns()
                os.fsync(handle.fileno())
                after_sync = time.perf_counter_ns()
                handle.seek((i * 31) % (len(payload) - 64))
                start_read = time.perf_counter_ns()
                chunk = handle.read(64)
                after_read = time.perf_counter_ns()
            timings = (
                opened - start_open,
                after_write - start_write,
                after_sync - after_write,
                after_read - start_read,
            )
            transcript.update(struct.pack(">IQQQQ", i, *timings))
            transcript.update(hashlib.blake2s(chunk, digest_size=8).digest())
            symbols.extend((value & 0xFF for value in timings))
        return build_source(
            "Disk and filesystem timing jitter",
            bytes(symbols),
            transcript.digest(),
            {"iterations": iterations, "directory": str(directory) if directory else "system temporary directory"},
        )
    except Exception as exc:
        return rejected_source("Disk and filesystem timing jitter", str(exc))
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def collect_microphone(duration: float, sample_rate: int, device: Optional[str]) -> SourceResult:
    if np is None:
        return skipped_source("Microphone sensor noise", "numpy is not installed")
    if sd is None:
        return skipped_source("Microphone sensor noise", "sounddevice is not installed")
    try:
        selected_device: Any = None
        if device is not None:
            try:
                selected_device = int(device)
            except ValueError:
                selected_device = device
        frames = int(duration * sample_rate)
        if frames < 2:
            raise ValueError("microphone duration is too short")
        recording = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=selected_device,
            blocking=True,
        )
        samples = np.asarray(recording, dtype=np.int32).reshape(-1)
        differences = np.diff(samples)
        if differences.size > MAX_SOURCE_SYMBOLS:
            step = math.ceil(differences.size / MAX_SOURCE_SYMBOLS)
            differences = differences[::step]
        symbols = (differences & 0xFF).astype(np.uint8).tobytes()
        digest = hashlib.sha3_512(recording.tobytes()).digest()
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
        return build_source(
            "Microphone temporal sensor noise",
            symbols,
            digest,
            {"duration_seconds": duration, "sample_rate": sample_rate, "RMS": rms, "device": device or "default"},
        )
    except Exception as exc:
        return rejected_source("Microphone temporal sensor noise", str(exc))


def collect_webcam(frames: int, device: int, warmup: int) -> SourceResult:
    if np is None:
        return skipped_source("Webcam temporal sensor noise", "numpy is not installed")
    if cv2 is None:
        return skipped_source("Webcam temporal sensor noise", "opencv-python is not installed")
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        return rejected_source("Webcam temporal sensor noise", f"unable to open camera index {device}")
    transcript = hashlib.sha3_512()
    symbols_parts: list[bytes] = []
    previous = None
    captured = 0
    try:
        for _ in range(max(0, warmup)):
            cap.read()
        for index in range(frames):
            ok, frame_data = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame_data, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (320, 240), interpolation=cv2.INTER_AREA)
            transcript.update(frame(gray.shape[0].to_bytes(2, "big"), gray.tobytes()))
            if previous is not None:
                diff = gray.astype(np.int16) - previous.astype(np.int16)
                flat = (diff.reshape(-1) & 0xFF).astype(np.uint8)
                symbols_parts.append(flat.tobytes())
            previous = gray
            captured += 1
        if captured < 2:
            return rejected_source("Webcam temporal sensor noise", "fewer than two frames were captured")
        symbols = b"".join(symbols_parts)
        if len(symbols) > MAX_SOURCE_SYMBOLS:
            stride = math.ceil(len(symbols) / MAX_SOURCE_SYMBOLS)
            symbols = symbols[::stride]
        return build_source(
            "Webcam temporal sensor noise",
            symbols,
            transcript.digest(),
            {"requested_frames": frames, "captured_frames": captured, "device": device, "resolution_used": "320x240 grayscale"},
        )
    except Exception as exc:
        return rejected_source("Webcam temporal sensor noise", str(exc))
    finally:
        cap.release()


def collect_linux_hwrng(byte_count: int, timeout: float) -> SourceResult:
    path = Path("/dev/hwrng")
    if platform.system() != "Linux":
        return skipped_source("Kernel hardware RNG device", "not running on Linux")
    if not path.exists():
        return skipped_source("Kernel hardware RNG device", "/dev/hwrng is absent")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            deadline = time.monotonic() + timeout
            data = bytearray()
            while len(data) < byte_count and time.monotonic() < deadline:
                readable, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
                if not readable:
                    break
                try:
                    chunk = os.read(fd, byte_count - len(data))
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                data.extend(chunk)
        finally:
            os.close(fd)
        if not data:
            return rejected_source("Kernel hardware RNG device", "no bytes were returned before timeout")
        return build_source(
            "Kernel hardware RNG device",
            bytes(data),
            hashlib.sha3_512(data).digest(),
            {"device": str(path), "bytes_read": len(data)},
        )
    except Exception as exc:
        return rejected_source("Kernel hardware RNG device", str(exc))


def collect_tpm(byte_count: int, timeout: float) -> SourceResult:
    command = shutil.which("tpm2_getrandom")
    if command is None:
        return skipped_source("TPM random generator", "tpm2_getrandom is not installed")
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(prefix="tpm-random-", delete=False) as handle:
            temp_path = Path(handle.name)
        proc = subprocess.run(
            [command, str(byte_count), "-o", str(temp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            reason = proc.stderr.decode(errors="replace").strip() or f"exit status {proc.returncode}"
            return rejected_source("TPM random generator", reason)
        data = temp_path.read_bytes()
        if not data:
            return rejected_source("TPM random generator", "TPM returned no data")
        return build_source(
            "TPM random generator",
            data,
            hashlib.sha3_512(data).digest(),
            {"bytes_read": len(data), "command": command},
        )
    except Exception as exc:
        return rejected_source("TPM random generator", str(exc))
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def collect_serial_trng(device: Optional[str], baud: int, byte_count: int, timeout: float) -> SourceResult:
    if device is None:
        return skipped_source("External serial entropy device", "no --serial-device was supplied")
    if serial is None:
        return skipped_source("External serial entropy device", "pyserial is not installed")
    try:
        with serial.Serial(device, baudrate=baud, timeout=timeout) as port:
            data = port.read(byte_count)
        if not data:
            return rejected_source("External serial entropy device", "serial device returned no data")
        return build_source(
            "External serial entropy device",
            data,
            hashlib.sha3_512(data).digest(),
            {"device": device, "baud": baud, "bytes_read": len(data)},
        )
    except Exception as exc:
        return rejected_source("External serial entropy device", str(exc))


class MouseCollector:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: list[bytes] = []
        self.symbols = bytearray()
        self.last_time = time.perf_counter_ns()
        self.last_x = 0
        self.last_y = 0

    def _record(self, event_type: int, x: int, y: int, extra: int = 0) -> None:
        now = time.perf_counter_ns()
        with self.lock:
            delta = now - self.last_time
            dx = x - self.last_x
            dy = y - self.last_y
            self.last_time = now
            self.last_x = x
            self.last_y = y
            record = struct.pack(">Bqqqqq", event_type, now, delta, x, y, extra ^ dx ^ (dy << 1))
            self.events.append(record)
            self.symbols.append((delta ^ x ^ (y << 1) ^ dx ^ (dy << 2) ^ extra) & 0xFF)

    def on_move(self, x: int, y: int) -> None:
        self._record(1, int(x), int(y))

    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        button_hash = int.from_bytes(hashlib.blake2s(str(button).encode(), digest_size=4).digest(), "big")
        self._record(2 if pressed else 3, int(x), int(y), button_hash)

    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._record(4, int(x), int(y), (int(dx) << 16) ^ int(dy))


def collect_keyboard_events(duration: float) -> tuple[list[bytes], bytes]:
    records: list[bytes] = []
    symbols = bytearray()
    previous = time.perf_counter_ns()

    def record_key(key_bytes: bytes) -> bool:
        nonlocal previous
        now = time.perf_counter_ns()
        delta = now - previous
        previous = now
        key_digest = hashlib.blake2s(key_bytes, digest_size=8).digest()
        records.append(struct.pack(">QQ", now, delta) + key_digest)
        symbols.append((delta ^ int.from_bytes(key_digest[:4], "big")) & 0xFF)
        return key_bytes in (b"\x1b",)

    deadline = time.monotonic() + duration
    if os.name == "nt":
        import msvcrt

        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in (b"\x00", b"\xe0") and msvcrt.kbhit():
                    key += msvcrt.getch()
                if record_key(key):
                    break
            else:
                time.sleep(0.001)
        return records, bytes(symbols)

    if not sys.stdin.isatty():
        return records, bytes(symbols)

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.01)
            if readable:
                key = os.read(fd, 8)
                if record_key(key):
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return records, bytes(symbols)


def collect_human_input(duration: float, console: Console) -> SourceResult:
    mouse_collector: Optional[MouseCollector] = None
    listener: Any = None
    if pynput_mouse is not None:
        try:
            mouse_collector = MouseCollector()
            listener = pynput_mouse.Listener(
                on_move=mouse_collector.on_move,
                on_click=mouse_collector.on_click,
                on_scroll=mouse_collector.on_scroll,
            )
            listener.start()
        except Exception:
            mouse_collector = None
            listener = None

    keyboard_available = os.name == "nt" or sys.stdin.isatty()
    if not keyboard_available and mouse_collector is None:
        return skipped_source("Human keyboard and mouse timing", "no interactive terminal and no usable pynput mouse listener")

    console.warn(f"For {duration:.1f} seconds, type irregularly and move/click the mouse. Press ESC to stop early.")
    keyboard_records: list[bytes] = []
    keyboard_symbols = b""
    try:
        if keyboard_available:
            keyboard_records, keyboard_symbols = collect_keyboard_events(duration)
        else:
            time.sleep(duration)
    finally:
        if listener is not None:
            try:
                listener.stop()
                listener.join(timeout=1.0)
            except Exception:
                pass

    mouse_records: list[bytes] = []
    mouse_symbols = b""
    if mouse_collector is not None:
        with mouse_collector.lock:
            mouse_records = list(mouse_collector.events)
            mouse_symbols = bytes(mouse_collector.symbols)

    symbols = keyboard_symbols + mouse_symbols
    if not symbols:
        return rejected_source("Human keyboard and mouse timing", "no human input events were captured")
    transcript = hashlib.sha3_512()
    for record in keyboard_records:
        transcript.update(frame(b"keyboard", record))
    for record in mouse_records:
        transcript.update(frame(b"mouse", record))
    return build_source(
        "Human keyboard and mouse timing",
        symbols,
        transcript.digest(),
        {
            "duration_seconds": duration,
            "keyboard_events": len(keyboard_symbols),
            "mouse_events": len(mouse_symbols),
            "characters_not_stored": True,
        },
        permit_inconclusive=True,
    )


def collect_environmental_metadata() -> SourceResult:
    """Collect personalization data. No entropy credit or health-test claim."""
    payload: dict[str, Any] = {
        "time_ns": time.time_ns(),
        "perf_counter_ns": time.perf_counter_ns(),
        "process_time_ns": time.process_time_ns(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname_hash": hashlib.sha256(platform.node().encode()).hexdigest(),
    }
    if psutil is not None:
        try:
            payload["boot_time"] = psutil.boot_time()
            payload["cpu_times"] = tuple(psutil.cpu_times())
            payload["cpu_stats"] = tuple(psutil.cpu_stats())
            payload["virtual_memory"] = tuple(psutil.virtual_memory())
            payload["swap_memory"] = tuple(psutil.swap_memory())
            payload["disk_io"] = tuple(psutil.disk_io_counters()) if psutil.disk_io_counters() else None
            payload["net_io"] = tuple(psutil.net_io_counters())
            if hasattr(psutil, "sensors_temperatures"):
                temperatures = psutil.sensors_temperatures()
                payload["temperatures"] = {
                    key: [(entry.label, entry.current) for entry in value]
                    for key, value in temperatures.items()
                }
            if hasattr(psutil, "sensors_fans"):
                fans = psutil.sensors_fans()
                payload["fans"] = {
                    key: [(entry.label, entry.current) for entry in value]
                    for key, value in fans.items()
                }
        except Exception as exc:
            payload["psutil_error"] = str(exc)
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    digest = hashlib.sha3_512(encoded).digest()
    return SourceResult(
        name="Environmental personalization metadata",
        status="MIXED_UNCREDITED",
        sample_count=len(encoded),
        alphabet_size=len(set(encoded)),
        digest_sha3_512=digest.hex(),
        details={"entropy_credit": "zero", "fields": sorted(payload.keys())},
        transcript_digest=digest,
    )


# ---------------------------------------------------------------------------
# Statistical helpers and built-in test battery
# ---------------------------------------------------------------------------


def clamp_probability(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return min(1.0, max(0.0, value))


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def gammaincc(a: float, x: float, eps: float = 1e-14, max_iter: int = 10000) -> float:
    if a <= 0.0 or x < 0.0:
        raise ValueError("invalid incomplete-gamma arguments")
    if x == 0.0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1.0:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(max_iter):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) <= abs(total) * eps:
                break
        p = total * math.exp(-x + a * math.log(x) - gln)
        return clamp_probability(1.0 - p)

    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / max(abs(b), tiny)
    if b < 0:
        d = -d
    h_value = d
    for i in range(1, max_iter + 1):
        an = -float(i) * (float(i) - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h_value *= delta
        if abs(delta - 1.0) <= eps:
            break
    q = math.exp(-x + a * math.log(x) - gln) * h_value
    return clamp_probability(q)


def chi_square_sf(statistic: float, degrees_of_freedom: int) -> float:
    return gammaincc(degrees_of_freedom / 2.0, statistic / 2.0)


def bits_from_bytes(data: bytes) -> bytes:
    if np is not None:
        return np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(np.uint8).tobytes()
    output = bytearray(len(data) * 8)
    index = 0
    for byte in data:
        for shift in range(7, -1, -1):
            output[index] = (byte >> shift) & 1
            index += 1
    return bytes(output)


def result_from_p(name: str, p: float, statistic: Optional[float] = None, details: str = "", suite: str = "built-in") -> StatisticalTestResult:
    p = clamp_probability(p)
    return StatisticalTestResult(name, "PASS" if p >= ALPHA else "FAIL", p, statistic, details, suite)


def skip_test(name: str, reason: str, suite: str = "built-in") -> StatisticalTestResult:
    return StatisticalTestResult(name, "SKIP", details=reason, suite=suite)


def test_monobit(bits: Sequence[int]) -> StatisticalTestResult:
    n = len(bits)
    if n < 100:
        return skip_test("Frequency (Monobit)", "requires at least 100 bits")
    total = sum(1 if bit else -1 for bit in bits)
    statistic = abs(total) / math.sqrt(n)
    return result_from_p("Frequency (Monobit)", math.erfc(statistic / math.sqrt(2.0)), statistic)


def test_block_frequency(bits: Sequence[int], block_size: int = 128) -> StatisticalTestResult:
    n = len(bits)
    blocks = n // block_size
    if blocks < 10:
        return skip_test("Block Frequency", f"requires at least {10 * block_size} bits")
    chi2 = 0.0
    for index in range(blocks):
        block = bits[index * block_size : (index + 1) * block_size]
        proportion = sum(block) / block_size
        chi2 += 4.0 * block_size * (proportion - 0.5) ** 2
    return result_from_p("Block Frequency", gammaincc(blocks / 2.0, chi2 / 2.0), chi2, f"M={block_size}, N={blocks}")


def test_runs(bits: Sequence[int]) -> StatisticalTestResult:
    n = len(bits)
    if n < 100:
        return skip_test("Runs", "requires at least 100 bits")
    pi = sum(bits) / n
    if abs(pi - 0.5) >= 2.0 / math.sqrt(n):
        return StatisticalTestResult("Runs", "FAIL", 0.0, details="monobit prerequisite failed")
    runs = 1 + sum(1 for i in range(1, n) if bits[i] != bits[i - 1])
    numerator = abs(runs - 2.0 * n * pi * (1.0 - pi))
    denominator = 2.0 * math.sqrt(2.0 * n) * pi * (1.0 - pi)
    return result_from_p("Runs", math.erfc(numerator / denominator), float(runs))


def longest_run(block: Sequence[int]) -> int:
    best = current = 0
    for bit in block:
        if bit:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def test_longest_run(bits: Sequence[int]) -> StatisticalTestResult:
    n = len(bits)
    if n < 128:
        return skip_test("Longest Run of Ones", "requires at least 128 bits")
    if n < 6272:
        m = 8
        probabilities = [0.2148, 0.3672, 0.2305, 0.1875]
        classify = lambda value: 0 if value <= 1 else 1 if value == 2 else 2 if value == 3 else 3
    elif n < 750000:
        m = 128
        probabilities = [0.1174, 0.2430, 0.2493, 0.1752, 0.1027, 0.1124]
        classify = lambda value: 0 if value <= 4 else value - 4 if value <= 8 else 5
    else:
        m = 10000
        probabilities = [0.0882, 0.2092, 0.2483, 0.1933, 0.1208, 0.0675, 0.0727]
        classify = lambda value: 0 if value <= 10 else value - 10 if value <= 15 else 6
    blocks = n // m
    frequencies = [0] * len(probabilities)
    for i in range(blocks):
        frequencies[classify(longest_run(bits[i * m : (i + 1) * m]))] += 1
    chi2 = sum((observed - blocks * expected) ** 2 / (blocks * expected) for observed, expected in zip(frequencies, probabilities))
    return result_from_p("Longest Run of Ones", chi_square_sf(chi2, len(probabilities) - 1), chi2, f"M={m}, N={blocks}, bins={frequencies}")


def cumulative_sums_p(bits: Sequence[int]) -> tuple[float, int]:
    n = len(bits)
    cumulative = 0
    z = 0
    for bit in bits:
        cumulative += 1 if bit else -1
        z = max(z, abs(cumulative))
    if z == 0:
        return 1.0, z
    root_n = math.sqrt(n)
    first_sum = 0.0
    start = math.floor((-n / z + 1.0) / 4.0)
    end = math.floor((n / z - 1.0) / 4.0)
    for k in range(start, end + 1):
        first_sum += normal_cdf((4 * k + 1) * z / root_n) - normal_cdf((4 * k - 1) * z / root_n)
    second_sum = 0.0
    start = math.floor((-n / z - 3.0) / 4.0)
    end = math.floor((n / z - 1.0) / 4.0)
    for k in range(start, end + 1):
        second_sum += normal_cdf((4 * k + 3) * z / root_n) - normal_cdf((4 * k + 1) * z / root_n)
    return clamp_probability(1.0 - first_sum + second_sum), z


def test_cumulative_sums(bits: Sequence[int]) -> list[StatisticalTestResult]:
    if len(bits) < 100:
        return [
            skip_test("Cumulative Sums (Forward)", "requires at least 100 bits"),
            skip_test("Cumulative Sums (Reverse)", "requires at least 100 bits"),
        ]
    forward_p, forward_z = cumulative_sums_p(bits)
    reverse_p, reverse_z = cumulative_sums_p(bytes(reversed(bits)))
    return [
        result_from_p("Cumulative Sums (Forward)", forward_p, float(forward_z)),
        result_from_p("Cumulative Sums (Reverse)", reverse_p, float(reverse_z)),
    ]


def psi_squared(bits: Sequence[int], m: int) -> float:
    n = len(bits)
    counts = [0] * (1 << m)
    extended = bytes(bits) + bytes(bits[: m - 1])
    value = 0
    mask = (1 << m) - 1
    for bit in extended[:m]:
        value = ((value << 1) | bit) & mask
    counts[value] += 1
    for i in range(1, n):
        value = ((value << 1) | extended[i + m - 1]) & mask
        counts[value] += 1
    return (sum(count * count for count in counts) * (1 << m) / n) - n


def test_serial(bits: Sequence[int], m: int = 3) -> list[StatisticalTestResult]:
    n = len(bits)
    if n < 1000:
        return [skip_test("Serial Δ1", "requires at least 1000 bits"), skip_test("Serial Δ2", "requires at least 1000 bits")]
    psi_m = psi_squared(bits, m)
    psi_m1 = psi_squared(bits, m - 1)
    psi_m2 = psi_squared(bits, m - 2)
    delta1 = psi_m - psi_m1
    delta2 = psi_m - 2.0 * psi_m1 + psi_m2
    return [
        result_from_p("Serial Δ1", gammaincc(2 ** (m - 2), delta1 / 2.0), delta1, f"m={m}"),
        result_from_p("Serial Δ2", gammaincc(2 ** (m - 3), delta2 / 2.0), delta2, f"m={m}"),
    ]


def circular_pattern_counts(bits: Sequence[int], m: int) -> list[int]:
    n = len(bits)
    counts = [0] * (1 << m)
    extended = bytes(bits) + bytes(bits[: m - 1])
    value = 0
    for bit in extended[:m]:
        value = (value << 1) | bit
    counts[value] += 1
    mask = (1 << m) - 1
    for i in range(1, n):
        value = ((value << 1) | extended[i + m - 1]) & mask
        counts[value] += 1
    return counts


def test_approximate_entropy(bits: Sequence[int], m: int = 3) -> StatisticalTestResult:
    n = len(bits)
    if n < 1000:
        return skip_test("Approximate Entropy", "requires at least 1000 bits")
    counts_m = circular_pattern_counts(bits, m)
    counts_m1 = circular_pattern_counts(bits, m + 1)

    def phi(counts: Sequence[int]) -> float:
        total = 0.0
        for count in counts:
            if count:
                probability = count / n
                total += probability * math.log(probability)
        return total

    apen = phi(counts_m) - phi(counts_m1)
    chi2 = 2.0 * n * (math.log(2.0) - apen)
    return result_from_p("Approximate Entropy", gammaincc(2 ** (m - 1), chi2 / 2.0), chi2, f"m={m}, ApEn={apen:.8f}")


def test_poker(bits: Sequence[int], m: int = 4) -> StatisticalTestResult:
    blocks = len(bits) // m
    if blocks < 100:
        return skip_test("Poker", f"requires at least {100 * m} bits")
    counts = [0] * (1 << m)
    for i in range(blocks):
        value = 0
        for bit in bits[i * m : (i + 1) * m]:
            value = (value << 1) | bit
        counts[value] += 1
    statistic = (2 ** m / blocks) * sum(value * value for value in counts) - blocks
    return result_from_p("Poker", chi_square_sf(statistic, (1 << m) - 1), statistic, f"m={m}")


def test_byte_frequency(data: bytes) -> StatisticalTestResult:
    if len(data) < 256:
        return skip_test("Byte Frequency Chi-Square", "requires at least 256 bytes")
    counts = Counter(data)
    expected = len(data) / 256.0
    statistic = sum((counts.get(value, 0) - expected) ** 2 / expected for value in range(256))
    return result_from_p("Byte Frequency Chi-Square", chi_square_sf(statistic, 255), statistic)


def test_autocorrelation(bits: Sequence[int], lag: int) -> StatisticalTestResult:
    n = len(bits) - lag
    if n < 1000:
        return skip_test(f"Autocorrelation lag {lag}", "requires at least 1000 comparable bits")
    mismatches = sum(bits[i] ^ bits[i + lag] for i in range(n))
    z = abs(mismatches - n / 2.0) / math.sqrt(n / 4.0)
    return result_from_p(f"Autocorrelation lag {lag}", math.erfc(z / math.sqrt(2.0)), z, f"mismatches={mismatches}/{n}")


def gf2_rank_32(rows: Sequence[int]) -> int:
    work = list(rows)
    rank = 0
    for column in range(31, -1, -1):
        pivot = next((index for index in range(rank, 32) if (work[index] >> column) & 1), None)
        if pivot is None:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        for index in range(32):
            if index != rank and ((work[index] >> column) & 1):
                work[index] ^= work[rank]
        rank += 1
        if rank == 32:
            break
    return rank


def test_binary_matrix_rank(bits: Sequence[int]) -> StatisticalTestResult:
    matrix_bits = 32 * 32
    matrices = len(bits) // matrix_bits
    if matrices < 38:
        return skip_test("Binary Matrix Rank", f"requires at least {38 * matrix_bits} bits")
    counts = [0, 0, 0]
    for matrix_index in range(matrices):
        offset = matrix_index * matrix_bits
        rows = []
        for row in range(32):
            value = 0
            for bit in bits[offset + row * 32 : offset + (row + 1) * 32]:
                value = (value << 1) | bit
            rows.append(value)
        rank = gf2_rank_32(rows)
        if rank == 32:
            counts[0] += 1
        elif rank == 31:
            counts[1] += 1
        else:
            counts[2] += 1
    probabilities = [0.2888, 0.5776, 0.1336]
    statistic = sum((observed - matrices * p) ** 2 / (matrices * p) for observed, p in zip(counts, probabilities))
    return result_from_p("Binary Matrix Rank", math.exp(-statistic / 2.0), statistic, f"N={matrices}, ranks={counts}")


def test_spectral(bits: Sequence[int]) -> StatisticalTestResult:
    n = len(bits)
    if n < 1000:
        return skip_test("Discrete Fourier Transform", "requires at least 1000 bits")
    if np is None:
        return skip_test("Discrete Fourier Transform", "numpy is not installed")
    raw = np.frombuffer(bytes(bits), dtype=np.uint8).astype(np.float64)
    values = raw * 2.0 - 1.0
    magnitudes = np.abs(np.fft.fft(values))[: n // 2]
    threshold = math.sqrt(math.log(1.0 / 0.05) * n)
    observed = int(np.sum(magnitudes < threshold))
    expected = 0.95 * n / 2.0
    denominator = math.sqrt(n * 0.95 * 0.05 / 4.0)
    d_value = (observed - expected) / denominator
    return result_from_p("Discrete Fourier Transform", math.erfc(abs(d_value) / math.sqrt(2.0)), d_value, f"peaks_below_threshold={observed}")


def test_overlapping_template(bits: Sequence[int]) -> StatisticalTestResult:
    m = 9
    block_size = 1032
    blocks = len(bits) // block_size
    if blocks < 50:
        return skip_test("Overlapping Template (9 ones)", f"requires at least {50 * block_size} bits")
    pattern = [1] * m
    frequencies = [0] * 6
    for block_index in range(blocks):
        block = bits[block_index * block_size : (block_index + 1) * block_size]
        count = 0
        run = 0
        for bit in block:
            if bit:
                run += 1
                if run >= m:
                    count += 1
            else:
                run = 0
        frequencies[min(count, 5)] += 1
    probabilities = [0.364091, 0.185659, 0.139381, 0.100571, 0.070432, 0.139865]
    statistic = sum((observed - blocks * p) ** 2 / (blocks * p) for observed, p in zip(frequencies, probabilities))
    return result_from_p("Overlapping Template (9 ones)", chi_square_sf(statistic, 5), statistic, f"N={blocks}, bins={frequencies}")


def berlekamp_massey(block: Sequence[int]) -> int:
    n = len(block)
    c = [0] * n
    b = [0] * n
    c[0] = b[0] = 1
    complexity = 0
    m = -1
    for index in range(n):
        discrepancy = block[index]
        for j in range(1, complexity + 1):
            discrepancy ^= c[j] & block[index - j]
        if discrepancy:
            temp = c.copy()
            shift = index - m
            for j in range(0, n - shift):
                c[j + shift] ^= b[j]
            if complexity <= index // 2:
                complexity = index + 1 - complexity
                m = index
                b = temp
    return complexity


def test_linear_complexity(bits: Sequence[int], block_size: int = 500) -> StatisticalTestResult:
    available_blocks = len(bits) // block_size
    if available_blocks < 200:
        return skip_test("Linear Complexity (sampled blocks)", f"requires at least {200 * block_size} bits")
    blocks = min(200, available_blocks)
    if available_blocks == blocks:
        selected = list(range(blocks))
    else:
        selected = [round(i * (available_blocks - 1) / (blocks - 1)) for i in range(blocks)]
    frequencies = [0] * 7
    mean = block_size / 2.0 + (9.0 + (-1.0) ** (block_size + 1)) / 36.0 - (block_size / 3.0 + 2.0 / 9.0) / (2.0 ** block_size)
    for index in selected:
        complexity = berlekamp_massey(bits[index * block_size : (index + 1) * block_size])
        transformed = ((-1.0) ** block_size) * (complexity - mean) + 2.0 / 9.0
        if transformed <= -2.5:
            bucket = 0
        elif transformed <= -1.5:
            bucket = 1
        elif transformed <= -0.5:
            bucket = 2
        elif transformed <= 0.5:
            bucket = 3
        elif transformed <= 1.5:
            bucket = 4
        elif transformed <= 2.5:
            bucket = 5
        else:
            bucket = 6
        frequencies[bucket] += 1
    probabilities = [0.01047, 0.03125, 0.125, 0.5, 0.25, 0.0625, 0.020833]
    statistic = sum((observed - blocks * p) ** 2 / (blocks * p) for observed, p in zip(frequencies, probabilities))
    return result_from_p("Linear Complexity (sampled blocks)", chi_square_sf(statistic, 6), statistic, f"M={block_size}, sampled_N={blocks}, available_N={available_blocks}, bins={frequencies}")


def maurer_parameters(n: int) -> Optional[int]:
    thresholds = [
        (1_059_061_760, 16),
        (496_435_200, 15),
        (231_669_760, 14),
        (107_560_960, 13),
        (49_643_520, 12),
        (22_753_280, 11),
        (10_342_400, 10),
        (4_654_080, 9),
        (2_068_480, 8),
        (904_960, 7),
        (387_840, 6),
    ]
    for minimum, length in thresholds:
        if n >= minimum:
            return length
    return None


def test_maurer_universal(bits: Sequence[int]) -> StatisticalTestResult:
    n = len(bits)
    length = maurer_parameters(n)
    if length is None:
        return skip_test("Maurer Universal", "requires at least 387840 bits")
    expected_values = {6: 5.2177052, 7: 6.1962507, 8: 7.1836656, 9: 8.1764248, 10: 9.1723243, 11: 10.170032, 12: 11.168765, 13: 12.168070, 14: 13.167693, 15: 14.167488, 16: 15.167379}
    variances = {6: 2.954, 7: 3.125, 8: 3.238, 9: 3.311, 10: 3.356, 11: 3.384, 12: 3.401, 13: 3.410, 14: 3.416, 15: 3.419, 16: 3.421}
    q = 10 * (1 << length)
    total_blocks = n // length
    k = total_blocks - q
    if k <= 0:
        return skip_test("Maurer Universal", "insufficient post-initialization blocks")
    table = [0] * (1 << length)

    def block_value(index: int) -> int:
        value = 0
        start = index * length
        for bit in bits[start : start + length]:
            value = (value << 1) | bit
        return value

    for i in range(q):
        table[block_value(i)] = i + 1
    total = 0.0
    for i in range(q, q + k):
        value = block_value(i)
        distance = i + 1 - table[value]
        table[value] = i + 1
        total += math.log2(distance)
    fn = total / k
    correction = 0.7 - 0.8 / length + (4.0 + 32.0 / length) * (k ** (-3.0 / length)) / 15.0
    sigma = correction * math.sqrt(variances[length] / k)
    p_value = math.erfc(abs(fn - expected_values[length]) / (math.sqrt(2.0) * sigma))
    return result_from_p("Maurer Universal", p_value, fn, f"L={length}, Q={q}, K={k}")


def test_random_excursions(bits: Sequence[int]) -> list[StatisticalTestResult]:
    states = (-4, -3, -2, -1, 1, 2, 3, 4)
    variant_states = tuple(range(-9, 0)) + tuple(range(1, 10))
    cycle_histograms = {state: [0] * 6 for state in states}
    total_visits = Counter()
    cycle_visits = Counter()
    position = 0
    cycle_count = 0

    for bit in bits:
        position += 1 if bit else -1
        if position in variant_states:
            total_visits[position] += 1
        if position in states:
            cycle_visits[position] += 1
        if position == 0:
            cycle_count += 1
            for state in states:
                cycle_histograms[state][min(cycle_visits.get(state, 0), 5)] += 1
            cycle_visits.clear()

    if position != 0:
        cycle_count += 1
        for state in states:
            cycle_histograms[state][min(cycle_visits.get(state, 0), 5)] += 1

    minimum_cycles = max(500, int(0.005 * math.sqrt(len(bits))))
    if cycle_count < minimum_cycles:
        reason = f"requires at least {minimum_cycles} zero-return cycles; observed {cycle_count}"
        return [skip_test("Random Excursions", reason), skip_test("Random Excursions Variant", reason)]

    p_values: list[float] = []
    for state in states:
        frequencies = cycle_histograms[state]
        abs_state = abs(state)
        probabilities = [0.0] * 6
        probabilities[0] = 1.0 - 1.0 / (2.0 * abs_state)
        for k in range(1, 5):
            probabilities[k] = (1.0 / (4.0 * abs_state * abs_state)) * (1.0 - 1.0 / (2.0 * abs_state)) ** (k - 1)
        probabilities[5] = (1.0 / (2.0 * abs_state)) * (1.0 - 1.0 / (2.0 * abs_state)) ** 4
        chi2 = sum((observed - cycle_count * p) ** 2 / (cycle_count * p) for observed, p in zip(frequencies, probabilities))
        p_values.append(chi_square_sf(chi2, 5))
    worst_excursion = min(p_values)

    variant_p_values: list[float] = []
    for state in variant_states:
        visits = total_visits.get(state, 0)
        denominator = math.sqrt(2.0 * cycle_count * (4.0 * abs(state) - 2.0))
        variant_p_values.append(math.erfc(abs(visits - cycle_count) / denominator))
    worst_variant = min(variant_p_values)
    return [
        result_from_p("Random Excursions", worst_excursion, details=f"J={cycle_count}, worst p-value across 8 states"),
        result_from_p("Random Excursions Variant", worst_variant, details=f"J={cycle_count}, worst p-value across 18 states"),
    ]


def diagnostic_metrics(data: bytes) -> list[StatisticalTestResult]:
    if not data:
        return [StatisticalTestResult("Shannon Entropy", "INFO", details="empty sample")]
    counts = Counter(data)
    entropy = -sum((count / len(data)) * math.log2(count / len(data)) for count in counts.values())
    compressed = zlib.compress(data, level=9)
    ratio = len(compressed) / len(data)
    duplicate_32 = 0
    seen: set[bytes] = set()
    for start in range(0, len(data) - 31, 32):
        block = data[start : start + 32]
        if block in seen:
            duplicate_32 += 1
        seen.add(block)
    return [
        StatisticalTestResult("Shannon Entropy", "INFO", statistic=entropy, details="bits per byte; diagnostic only"),
        StatisticalTestResult("Compression Ratio", "INFO", statistic=ratio, details="zlib-compressed size/original size; diagnostic only"),
        StatisticalTestResult("Duplicate 256-bit Blocks", "PASS" if duplicate_32 == 0 else "FAIL", statistic=float(duplicate_32), details="continuous duplicate-block sanity check"),
    ]


def run_builtin_tests(data: bytes) -> list[StatisticalTestResult]:
    bits = bits_from_bytes(data)
    results: list[StatisticalTestResult] = []
    results.extend(diagnostic_metrics(data))
    results.append(test_byte_frequency(data))
    results.append(test_monobit(bits))
    results.append(test_block_frequency(bits))
    results.append(test_runs(bits))
    results.append(test_longest_run(bits))
    results.extend(test_cumulative_sums(bits))
    results.extend(test_serial(bits))
    results.append(test_approximate_entropy(bits))
    results.append(test_poker(bits))
    for lag in (1, 2, 8, 16, 32):
        results.append(test_autocorrelation(bits, lag))
    results.append(test_binary_matrix_rank(bits))
    results.append(test_spectral(bits))
    results.append(test_overlapping_template(bits))
    results.append(test_maurer_universal(bits))
    results.append(test_linear_complexity(bits))
    results.extend(test_random_excursions(bits))
    return results


# ---------------------------------------------------------------------------
# Optional test integrations
# ---------------------------------------------------------------------------


def run_nistrng_tests(data: bytes) -> list[StatisticalTestResult]:
    if np is None:
        return [skip_test("NIST SP 800-22 package battery", "numpy is not installed", "nistrng")]
    try:
        from nistrng import SP800_22R1A_BATTERY, check_eligibility_all_battery, run_all_battery
    except ImportError:
        return [skip_test("NIST SP 800-22 package battery", "nistrng is not installed", "nistrng")]
    try:
        bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
        eligible = check_eligibility_all_battery(bits, SP800_22R1A_BATTERY)
        if not eligible:
            return [skip_test("NIST SP 800-22 package battery", "no package tests were eligible for this sample size", "nistrng")]
        raw_results = run_all_battery(bits, eligible, False)
        results: list[StatisticalTestResult] = []
        for test_result, elapsed_ms in raw_results:
            score = test_result.score
            if hasattr(score, "tolist"):
                score = score.tolist()
            if isinstance(score, (list, tuple)):
                numeric = [float(value) for value in score if isinstance(value, (int, float))]
                p_value = min(numeric) if numeric else None
                score_text = json.dumps(score)
            else:
                try:
                    p_value = float(score)
                except (TypeError, ValueError):
                    p_value = None
                score_text = str(score)
            results.append(
                StatisticalTestResult(
                    name=str(test_result.name),
                    status="PASS" if bool(test_result.passed) else "FAIL",
                    p_value=p_value,
                    details=f"score={score_text}; elapsed={elapsed_ms} ms",
                    suite="nistrng SP 800-22",
                )
            )
        ineligible = sorted(set(SP800_22R1A_BATTERY.keys()) - set(eligible.keys()))
        for name in ineligible:
            results.append(skip_test(str(name), "sample size is not eligible", "nistrng SP 800-22"))
        return results
    except Exception as exc:
        return [StatisticalTestResult("NIST SP 800-22 package battery", "ERROR", details=str(exc), suite="nistrng")]


def command_version(command: str) -> str:
    try:
        proc = subprocess.run([command, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5, check=False)
        return proc.stdout.decode(errors="replace").splitlines()[0][:200]
    except Exception:
        return "unknown"


def run_rngtest(path: Path, timeout: int) -> tuple[list[StatisticalTestResult], dict[str, Any]]:
    command = shutil.which("rngtest")
    if command is None:
        return [skip_test("rngtest FIPS battery", "rngtest command is not installed", "rngtest")], {"installed": False}
    block_count = path.stat().st_size // 2500
    if block_count < 1:
        return [skip_test("rngtest FIPS battery", "requires at least 2500 bytes", "rngtest")], {"installed": True, "version": command_version(command)}
    try:
        with path.open("rb") as handle:
            proc = subprocess.run(
                [command, "-c", str(block_count)],
                stdin=handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        text = (proc.stdout + proc.stderr).decode(errors="replace")
        match = re.search(r"FIPS 140-2 failures:\s*(\d+)", text)
        failures = int(match.group(1)) if match else None
        status = "PASS" if failures == 0 else "FAIL" if failures is not None else "ERROR"
        return [StatisticalTestResult("rngtest FIPS 140-2 battery", status, statistic=float(failures) if failures is not None else None, details=text[-2000:], suite="rngtest")], {"installed": True, "version": command_version(command), "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return [StatisticalTestResult("rngtest FIPS 140-2 battery", "ERROR", details="timeout", suite="rngtest")], {"installed": True, "version": command_version(command)}


def run_ent(path: Path, timeout: int) -> tuple[list[StatisticalTestResult], dict[str, Any]]:
    command = shutil.which("ent")
    if command is None:
        return [skip_test("ENT diagnostics", "ent command is not installed", "ent")], {"installed": False}
    try:
        proc = subprocess.run([command, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        text = (proc.stdout + proc.stderr).decode(errors="replace")
        return [StatisticalTestResult("ENT diagnostics", "INFO" if proc.returncode == 0 else "ERROR", details=text[-3000:], suite="ent")], {"installed": True, "version": command_version(command), "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return [StatisticalTestResult("ENT diagnostics", "ERROR", details="timeout", suite="ent")], {"installed": True, "version": command_version(command)}


def run_dieharder(path: Path, timeout: int) -> tuple[list[StatisticalTestResult], dict[str, Any]]:
    command = shutil.which("dieharder")
    if command is None:
        return [skip_test("Dieharder battery", "dieharder command is not installed", "dieharder")], {"installed": False}
    if path.stat().st_size < 10 * 1024 * 1024:
        return [skip_test("Dieharder battery", "requires at least 10 MiB here; much larger streams are preferable", "dieharder")], {"installed": True, "version": command_version(command)}
    try:
        proc = subprocess.run(
            [command, "-a", "-g", "201", "-f", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        text = (proc.stdout + proc.stderr).decode(errors="replace")
        failed = len(re.findall(r"\bFAILED\b", text, flags=re.IGNORECASE))
        weak = len(re.findall(r"\bWEAK\b", text, flags=re.IGNORECASE))
        status = "FAIL" if failed else "WARN" if weak else "PASS" if proc.returncode == 0 else "ERROR"
        details = f"FAILED={failed}, WEAK={weak}. Note: dieharder may rewind finite input files, so results can be misleading.\n{text[-5000:]}"
        return [StatisticalTestResult("Dieharder battery", status, statistic=float(failed), details=details, suite="dieharder")], {"installed": True, "version": command_version(command), "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return [StatisticalTestResult("Dieharder battery", "ERROR", details="timeout", suite="dieharder")], {"installed": True, "version": command_version(command)}


def practrand_size(size: int) -> Optional[str]:
    units = [(1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")]
    for unit_size, suffix in units:
        if size >= unit_size:
            power = 1 << int(math.floor(math.log2(size / unit_size)))
            return f"{power}{suffix}"
    return None


def run_practrand(path: Path, timeout: int) -> tuple[list[StatisticalTestResult], dict[str, Any]]:
    command = shutil.which("practrand-RNG_test") or shutil.which("RNG_test")
    if command is None:
        return [skip_test("PractRand battery", "PractRand RNG_test command is not installed", "PractRand")], {"installed": False}
    max_size = practrand_size(path.stat().st_size)
    if max_size is None or path.stat().st_size < 1024 * 1024:
        return [skip_test("PractRand battery", "requires at least 1 MiB", "PractRand")], {"installed": True, "version": command_version(command)}
    try:
        with path.open("rb") as handle:
            proc = subprocess.run(
                [command, "stdin", "-tf", "2", "-tlmin", "1MB", "-tlmax", max_size],
                stdin=handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        text = (proc.stdout + proc.stderr).decode(errors="replace")
        suspicious = bool(re.search(r"FAIL|suspicious|VERY SUSPICIOUS", text, flags=re.IGNORECASE))
        status = "FAIL" if suspicious else "PASS" if proc.returncode == 0 else "ERROR"
        return [StatisticalTestResult("PractRand battery", status, details=text[-5000:], suite="PractRand")], {"installed": True, "version": command_version(command), "returncode": proc.returncode, "tested_to": max_size}
    except subprocess.TimeoutExpired:
        return [StatisticalTestResult("PractRand battery", "ERROR", details="timeout", suite="PractRand")], {"installed": True, "version": command_version(command)}


# ---------------------------------------------------------------------------
# Generation, reporting and CLI
# ---------------------------------------------------------------------------


def source_status_is_mixed(source: SourceResult) -> bool:
    return source.status in {"ACCEPTED", "MIXED_UNCREDITED"} and bool(source.transcript_digest)


def build_auxiliary_digest(sources: Sequence[SourceResult]) -> bytes:
    h = hashlib.sha3_512()
    h.update(DOMAIN)
    h.update(frame(b"version", PROGRAM_VERSION.encode()))
    for source in sources:
        if not source_status_is_mixed(source):
            continue
        h.update(frame(b"source-name", source.name.encode()))
        h.update(frame(b"source-status", source.status.encode()))
        h.update(frame(b"source-digest", source.transcript_digest))
        h.update(frame(b"source-sample-count", struct.pack(">Q", source.sample_count)))
    return h.digest()


def create_output(path: Path, size: int, drbg: HmacDrbgSha512, overwrite: bool) -> str:
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    fd = os.open(path, flags, 0o600)
    sha256 = hashlib.sha256()
    remaining = size
    counter = 0
    try:
        with os.fdopen(fd, "wb", buffering=0) as handle:
            while remaining:
                count = min(OUTPUT_CHUNK, remaining)
                os_bytes = secrets.token_bytes(count)
                additional = struct.pack(">QQ", counter, remaining)
                mask = drbg.generate(count, additional)
                output = xor_bytes(os_bytes, mask)
                handle.write(output)
                sha256.update(output)
                remaining -= count
                counter += 1
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return sha256.hexdigest()


def load_test_sample(path: Path, max_bytes: int) -> tuple[bytes, bool]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(max_bytes)
    return data, len(data) == size


def save_raw_symbols(directory: Path, sources: Sequence[SourceResult]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    for source in sources:
        if not source.symbols:
            continue
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.name).strip("_").lower()
        path = directory / f"{safe_name}.symbols.bin"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.symbols)


def display_sources(console: Console, sources: Sequence[SourceResult]) -> None:
    console.section("Entropy and personalization sources")
    for source in sources:
        if source.status == "ACCEPTED":
            console.good(f"[ACCEPTED] {source.name}: {source.sample_count} samples")
        elif source.status == "MIXED_UNCREDITED":
            console.warn(f"[MIXED, NO ENTROPY CREDIT] {source.name}: {source.sample_count} samples")
        elif source.status == "SKIPPED":
            console.warn(f"[SKIPPED] {source.name}: {source.error}")
        else:
            console.error(f"[REJECTED] {source.name}: {source.error or 'health-test failure'}")
        for test in source.health_tests:
            text = f"    {test.status:12s} {test.name}"
            if test.observed is not None:
                text += f" observed={test.observed:.6g}"
            if test.threshold is not None:
                text += f" threshold={test.threshold:.6g}"
            if test.status == "PASS":
                console.good(text)
            elif test.status in {"INCONCLUSIVE", "SKIP"}:
                console.warn(text)
            elif test.status == "FAIL":
                console.error(text)
            else:
                console.info(text)


def display_tests(console: Console, results: Sequence[StatisticalTestResult]) -> None:
    console.section("Statistical tests")
    for result in results:
        text = f"[{result.status:5s}] {result.suite}: {result.name}"
        if result.p_value is not None:
            text += f" p={result.p_value:.6g}"
        if result.statistic is not None:
            text += f" statistic={result.statistic:.6g}"
        if result.status == "PASS":
            console.good(text)
        elif result.status in {"SKIP", "WARN", "INFO"}:
            console.warn(text)
        elif result.status in {"FAIL", "ERROR"}:
            console.error(text)
        else:
            console.info(text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect auxiliary hardware/human noise and generate N encryption-safe bytes using a mandatory OS CSPRNG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--bytes", "-n", type=int, required=True, dest="size", help="number of output bytes")
    parser.add_argument("--output", "-o", type=Path, required=True, help="binary output file")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output file")
    parser.add_argument("--print-hex", action="store_true", help="print output as hex when size is at most 4096 bytes")
    parser.add_argument("--json-report", type=Path, help="write a machine-readable JSON report")
    parser.add_argument("--save-raw-symbols", type=Path, help="save pre-conditioning symbol streams for offline analysis")
    parser.add_argument("--max-test-bytes", type=int, default=2 * 1024 * 1024, help="maximum contiguous output bytes loaded for built-in/NIST testing")
    parser.add_argument("--fail-on-test-failure", action="store_true", help="return exit status 3 if any statistical test fails")
    parser.add_argument("--require-healthy-sources", type=int, default=0, help="minimum number of auxiliary sources that must pass health checks")

    source = parser.add_argument_group("source selection")
    source.add_argument("--non-interactive", action="store_true", help="disable keyboard and mouse collection")
    source.add_argument("--human-seconds", type=float, default=10.0)
    source.add_argument("--no-jitter", action="store_true")
    source.add_argument("--jitter-samples", type=int, default=50_000)
    source.add_argument("--jitter-workers", type=int, default=min(4, os.cpu_count() or 1))
    source.add_argument("--no-disk-jitter", action="store_true")
    source.add_argument("--disk-iterations", type=int, default=384)
    source.add_argument("--disk-directory", type=Path)
    source.add_argument("--no-microphone", action="store_true")
    source.add_argument("--microphone-seconds", type=float, default=3.0)
    source.add_argument("--sample-rate", type=int, default=44_100)
    source.add_argument("--microphone-device")
    source.add_argument("--no-webcam", action="store_true")
    source.add_argument("--webcam-frames", type=int, default=16)
    source.add_argument("--webcam-device", type=int, default=0)
    source.add_argument("--webcam-warmup", type=int, default=5)
    source.add_argument("--no-hwrng", action="store_true")
    source.add_argument("--no-tpm", action="store_true")
    source.add_argument("--hardware-bytes", type=int, default=4096)
    source.add_argument("--hardware-timeout", type=float, default=5.0)
    source.add_argument("--serial-device")
    source.add_argument("--serial-baud", type=int, default=115200)
    source.add_argument("--serial-bytes", type=int, default=4096)
    source.add_argument("--serial-timeout", type=float, default=5.0)

    tests = parser.add_argument_group("test suites")
    tests.add_argument("--no-built-in-tests", dest="no_builtin_tests", action="store_true")
    tests.add_argument("--no-nistrng", action="store_true", help="do not attempt the optional nistrng SP 800-22 battery")
    tests.add_argument("--external-tests", choices=("none", "auto", "all"), default="auto", help="auto runs lightweight installed tools; all additionally runs Dieharder and PractRand")
    tests.add_argument("--external-timeout", type=int, default=300)

    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.size <= 0 or args.size > MAX_OUTPUT_BYTES:
        raise ValueError(f"--bytes must be between 1 and {MAX_OUTPUT_BYTES}")
    if args.max_test_bytes <= 0:
        raise ValueError("--max-test-bytes must be positive")
    if args.require_healthy_sources < 0:
        raise ValueError("--require-healthy-sources cannot be negative")
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"output exists: {args.output}; use --overwrite to replace it")
    args.output.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    console = Console(color=not args.no_color and sys.stdout.isatty(), quiet=args.quiet)
    warnings: list[str] = []

    try:
        validate_args(args)
    except Exception as exc:
        console.error(str(exc))
        return 2

    console.section("Collection")
    console.info("Acquiring mandatory operating-system CSPRNG seed...")
    try:
        os_seed = secure_os_seed()
    except Exception as exc:
        console.error(f"OS CSPRNG acquisition failed: {exc}")
        return 2
    console.good("OS CSPRNG seed acquired and duplicate-block sanity check passed.")

    sources: list[SourceResult] = []

    collectors: list[tuple[str, bool, Callable[[], SourceResult]]] = [
        ("CPU/scheduler jitter", not args.no_jitter, lambda: collect_cpu_scheduler_jitter(args.jitter_samples, args.jitter_workers)),
        ("disk jitter", not args.no_disk_jitter, lambda: collect_disk_timing_jitter(args.disk_iterations, args.disk_directory)),
        ("microphone", not args.no_microphone, lambda: collect_microphone(args.microphone_seconds, args.sample_rate, args.microphone_device)),
        ("webcam", not args.no_webcam, lambda: collect_webcam(args.webcam_frames, args.webcam_device, args.webcam_warmup)),
        ("Linux /dev/hwrng", not args.no_hwrng, lambda: collect_linux_hwrng(args.hardware_bytes, args.hardware_timeout)),
        ("TPM", not args.no_tpm, lambda: collect_tpm(args.hardware_bytes, args.hardware_timeout)),
        ("serial TRNG", args.serial_device is not None, lambda: collect_serial_trng(args.serial_device, args.serial_baud, args.serial_bytes, args.serial_timeout)),
    ]

    for label, enabled, collector in collectors:
        if not enabled:
            sources.append(skipped_source(label, "disabled by command line or not configured"))
            continue
        console.info(f"Collecting {label}...")
        try:
            sources.append(collector())
        except Exception as exc:
            sources.append(rejected_source(label, f"unhandled collector error: {exc}"))

    if not args.non_interactive:
        console.info("Collecting human timing input...")
        sources.append(collect_human_input(args.human_seconds, console))
    else:
        sources.append(skipped_source("Human keyboard and mouse timing", "disabled with --non-interactive"))

    sources.append(collect_environmental_metadata())
    display_sources(console, sources)

    healthy_count = sum(source.status == "ACCEPTED" for source in sources)
    if healthy_count < args.require_healthy_sources:
        console.error(f"Only {healthy_count} auxiliary sources passed health checks; {args.require_healthy_sources} required.")
        return 2

    if args.save_raw_symbols:
        save_raw_symbols(args.save_raw_symbols, sources)
        console.info(f"Saved raw symbol streams to {args.save_raw_symbols}")

    auxiliary_digest = build_auxiliary_digest(sources)
    personalization = hashlib.sha3_512(
        DOMAIN
        + frame(b"auxiliary-digest", auxiliary_digest)
        + frame(b"output-size", struct.pack(">Q", args.size))
        + frame(b"output-path-hash", hashlib.sha256(str(args.output.resolve()).encode()).digest())
    ).digest()
    drbg = HmacDrbgSha512(os_seed + auxiliary_digest + personalization)

    console.section("Generation")
    try:
        output_sha256 = create_output(args.output, args.size, drbg, args.overwrite)
    except Exception as exc:
        console.error(f"Output generation failed: {exc}")
        return 2
    console.good(f"Wrote {args.size} bytes to {args.output}")
    console.info(f"SHA-256: {output_sha256}")

    test_data, tested_full = load_test_sample(args.output, min(args.max_test_bytes, args.size))
    if not tested_full:
        warning = f"Statistical tests cover only the first {len(test_data)} of {args.size} output bytes."
        warnings.append(warning)
        console.warn(warning)

    test_results: list[StatisticalTestResult] = []
    external_tools: dict[str, Any] = {}
    if not args.no_builtin_tests:
        test_results.extend(run_builtin_tests(test_data))
    if not args.no_nistrng:
        test_results.extend(run_nistrng_tests(test_data))

    if args.external_tests in {"auto", "all"}:
        rng_results, rng_meta = run_rngtest(args.output, args.external_timeout)
        test_results.extend(rng_results)
        external_tools["rngtest"] = rng_meta
        ent_results, ent_meta = run_ent(args.output, args.external_timeout)
        test_results.extend(ent_results)
        external_tools["ent"] = ent_meta
    if args.external_tests == "all":
        dieharder_results, dieharder_meta = run_dieharder(args.output, args.external_timeout)
        test_results.extend(dieharder_results)
        external_tools["dieharder"] = dieharder_meta
        practrand_results, practrand_meta = run_practrand(args.output, args.external_timeout)
        test_results.extend(practrand_results)
        external_tools["PractRand"] = practrand_meta

    display_tests(console, test_results)

    failures = [result for result in test_results if result.status == "FAIL"]
    errors = [result for result in test_results if result.status == "ERROR"]
    skipped = [result for result in test_results if result.status == "SKIP"]
    console.section("Summary")
    if failures:
        console.error(f"{len(failures)} statistical test result(s) reported FAIL.")
    else:
        console.good("No executed statistical test reported FAIL.")
    if errors:
        console.error(f"{len(errors)} test integration(s) reported ERROR.")
    if skipped:
        console.warn(f"{len(skipped)} test(s) were skipped because of sample-size or missing-tool constraints.")
    console.warn("Passing statistical tests does not prove physical entropy or certify this implementation.")

    if args.print_hex:
        if args.size > 4096:
            console.warn("Refusing to print more than 4096 output bytes as hex.")
        else:
            print(args.output.read_bytes().hex())

    report = GenerationReport(
        program_version=PROGRAM_VERSION,
        created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        platform=platform.platform(),
        python_version=sys.version,
        output_path=str(args.output.resolve()),
        output_bytes=args.size,
        output_sha256=output_sha256,
        tested_bytes=len(test_data),
        tested_full_output=tested_full,
        sources=[source.report_dict() for source in sources],
        tests=[asdict(result) for result in test_results],
        external_tools=external_tools,
        warnings=warnings + ["Passing statistical tests does not prove entropy or provide SP 800-90B validation."],
    )
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(args.json_report, 0o600)
        except OSError:
            pass
        console.info(f"JSON report written to {args.json_report}")

    if args.fail_on_test_failure and (failures or errors):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
