"""Image metadata removal and recompression.

Stripping strategy: Pillow carries `im.info` (EXIF, XMP, ICC, PNG text chunks,
GPS, thumbnails) through a normal open/save round trip. So we do not "save
without metadata" -- we rebuild the image from its raw pixel buffer, which
leaves every ancillary chunk behind by construction, then write the new file
with metadata parameters explicitly blanked.

Two things are read *before* the strip because dropping them silently corrupts
the picture rather than protecting anyone:
  - EXIF orientation, which is baked into the pixels first, otherwise every
    phone photo comes out rotated.
  - The ICC profile, which is converted to sRGB first, otherwise wide-gamut
    photos come out desaturated or oversaturated.
"""
from __future__ import annotations

import io
import os

from PIL import Image, ImageCms, ImageOps, ImageSequence

try:  # HEIC/HEIF is what iPhones actually produce.
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - optional dependency
    HEIF_OK = False

# Refuse absurd pixel counts rather than letting a crafted file exhaust memory.
Image.MAX_IMAGE_PIXELS = 400_000_000

ANIMATED_FORMATS = {"GIF", "WEBP", "APNG", "PNG"}

_SRGB = ImageCms.createProfile("sRGB")


def _strip(im: Image.Image) -> Image.Image:
    """Rebuild an image from raw pixels, leaving all ancillary data behind."""
    clean = Image.frombytes(im.mode, im.size, im.tobytes())
    return clean


def _to_srgb(im: Image.Image, log) -> Image.Image:
    """Convert an embedded colour profile into sRGB, then discard the profile."""
    icc = im.info.get("icc_profile")
    if not icc:
        return im
    try:
        src = ImageCms.getOpenProfile(io.BytesIO(icc))
        name = ImageCms.getProfileDescription(src).strip()
        if im.mode not in ("RGB", "RGBA", "L", "CMYK"):
            im = im.convert("RGB")
        out_mode = "RGBA" if im.mode == "RGBA" else "RGB"
        im = ImageCms.profileToProfile(im, src, _SRGB, outputMode=out_mode)
        log(f"colour profile '{name[:48]}' converted to sRGB, then dropped")
    except Exception as exc:
        log(f"colour profile unreadable ({exc}); converting to RGB")
        if im.mode not in ("RGB", "RGBA", "L"):
            im = im.convert("RGB")
    return im


def _fit(im: Image.Image, max_edge: int, log) -> Image.Image:
    if not max_edge or max(im.size) <= max_edge:
        return im
    before = im.size
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    log(f"resized {before[0]}x{before[1]} -> {im.size[0]}x{im.size[1]}")
    return im


def _save_params(fmt: str, quality: int, im: Image.Image) -> dict:
    """Encoder settings. These are where the actual compression wins live."""
    if fmt == "JPEG":
        return {
            "format": "JPEG",
            "quality": quality,
            "optimize": True,          # second Huffman pass, ~2-5% smaller, free
            "progressive": True,       # smaller above ~10KB and renders sooner
            # 4:4:4 keeps chroma detail when quality is high; 4:2:0 halves chroma
            # data when it is not, which is where most of the saving comes from.
            "subsampling": 0 if quality >= 88 else 2,
            "exif": b"",
            "icc_profile": None,
        }
    if fmt == "WEBP":
        return {
            "format": "WEBP",
            "quality": quality,
            "method": 6,               # slowest/best search
            "lossless": quality >= 100,
            "exif": b"",
            "icc_profile": None,
            "xmp": b"",
        }
    if fmt == "AVIF":
        return {
            "format": "AVIF",
            "quality": quality,
            "speed": 5,
            "exif": b"",
            "icc_profile": None,
            "xmp": b"",
        }
    if fmt == "PNG":
        return {
            "format": "PNG",
            "optimize": True,
            "compress_level": 9,
            "pnginfo": None,
            "icc_profile": None,
        }
    return {"format": fmt}


def _target_format(src_ext: str, im: Image.Image, choice: str) -> str:
    if choice != "keep":
        return choice.upper()
    ext = src_ext.lower()
    if ext in (".png", ".bmp", ".tga", ".ico"):
        return "PNG" if _has_alpha(im) else "PNG"
    if ext in (".gif",):
        return "GIF"
    if ext in (".webp",):
        return "WEBP"
    if ext in (".avif", ".heic", ".heif"):
        return "AVIF"
    return "JPEG"


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info


_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "AVIF": ".avif", "GIF": ".gif"}


def process(src: str, out_dir: str, opts: dict, log, progress) -> str:
    """Scrub and recompress one image. Returns the output path."""
    quality = int(opts.get("quality", 80))
    max_edge = int(opts.get("max_edge", 0) or 0)
    choice = opts.get("image_format", "keep")

    progress(5)
    im = Image.open(src)
    src_format = im.format or "?"
    found = [k for k in ("exif", "XML:com.adobe.xmp", "icc_profile", "comment", "dpi")
             if k in im.info]
    log(f"{src_format} {im.size[0]}x{im.size[1]} {im.mode}")
    if found:
        log(f"metadata present: {', '.join(found)}")
    else:
        log("no metadata blocks found in container")

    animated = getattr(im, "n_frames", 1) > 1
    progress(15)

    if animated and choice == "keep":
        return _process_animated(im, src, out_dir, quality, max_edge, log, progress)

    im = ImageOps.exif_transpose(im) or im   # bake rotation before we lose it
    im = _to_srgb(im, log)
    im = _fit(im, max_edge, log)

    fmt = _target_format(os.path.splitext(src)[1], im, choice)

    if fmt in ("JPEG",) and _has_alpha(im):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
        log("flattened alpha onto white for JPEG")
    elif fmt == "JPEG" and im.mode not in ("RGB", "L", "CMYK"):
        im = im.convert("RGB")
    elif fmt in ("PNG", "WEBP", "AVIF") and im.mode == "P":
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")

    progress(45)
    clean = _strip(im)
    log("pixel buffer rebuilt; all ancillary chunks discarded")
    progress(60)

    dst = os.path.join(out_dir, "out" + _EXT.get(fmt, ".bin"))
    clean.save(dst, **_save_params(fmt, quality, clean))
    progress(95)
    log(f"encoded {fmt} at quality {quality}")
    return dst


def _process_animated(im, src, out_dir, quality, max_edge, log, progress) -> str:
    """Keep the animation, drop everything around it."""
    fmt = im.format or "GIF"
    log(f"animated: {getattr(im, 'n_frames', '?')} frames, preserving sequence")
    frames = []
    total = getattr(im, "n_frames", 1)
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        f = frame.convert("RGBA")
        if max_edge and max(f.size) > max_edge:
            f.thumbnail((max_edge, max_edge), Image.LANCZOS)
        frames.append(_strip(f))
        progress(15 + int(70 * (i + 1) / max(total, 1)))

    duration = im.info.get("duration", 80)
    loop = im.info.get("loop", 0)
    dst = os.path.join(out_dir, "out" + (".webp" if fmt == "WEBP" else ".gif"))
    if fmt == "WEBP":
        frames[0].save(dst, format="WEBP", save_all=True, append_images=frames[1:],
                       duration=duration, loop=loop, quality=quality, method=6,
                       exif=b"", icc_profile=None, xmp=b"")
    else:
        pal = [f.convert("P", palette=Image.ADAPTIVE, colors=256) for f in frames]
        pal[0].save(dst, format="GIF", save_all=True, append_images=pal[1:],
                    duration=duration, loop=loop, optimize=True, disposal=2)
    log(f"re-encoded animation, timing preserved ({duration}ms/frame)")
    return dst
