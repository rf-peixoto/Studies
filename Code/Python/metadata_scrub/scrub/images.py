"""Image metadata removal and recompression.

Stripping strategy: Pillow carries `im.info` (EXIF, XMP, ICC, PNG text chunks,
GPS, thumbnails) through a normal open/save round trip. So we do not "save
without metadata" -- we rebuild the image from its raw pixel buffer, which
leaves every ancillary chunk behind by construction, then write the new file
with metadata parameters explicitly blanked.

Three things are read *before* the strip, because dropping them silently
corrupts the picture rather than protecting anyone:
  - EXIF orientation, baked into the pixels first, or every phone photo comes
    out rotated.
  - The ICC profile, converted to sRGB first, or wide-gamut photos shift.
  - The palette of an indexed image, which is picture data rather than
    metadata. Without it an indexed GIF or PNG decodes to a flat colour.
"""
from __future__ import annotations

import io
import os

from PIL import Image, ImageCms, ImageOps, ImageSequence

from scrub import lossless
from scrub.similarity import floor_for, ssim

try:  # HEIC/HEIF is what iPhones actually produce.
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - optional dependency
    HEIF_OK = False

# Refuse absurd pixel counts rather than letting a crafted file exhaust memory.
Image.MAX_IMAGE_PIXELS = 400_000_000

_SRGB = ImageCms.createProfile("sRGB")
_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "AVIF": ".avif",
        "GIF": ".gif"}

# Search ladders, ordered from most compressed to least. Each entry is
# (quality, subsampling); subsampling is ignored by formats that have no chroma
# setting. The 4:2:0 -> 4:4:4 step sits near the top so the whole ladder is
# non-decreasing in perceived quality, which is what lets the search bisect it.
LADDERS = {
    "JPEG": [(25, 2), (32, 2), (38, 2), (44, 2), (50, 2), (56, 2), (62, 2),
             (68, 2), (73, 2), (78, 2), (82, 2), (85, 2), (88, 2), (90, 2),
             (92, 2), (90, 0), (93, 0), (95, 0), (97, 0), (99, 0)],
    "WEBP": [(20, 0), (26, 0), (32, 0), (38, 0), (44, 0), (50, 0), (56, 0),
             (62, 0), (68, 0), (73, 0), (78, 0), (83, 0), (87, 0), (91, 0),
             (94, 0), (97, 0), (99, 0)],
    "AVIF": [(20, 0), (26, 0), (32, 0), (38, 0), (44, 0), (50, 0), (56, 0),
             (62, 0), (68, 0), (73, 0), (78, 0), (83, 0), (87, 0), (91, 0),
             (94, 0), (97, 0), (99, 0)],
}
_TUNABLE = set(LADDERS)

# Formats whose pixels already went through a lossy encoder once.
LOSSY_SOURCES = {"JPEG", "MPO", "WEBP", "AVIF", "HEIF", "HEIC"}


def _strip(im: Image.Image) -> Image.Image:
    """Rebuild an image from raw pixels, leaving all ancillary data behind."""
    clean = Image.frombytes(im.mode, im.size, im.tobytes())
    if im.mode in ("P", "PA"):
        # The palette is the picture, not metadata about it. Without this an
        # indexed image comes back as a single flat colour.
        palette = im.getpalette()
        if palette:
            clean.putpalette(palette)
        # Likewise the transparent palette index: it says which pixels are
        # see-through, which is content rather than a note about content.
        if "transparency" in im.info:
            clean.info["transparency"] = im.info["transparency"]
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


def _save_params(fmt: str, quality: int, im: Image.Image,
                 subsampling: int = 2) -> dict:
    """Encoder settings. These are where the actual compression wins live."""
    if fmt == "JPEG":
        return {
            "format": "JPEG",
            "quality": quality,
            "optimize": True,          # second Huffman pass, ~2-5% smaller, free
            "progressive": True,       # smaller above ~10KB and renders sooner
            # 4:2:0 halves the chroma data, which is most of the saving. The
            # search decides when a picture cannot afford it.
            "subsampling": subsampling,
            "exif": b"",
            "icc_profile": None,
        }
    if fmt == "WEBP":
        return {"format": "WEBP", "quality": quality, "method": 6,
                "lossless": quality >= 100, "exif": b"", "icc_profile": None,
                "xmp": b""}
    if fmt == "WEBP_LOSSLESS":
        return {"format": "WEBP", "lossless": True, "quality": 100, "method": 6,
                "exif": b"", "icc_profile": None, "xmp": b""}
    if fmt == "AVIF":
        return {"format": "AVIF", "quality": quality, "speed": 5,
                "exif": b"", "icc_profile": None, "xmp": b""}
    if fmt in ("PNG", "GIF"):
        if fmt == "GIF":
            return {"format": "GIF", "optimize": True}
        params = {"format": "PNG", "optimize": True, "compress_level": 9,
                  "pnginfo": None, "icc_profile": None}
        if im.mode in ("P", "PA") and "transparency" in im.info:
            params["transparency"] = im.info["transparency"]
        return params
    return {"format": fmt}


