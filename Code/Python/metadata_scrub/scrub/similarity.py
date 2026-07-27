"""Structural similarity, used to decide how hard a file can be compressed.

A quality slider that feeds straight into the encoder is a guess: JPEG quality
82 means something different for a photograph than for a screenshot, and
something different again for WebP or AVIF. So instead of passing the number
through, we ask what the user actually wants -- "I should not be able to see the
difference" -- and search for the smallest file that still meets it.

SSIM compares local structure rather than absolute pixel error, which is why it
tracks visible damage far better than PSNR does. This is the standard formula
with a uniform window instead of a gaussian one, computed with integral images
so it stays linear in the pixel count.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# Analysis is capped here. Above it the images are downsampled by an equal
# factor before comparison: the cost is linear in pixels and a 48 MP phone photo
# would otherwise spend longer being measured than encoded.
MAX_ANALYSIS_PIXELS = 2_000_000

WINDOW = 7
C1 = (0.01 * 255) ** 2
C2 = (0.03 * 255) ** 2


def _boxsum(a: np.ndarray, w: int) -> np.ndarray:
    """Sum over every w x w window, via a summed-area table."""
    integral = np.cumsum(np.cumsum(a, axis=0, dtype=np.float64), axis=1)
    integral = np.pad(integral, ((1, 0), (1, 0)))
    return (integral[w:, w:] - integral[:-w, w:]
            - integral[w:, :-w] + integral[:-w, :-w])


def _luma(im: Image.Image, size: tuple[int, int] | None) -> np.ndarray:
    if im.mode != "L":
        im = im.convert("L")
    if size and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, dtype=np.float64)


def ssim(a: Image.Image, b: Image.Image) -> float:
    """Mean SSIM over the luma channel. 1.0 is identical."""
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)

    size = None
    pixels = a.size[0] * a.size[1]
    if pixels > MAX_ANALYSIS_PIXELS:
        scale = (MAX_ANALYSIS_PIXELS / pixels) ** 0.5
        size = (max(WINDOW + 1, int(a.size[0] * scale)),
                max(WINDOW + 1, int(a.size[1] * scale)))

    x = _luma(a, size)
    y = _luma(b, size if size else a.size)
    if x.shape != y.shape:
        y = _luma(b, (x.shape[1], x.shape[0]))
    if min(x.shape) < WINDOW:
        return 1.0 if np.array_equal(x, y) else 0.0

    w = WINDOW
    n = w * w
    mu_x = _boxsum(x, w) / n
    mu_y = _boxsum(y, w) / n
    sigma_x = _boxsum(x * x, w) / n - mu_x * mu_x
    sigma_y = _boxsum(y * y, w) / n - mu_y * mu_y
    sigma_xy = _boxsum(x * y, w) / n - mu_x * mu_y

    numerator = (2 * mu_x * mu_y + C1) * (2 * sigma_xy + C2)
    denominator = (mu_x ** 2 + mu_y ** 2 + C1) * (sigma_x + sigma_y + C2)
    return float(np.mean(numerator / denominator))


# Named levels, in the order a person would think about them. The number is the
# SSIM floor a candidate encode has to clear to be accepted.
LEVELS = {
    "lossless":      None,    # no search: pixels must come back untouched
    "imperceptible": 0.995,
    "high":          0.985,
    "balanced":      0.965,
    "small":         0.935,
    "tiny":          0.895,
}

LEVEL_ORDER = ["lossless", "imperceptible", "high", "balanced", "small", "tiny"]


def floor_for(level: str) -> float | None:
    return LEVELS.get(level, LEVELS["balanced"])
