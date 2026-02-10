#!/usr/bin/env python3
"""
sstv_like.py
SSTV-inspired image -> audio -> spectrogram tool.

Dependencies:
  pip install numpy pillow scipy matplotlib

Examples:
  # 1) Image -> WAV + PNG spectrogram
  python sstv_like.py encode -i input.png -o out.wav --spec out.png --width 360 --height 256 \
      --fmin 300 --fmax 6000 --col-ms 20 --nfft 8192 --hop 512 --scale linear

  # 2) Only render a spectrogram from an existing wav
  python sstv_like.py spec -i out.wav -o out.png --fmin 300 --fmax 6000 --nfft 8192 --hop 512 --scale linear

  # 3) If you want denser vertical detail, use narrower band + larger NFFT (but then set fmax accordingly)
  python sstv_like.py encode -i input.png -o out.wav --spec out.png --fmin 300 --fmax 3000 --nfft 16384 --col-ms 25
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from scipy.io import wavfile
import matplotlib.pyplot as plt


# -----------------------------
# Utility / DSP helpers
# -----------------------------

def _hann(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones((n,), dtype=np.float32)
    return np.hanning(n).astype(np.float32)

def _hamming(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones((n,), dtype=np.float32)
    return np.hamming(n).astype(np.float32)

def _blackman(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones((n,), dtype=np.float32)
    return np.blackman(n).astype(np.float32)

def make_window(name: str, n: int) -> np.ndarray:
    name = name.lower()
    if name == "hann":
        return _hann(n)
    if name == "hamming":
        return _hamming(n)
    if name == "blackman":
        return _blackman(n)
    if name == "rect":
        return np.ones((n,), dtype=np.float32)
    raise ValueError(f"Unsupported window '{name}'. Use hann/hamming/blackman/rect.")

def db_to_linear(db: float) -> float:
    return float(10.0 ** (db / 20.0))

def clamp01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)

def normalize_audio(x: np.ndarray, method: str = "peak", target_dbfs: float = -1.0) -> np.ndarray:
    """
    method:
      - peak: peak normalize to 0 dBFS (or target_dbfs)
      - rms: normalize RMS to target_dbfs
    """
    x = x.astype(np.float32, copy=False)
    if method == "peak":
        peak = float(np.max(np.abs(x)) + 1e-12)
        gain = db_to_linear(target_dbfs) / peak
        return x * gain

    if method == "rms":
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        gain = db_to_linear(target_dbfs) / rms
        return x * gain

    raise ValueError("normalize method must be 'peak' or 'rms'.")

def apply_preemphasis(x: np.ndarray, coeff: float = 0.97) -> np.ndarray:
    """
    Simple pre-emphasis filter: y[n] = x[n] - coeff*x[n-1]
    Can improve “edge” visibility in spectrograms for some images.
    """
    if coeff <= 0.0:
        return x
    y = np.empty_like(x, dtype=np.float32)
    y[0] = x[0]
    y[1:] = x[1:] - coeff * x[:-1]
    return y

def suggest_nfft(sr: int, height: int, fmin: float, fmax: float, safety: float = 0.75) -> int:
    """
    Heuristic: you want frequency resolution Δf <= safety * (band/(height-1)).
    Δf ≈ sr/NFFT  => NFFT >= sr / Δf.
    Returns next power of two.
    """
    if height <= 2:
        return 4096
    band = max(1.0, float(fmax - fmin))
    step = band / float(height - 1)
    target_df = max(1e-6, safety * step)
    nfft = int(math.ceil(sr / target_df))
    # next power of two
    p = 1
    while p < nfft:
        p <<= 1
    return max(512, p)


# -----------------------------
# Encoding: image -> audio
# -----------------------------

@dataclass
class EncodeConfig:
    width: int = 360
    height: int = 256
    sample_rate: int = 44100

    # mapping / aesthetics
    fmin: float = 300.0
    fmax: float = 6000.0
    col_ms: float = 20.0  # milliseconds per column

    # image shaping
    gamma: float = 1.0       # perceptual gamma
    amp_curve: float = 1.0   # additional power curve for contrast
    invert: bool = False     # invert image brightness

    # audio shaping
    col_window: str = "hann"     # window applied per column segment
    normalize: str = "peak"      # peak or rms
    target_dbfs: float = -1.0
    preemph: float = 0.0         # 0 disables, else typical 0.97
    noise_db: Optional[float] = None  # add noise at SNR-ish level (negative => lower)
    add_lead_in_ms: float = 0.0
    add_lead_out_ms: float = 0.0

def load_image_as_matrix(path: str, width: int, height: int) -> np.ndarray:
    img = Image.open(path).convert("L").resize((width, height), Image.BICUBIC)
    a = np.asarray(img, dtype=np.float32) / 255.0
    return a

def encode_image_to_audio(img01: np.ndarray, cfg: EncodeConfig) -> np.ndarray:
    """
    SSTV-like spectrogram encoding:
    - Each column is one time slice.
    - Each row maps to a frequency bin between fmin..fmax.
    - Pixel brightness maps to amplitude of that bin (additive synthesis).
    """
    a = img01
    if cfg.invert:
        a = 1.0 - a

    a = clamp01(a) ** float(cfg.gamma)
    a = clamp01(a) ** float(cfg.amp_curve)

    h, w = a.shape
    if h != cfg.height or w != cfg.width:
        raise ValueError(f"Image matrix shape {a.shape} does not match cfg {(cfg.height, cfg.width)}")

    n_samp_col = max(1, int(cfg.sample_rate * (cfg.col_ms / 1000.0)))
    t = (np.arange(n_samp_col, dtype=np.float32) / float(cfg.sample_rate))

    freqs = np.linspace(cfg.fmin, cfg.fmax, cfg.height, dtype=np.float32)

    # Precompute oscillators for one column window:
    # osc[row, sample] = sin(2π f_row t)
    osc = np.sin(2.0 * np.pi * freqs[:, None] * t[None, :]).astype(np.float32)

    win = make_window(cfg.col_window, n_samp_col)

    out = np.zeros(cfg.width * n_samp_col, dtype=np.float32)

    for x in range(cfg.width):
        # flip vertically: bottom row -> low frequency (typical spectrogram convention)
        amps = a[::-1, x].astype(np.float32)

        col = (amps[:, None] * osc).sum(axis=0)

        # per-column normalize (optional but helps prevent a few bright columns clipping everything)
        peak = float(np.max(np.abs(col)) + 1e-12)
        col = (col / peak) * win

        out[x * n_samp_col:(x + 1) * n_samp_col] = col

    # optional lead-in/out silence
    lead_in = int(cfg.sample_rate * (cfg.add_lead_in_ms / 1000.0))
    lead_out = int(cfg.sample_rate * (cfg.add_lead_out_ms / 1000.0))
    if lead_in > 0 or lead_out > 0:
        out = np.concatenate([
            np.zeros(lead_in, dtype=np.float32),
            out,
            np.zeros(lead_out, dtype=np.float32),
        ])

    # optional pre-emphasis
    out = apply_preemphasis(out, cfg.preemph)

    # optional noise (useful if you want “radio-like” texture)
    if cfg.noise_db is not None:
        # noise_db here is relative to signal RMS; e.g. -30 means noise RMS is 30 dB below signal RMS
        sig_rms = float(np.sqrt(np.mean(out * out) + 1e-12))
        noise_rms = sig_rms * db_to_linear(float(cfg.noise_db))
        noise = np.random.normal(0.0, noise_rms, size=out.shape).astype(np.float32)
        out = out + noise

    out = normalize_audio(out, method=cfg.normalize, target_dbfs=cfg.target_dbfs)

    # final safety clamp
    out = np.clip(out, -1.0, 1.0).astype(np.float32)
    return out

def write_wav(path: str, sr: int, audio: np.ndarray) -> None:
    pcm = (audio * 32767.0).astype(np.int16)
    wavfile.write(path, sr, pcm)


# -----------------------------
# Spectrogram rendering: wav -> png
# -----------------------------

@dataclass
class SpecConfig:
    sample_rate: Optional[int] = None  # if None, read from wav
    fmin: float = 0.0
    fmax: Optional[float] = None  # if None, use Nyquist
    nfft: int = 8192
    hop: int = 512
    scale: str = "linear"  # linear or log
    dyn_range_db: float = 80.0  # displayed dynamic range
    figsize: Tuple[float, float] = (12.0, 6.0)
    dpi: int = 200

def render_spectrogram_png(wav_path: str, out_png: str, cfg: SpecConfig) -> None:
    sr, data = wavfile.read(wav_path)
    if cfg.sample_rate is not None and cfg.sample_rate != sr:
        # The WAV's sr is authoritative; override only if you know it is wrong.
        sr = cfg.sample_rate

    if data.dtype.kind in ("i", "u"):
        # int PCM -> float [-1,1]
        maxv = float(np.iinfo(data.dtype).max)
        x = (data.astype(np.float32) / maxv).clip(-1.0, 1.0)
    else:
        x = data.astype(np.float32)

    nfft = int(cfg.nfft)
    hop = int(cfg.hop)
    if hop <= 0 or hop >= nfft:
        raise ValueError("hop must be >0 and < nfft.")

    # Use matplotlib.specgram (no seaborn, and no manual colors)
    fig = plt.figure(figsize=cfg.figsize, dpi=cfg.dpi)
    ax = fig.add_subplot(1, 1, 1)

    # specgram returns Pxx, freqs, bins, im
    Pxx, freqs, bins, im = ax.specgram(
        x,
        NFFT=nfft,
        Fs=sr,
        noverlap=(nfft - hop),
        scale=("dB" if cfg.scale.lower() == "log" else "linear"),
    )

    fmax = float(cfg.fmax) if cfg.fmax is not None else (sr / 2.0)
    ax.set_ylim(float(cfg.fmin), fmax)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")

    # dynamic range control:
    # In dB mode, Pxx already in dB; in linear, it is power.
    if cfg.scale.lower() == "log":
        vmax = float(np.max(Pxx))
        vmin = vmax - float(cfg.dyn_range_db)
        im.set_clim(vmin=vmin, vmax=vmax)
    else:
        # For linear, clamp by percentile to avoid a few peaks dominating.
        hi = float(np.percentile(Pxx, 99.5))
        lo = float(np.percentile(Pxx, 5.0))
        im.set_clim(vmin=lo, vmax=hi)

    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


# -----------------------------
# CLI
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sstv_like.py", description="SSTV-inspired image<->audio spectrogram tool.")
    sub = p.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode", help="Encode an image into an SSTV-like WAV, optionally also render spectrogram PNG.")
    enc.add_argument("-i", "--input", required=True, help="Input image file (png/jpg/etc).")
    enc.add_argument("-o", "--output", required=True, help="Output WAV path.")
    enc.add_argument("--spec", default=None, help="If set, also write a spectrogram PNG to this path.")

    enc.add_argument("--width", type=int, default=360)
    enc.add_argument("--height", type=int, default=256)
    enc.add_argument("--sr", type=int, default=44100)

    enc.add_argument("--fmin", type=float, default=300.0)
    enc.add_argument("--fmax", type=float, default=6000.0)
    enc.add_argument("--col-ms", type=float, default=20.0, help="Milliseconds per image column (time resolution).")

    enc.add_argument("--gamma", type=float, default=1.0)
    enc.add_argument("--amp-curve", type=float, default=1.0, help="Additional power curve for contrast (e.g. 1.2–2.0).")
    enc.add_argument("--invert", action="store_true")

    enc.add_argument("--col-window", type=str, default="hann", choices=["hann", "hamming", "blackman", "rect"])
    enc.add_argument("--normalize", type=str, default="peak", choices=["peak", "rms"])
    enc.add_argument("--target-dbfs", type=float, default=-1.0)
    enc.add_argument("--preemph", type=float, default=0.0, help="0 disables. Typical 0.97.")
    enc.add_argument("--noise-db", type=float, default=None,
                     help="Add noise RMS relative to signal RMS (dB). Example: -30 adds light noise. Omit to disable.")
    enc.add_argument("--lead-in-ms", type=float, default=0.0)
    enc.add_argument("--lead-out-ms", type=float, default=0.0)

    enc.add_argument("--auto-nfft", action="store_true",
                     help="If also rendering spectrogram, suggest NFFT from height & band. Overrides --nfft if set.")

    # Spec options (when --spec is used)
    enc.add_argument("--nfft", type=int, default=8192)
    enc.add_argument("--hop", type=int, default=512)
    enc.add_argument("--scale", type=str, default="linear", choices=["linear", "log"])
    enc.add_argument("--dyn-range-db", type=float, default=80.0)
    enc.add_argument("--dpi", type=int, default=200)
    enc.add_argument("--fig-w", type=float, default=12.0)
    enc.add_argument("--fig-h", type=float, default=6.0)

    sp = sub.add_parser("spec", help="Render a spectrogram PNG from a WAV.")
    sp.add_argument("-i", "--input", required=True, help="Input WAV.")
    sp.add_argument("-o", "--output", required=True, help="Output PNG.")

    sp.add_argument("--fmin", type=float, default=300.0)
    sp.add_argument("--fmax", type=float, default=6000.0)
    sp.add_argument("--nfft", type=int, default=8192)
    sp.add_argument("--hop", type=int, default=512)
    sp.add_argument("--scale", type=str, default="linear", choices=["linear", "log"])
    sp.add_argument("--dyn-range-db", type=float, default=80.0)
    sp.add_argument("--dpi", type=int, default=200)
    sp.add_argument("--fig-w", type=float, default=12.0)
    sp.add_argument("--fig-h", type=float, default=6.0)

    sub.add_parser("recommend", help="Print practical parameter recommendations for common goals.")

    return p

def cmd_recommend() -> None:
    print(
        "\nParameter recommendations (practical):\n"
        "1) If the image looks 'compressed' in Y in a spectrogram tool:\n"
        "   - Ensure the spectrogram max frequency matches your fmax.\n"
        "   - Increase NFFT (e.g. 8192 or 16384 at 44100 Hz) for better vertical resolution.\n\n"
        "2) If the image is not readable (too faint):\n"
        "   - Increase col-ms (e.g. 20 -> 30).\n"
        "   - Try amp-curve 1.3–2.0.\n"
        "   - Use log scale with dyn-range-db ~ 60–100.\n\n"
        "3) If you want more vertical detail with height=256:\n"
        "   - Use wider band (e.g. fmin=300, fmax=6000) OR\n"
        "   - Use very large NFFT for narrow band (e.g. fmax=3000 with NFFT>=16384).\n\n"
        "4) Typical stable starting point:\n"
        "   encode: fmin=300 fmax=6000 col-ms=20 width=360 height=256 sr=44100\n"
        "   spec:   nfft=8192 hop=512 scale=linear (or log) dyn-range-db=80\n"
    )

def main() -> None:
    p = build_parser()
    args = p.parse_args()

    if args.cmd == "recommend":
        cmd_recommend()
        return

    if args.cmd == "encode":
        cfg = EncodeConfig(
            width=args.width,
            height=args.height,
            sample_rate=args.sr,
            fmin=args.fmin,
            fmax=args.fmax,
            col_ms=args.col_ms,
            gamma=args.gamma,
            amp_curve=args.amp_curve,
            invert=args.invert,
            col_window=args.col_window,
            normalize=args.normalize,
            target_dbfs=args.target_dbfs,
            preemph=args.preemph,
            noise_db=args.noise_db,
            add_lead_in_ms=args.lead_in_ms,
            add_lead_out_ms=args.lead_out_ms,
        )

        img01 = load_image_as_matrix(args.input, cfg.width, cfg.height)
        audio = encode_image_to_audio(img01, cfg)
        write_wav(args.output, cfg.sample_rate, audio)
        print(f"[OK] Wrote WAV: {args.output}")

        if args.spec:
            nfft = args.nfft
            if args.auto_nfft:
                nfft = suggest_nfft(cfg.sample_rate, cfg.height, cfg.fmin, cfg.fmax)
                print(f"[info] auto-nfft suggested: {nfft}")

            scfg = SpecConfig(
                fmin=cfg.fmin,
                fmax=cfg.fmax,
                nfft=nfft,
                hop=args.hop,
                scale=args.scale,
                dyn_range_db=args.dyn_range_db,
                figsize=(args.fig_w, args.fig_h),
                dpi=args.dpi,
            )
            render_spectrogram_png(args.output, args.spec, scfg)
            print(f"[OK] Wrote spectrogram PNG: {args.spec}")

        return

    if args.cmd == "spec":
        scfg = SpecConfig(
            fmin=args.fmin,
            fmax=args.fmax,
            nfft=args.nfft,
            hop=args.hop,
            scale=args.scale,
            dyn_range_db=args.dyn_range_db,
            figsize=(args.fig_w, args.fig_h),
            dpi=args.dpi,
        )
        render_spectrogram_png(args.input, args.output, scfg)
        print(f"[OK] Wrote spectrogram PNG: {args.output}")
        return

    raise SystemExit("Unknown command")

if __name__ == "__main__":
    main()