def _target_format(src_format: str, choice: str) -> str:
    """Decide the output format.

    Keyed on what Pillow detected, never on the filename: uploads are stored
    under generated names with no extension, so an extension-based guess turns
    every PNG and GIF into a JPEG -- flattening transparency and quietly
    changing the format the user asked to keep.
    """
    if choice != "keep":
        return choice.upper()
    fmt = (src_format or "").upper()
    if fmt in ("PNG", "BMP", "TGA", "ICO", "TIFF", "PPM"):
        return "PNG"
    if fmt == "GIF":
        return "GIF"
    if fmt == "WEBP":
        return "WEBP"
    if fmt in ("AVIF", "HEIF", "HEIC"):
        return "AVIF"
    return "JPEG"


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info


def _encode(im: Image.Image, fmt: str, quality: int, subsampling: int = 2) -> bytes:
    buf = io.BytesIO()
    im.save(buf, **_save_params(fmt, quality, im, subsampling))
    return buf.getvalue()


def _decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def search_encode(im: Image.Image, fmt: str, floor: float, log) -> bytes:
    """Find the most compressed setting that still looks as good as asked.

    The ladder runs from heavily compressed to barely compressed and is
    non-decreasing in similarity, so this is a plain bisection for the leftmost
    entry that clears the floor -- four or five encodes rather than fourteen.
    """
    ladder = LADDERS[fmt]
    lo, hi = 0, len(ladder) - 1
    best: tuple[bytes, float, tuple[int, int]] | None = None
    tried = 0

    while lo <= hi:
        mid = (lo + hi) // 2
        quality, sub = ladder[mid]
        data = _encode(im, fmt, quality, sub)
        tried += 1
        try:
            score = ssim(im, _decode(data))
        except Exception:
            score = 1.0
        if score >= floor:
            best = (data, score, ladder[mid])
            hi = mid - 1
        else:
            lo = mid + 1

    if best is None:
        quality, sub = ladder[-1]
        data = _encode(im, fmt, quality, sub)
        try:
            score = ssim(im, _decode(data))
        except Exception:
            score = 0.0
        log(f"even the highest setting only reaches {score:.4f} similarity; "
            f"used it anyway")
        return data

    data, score, (quality, sub) = best
    chroma = "4:4:4" if sub == 0 else "4:2:0"
    detail = f"quality {quality}" + (f", {chroma}" if fmt == "JPEG" else "")
    log(f"searched {tried} settings; {detail} gives {score:.4f} similarity "
        f"against a floor of {floor:.3f} -- {len(data) // 1024} KB")
    return data


