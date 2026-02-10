from PIL import Image
import numpy as np
from scipy.io import wavfile

def image_to_sstv_like_audio(
    input_path: str,
    wav_path: str,
    width: int = 320,
    height: int = 256,
    sample_rate: int = 44100,
    col_duration: float = 0.008,  # seconds per column
    f_min: float = 300.0,
    f_max: float = 3000.0,
    gamma: float = 1.0
) -> None:
    """
    Make an SSTV-like audio file by encoding image brightness into spectral energy over time.
    This is NOT a standard SSTV mode; it is an aesthetic/educational transform.
    """
    img = Image.open(input_path).convert("L").resize((width, height), Image.BICUBIC)
    a = np.asarray(img, dtype=np.float32) / 255.0
    if gamma != 1.0:
        a = np.clip(a, 0, 1) ** gamma

    n_col = width
    n_samp_col = max(1, int(sample_rate * col_duration))
    t = np.arange(n_samp_col, dtype=np.float32) / sample_rate

    # Frequency bins mapped from rows (bottom = low freq, top = high freq)
    freqs = np.linspace(f_min, f_max, height, dtype=np.float32)

    # Precompute oscillators for each "row frequency" within one column window
    # Shape: (height, n_samp_col)
    osc = np.sin(2.0 * np.pi * freqs[:, None] * t[None, :]).astype(np.float32)

    audio = np.zeros(n_col * n_samp_col, dtype=np.float32)

    # Optional window to reduce clicks between columns
    window = np.hanning(n_samp_col).astype(np.float32)

    for x in range(n_col):
        # Column amplitudes: flip vertically so low rows map to low frequencies
        amps = a[::-1, x].astype(np.float32)  # shape (height,)

        # Mix spectral slice
        col = (amps[:, None] * osc).sum(axis=0)

        # Normalize per column to avoid clipping, then apply window
        peak = np.max(np.abs(col)) + 1e-9
        col = (col / peak) * window

        audio[x * n_samp_col:(x + 1) * n_samp_col] = col

    # Global normalization and 16-bit PCM export
    audio /= (np.max(np.abs(audio)) + 1e-9)
    pcm = (audio * 32767.0).astype(np.int16)
    wavfile.write(wav_path, sample_rate, pcm)

# Example:
image_to_sstv_like_audio("input.jpg", "sstv_like.wav", width=360, height=256, col_duration=0.007)
