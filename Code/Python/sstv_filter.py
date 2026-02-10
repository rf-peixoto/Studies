from PIL import Image
import numpy as np
from scipy.io import wavfile

def image_to_sstv_like_audio(
    input_path: str,
    wav_path: str,
    width: int = 360,
    height: int = 256,
    sample_rate: int = 44100,
    col_duration: float = 0.02,   # aumente para 0.03 se ainda estiver fraco
    f_min: float = 300.0,
    f_max: float = 6000.0,        # banda mais larga = menos compressão/mais separação
    gamma: float = 1.0,
    amp_curve: float = 1.0        # >1 aumenta contraste (ex: 1.4)
) -> None:
    img = Image.open(input_path).convert("L").resize((width, height), Image.BICUBIC)
    a = np.asarray(img, dtype=np.float32) / 255.0

    a = np.clip(a, 0.0, 1.0) ** gamma
    a = np.clip(a, 0.0, 1.0) ** amp_curve

    n_samp_col = max(1, int(sample_rate * col_duration))
    t = np.arange(n_samp_col, dtype=np.float32) / sample_rate
    freqs = np.linspace(f_min, f_max, height, dtype=np.float32)
    osc = np.sin(2.0 * np.pi * freqs[:, None] * t[None, :]).astype(np.float32)
    audio = np.zeros(width * n_samp_col, dtype=np.float32)
    window = np.hanning(n_samp_col).astype(np.float32)

    for x in range(width):
        amps = a[::-1, x].astype(np.float32)

        col = (amps[:, None] * osc).sum(axis=0)

        peak = np.max(np.abs(col)) + 1e-9
        col = (col / peak) * window

        audio[x * n_samp_col:(x + 1) * n_samp_col] = col

    audio /= (np.max(np.abs(audio)) + 1e-9)
    pcm = (audio * 32767.0).astype(np.int16)
    wavfile.write(wav_path, sample_rate, pcm)

image_to_sstv_like_audio("input.jpg", "sstv_like.wav", col_duration=0.02, f_max=6000, amp_curve=1.4)