def process(src: str, out_dir: str, opts: dict, log, progress) -> str:
    """Scrub and recompress one image. Returns the output path."""
    level = opts.get("level", "balanced")
    floor = floor_for(level)
    max_edge = int(opts.get("max_edge", 0) or 0)
    choice = opts.get("image_format", "keep")

    progress(5)
    im = Image.open(src)
    src_format = im.format or "?"
    found = [k for k in ("exif", "XML:com.adobe.xmp", "icc_profile", "comment")
             if k in im.info]
    log(f"{src_format} {im.size[0]}x{im.size[1]} {im.mode}")
    log(f"metadata present: {', '.join(found)}" if found
        else "no metadata blocks found in container")

    animated = getattr(im, "n_frames", 1) > 1
    progress(15)

    if animated and choice == "keep":
        return _process_animated(im, out_dir, level, max_edge, log, progress)

    before_size = im.size
    im = ImageOps.exif_transpose(im) or im   # bake rotation before we lose it
    im = _to_srgb(im, log)
    im = _fit(im, max_edge, log)
    resized = im.size != before_size

    fmt = _target_format(src_format, choice)

    if fmt == "JPEG" and _has_alpha(im):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
        log("flattened alpha onto white for JPEG")
    elif fmt == "JPEG" and im.mode not in ("RGB", "L", "CMYK"):
        im = im.convert("RGB")
    elif fmt in ("WEBP", "AVIF") and im.mode == "P":
        # PNG is deliberately absent here: it stores palettes natively, and
        # expanding an indexed screenshot to 24-bit RGB multiplies its size.
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")

    progress(45)
    clean = _strip(im)
    log("pixel buffer rebuilt; all ancillary chunks discarded")
    progress(60)

    if floor is None and fmt in _TUNABLE:
        if (src_format or "").upper() in LOSSY_SOURCES and choice == "keep":
            # The pixels are already the result of lossy compression. Re-encoding
            # them "losslessly" into PNG preserves the compression artefacts at
            # enormous cost -- the honest lossless answer is to leave the image
            # data alone and clean only the container.
            dst = os.path.join(out_dir, "out" + _EXT.get(fmt, ".bin"))
            data, removed = lossless.strip(src)
            if data is not None:
                with open(dst, "wb") as fh:
                    fh.write(data)
                log("lossless: image data left untouched, "
                    + (f"removed {', '.join(sorted(set(removed)))}" if removed
                       else "no metadata blocks were present"))
                progress(95)
                return dst
            log("lossless requested but this container cannot be edited in "
                "place; re-encoding at the highest setting")
            quality, sub = LADDERS[fmt][-1]
            with open(dst, "wb") as fh:
                fh.write(_encode(clean, fmt, quality, sub))
            progress(95)
            return dst
        fmt = "WEBP_LOSSLESS" if fmt in ("WEBP", "AVIF") else "PNG"
        log(f"lossless requested -- writing {fmt.split('_')[0]} instead")

    dst = os.path.join(out_dir, "out" + _EXT.get(fmt.split("_")[0], ".bin"))
    if fmt in _TUNABLE:
        data = search_encode(clean, fmt, floor, log)
        with open(dst, "wb") as fh:
            fh.write(data)
    else:
        clean.save(dst, **_save_params(fmt, 100, clean))
        log(f"{fmt.split('_')[0]} is lossless; nothing to trade away")

    _keep_the_smaller(src, dst, src_format, fmt.split("_")[0], resized, log)
    _suggest_format(clean, fmt, os.path.getsize(dst), log)
    progress(95)
    return dst


def _suggest_format(im: Image.Image, fmt: str, size: int, log) -> None:
    """Say something when lossless is the wrong container for the content.

    A photograph stored as PNG cannot be made much smaller without changing
    format, so reporting 0% and stopping is accurate but useless.
    """
    if fmt != "PNG" or size < 400_000 or im.mode in ("P", "PA", "1", "L"):
        return   # an indexed or greyscale image is never the photographic case
    try:
        # Nearest-neighbour, so the sample keeps the real palette instead of
        # inventing blended colours that skew the count either way.
        sample = im.convert("RGB").resize((64, 64), Image.NEAREST)
        found = sample.getcolors(maxcolors=4096)
        colours = 4096 if found is None else len(found)
    except Exception:
        return
    if colours > 1200:      # photographic rather than flat-shaded
        log("this looks like a photograph stored losslessly -- PNG cannot "
            "compress it much further; switching the format to JPEG or WebP "
            "would typically cut it by 80-95%")


def _keep_the_smaller(src: str, dst: str, src_format: str, out_format: str,
                      resized: bool, log) -> None:
    """Fall back to lossless stripping when re-encoding did not pay off.

    Only when the format is unchanged and the pixels were not resized -- in any
    other case the user asked for a conversion and the original bytes are not a
    valid answer to that.
    """
    if resized or (src_format or "").upper() != out_format.upper():
        return
    encoded = os.path.getsize(dst)
    original = os.path.getsize(src)

    data, removed = lossless.strip(src)
    if data is None:
        if encoded > original:
            log(f"re-encoding made this larger ({original // 1024} KB -> "
                f"{encoded // 1024} KB) and this format has no lossless route")
        return

    if len(data) >= encoded:
        return

    with open(dst, "wb") as fh:
        fh.write(data)
    log(f"re-encoding would have produced {encoded // 1024} KB, more than the "
        f"{len(data) // 1024} KB this file needs")
    log("stripped losslessly instead: pixel data untouched, "
        + (f"removed {', '.join(sorted(set(removed)))}" if removed
           else "no metadata blocks were present"))


def _process_animated(im, out_dir, level, max_edge, log, progress) -> str:
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
        frames[0].save(dst, format="WEBP", save_all=True,
                       append_images=frames[1:], duration=duration, loop=loop,
                       quality=quality, method=6, exif=b"", icc_profile=None,
                       xmp=b"")
    else:
        pal = [f.convert("P", palette=Image.ADAPTIVE, colors=256) for f in frames]
        pal[0].save(dst, format="GIF", save_all=True, append_images=pal[1:],
                    duration=duration, loop=loop, optimize=True, disposal=2)
    log(f"re-encoded animation, timing preserved ({duration}ms/frame)")
    return dst
