"""Lossless metadata removal.

Re-encoding is how you make a file smaller, but it is not the only way to make
one clean, and sometimes it is the wrong one. If a PNG was already squeezed by
a better compressor than Pillow, or a JPEG is already at a lower quality than
the one being asked for, re-encoding hands back something *larger* than it
started -- and for a lossy format, worse as well.

These functions rewrite the container and leave the pixel data byte-for-byte
alone. The result is always smaller than the input, because it only deletes.
The caller runs both routes and keeps whichever is smaller.
"""
from __future__ import annotations

import struct

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Chunks that carry the picture, its palette, or its animation. Everything not
# in here is either metadata or a rendering hint we can live without.
PNG_KEEP = {
    b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND",
    b"acTL", b"fcTL", b"fdAT",          # APNG animation
    b"gAMA", b"cHRM", b"sRGB", b"bKGD",  # colour rendering, no personal content
}
# Named for the log, so the user is told what left rather than just a byte count.
PNG_LABELS = {
    b"tEXt": "text", b"zTXt": "compressed text", b"iTXt": "international text",
    b"eXIf": "EXIF", b"iCCP": "colour profile", b"tIME": "modification time",
    b"pHYs": "pixel density", b"sPLT": "suggested palette", b"hIST": "histogram",
    b"dSIG": "digital signature", b"caNv": "canvas info", b"orNT": "orientation",
}

JPEG_DROP = {
    0xE1: "EXIF/XMP", 0xE2: "colour profile", 0xE3: "meta", 0xEC: "Picture Info",
    0xED: "Photoshop/IPTC", 0xEE: "Adobe", 0xEF: "app-specific",
    0xFE: "comment",
}
JPEG_DROP.update({m: "app-specific" for m in range(0xE4, 0xEC)})


def strip_png(data: bytes) -> tuple[bytes | None, list[str]]:
    """Rebuild a PNG from its critical chunks only."""
    if not data.startswith(PNG_MAGIC):
        return None, []
    out = bytearray(PNG_MAGIC)
    removed: list[str] = []
    pos = len(PNG_MAGIC)
    n = len(data)
    while pos + 8 <= n:
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > n or length > n:
            return None, []                     # truncated or hostile; bail out
        if ctype in PNG_KEEP:
            out += data[pos:end]
        else:
            removed.append(PNG_LABELS.get(ctype, ctype.decode("ascii", "replace")))
        pos = end
        if ctype == b"IEND":
            break
    if not out.endswith(b"IEND\xae\x42\x60\x82") and b"IEND" not in out[-12:]:
        out += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0xAE426082)
    return bytes(out), removed


def strip_jpeg(data: bytes) -> tuple[bytes | None, list[str]]:
    """Rebuild a JPEG without its application and comment segments.

    The entropy-coded scan data is copied verbatim, so the decoded picture is
    bit-identical to the input.
    """
    if not data.startswith(b"\xff\xd8"):
        return None, []
    out = bytearray(b"\xff\xd8")
    removed: list[str] = []
    pos = 2
    n = len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            return None, []                     # not where a marker should be
        marker = data[pos + 1]
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += data[pos:pos + 2]
            pos += 2
            continue
        if marker == 0xD9:                       # EOI
            out += data[pos:pos + 2]
            pos += 2
            break
        (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
        end = pos + 2 + length
        if length < 2 or end > n:
            return None, []
        if marker in JPEG_DROP:
            removed.append(JPEG_DROP[marker])
        else:
            out += data[pos:end]
        pos = end
        if marker == 0xDA:                       # SOS: scan data runs to the end
            out += data[pos:]
            break
    return bytes(out), removed


def strip_gif(data: bytes) -> tuple[bytes | None, list[str]]:
    """Drop comment and application extension blocks from a GIF.

    Graphic-control and plain-text extensions are left alone: the first carries
    frame timing and transparency, so removing it breaks animation.
    """
    if not data.startswith((b"GIF87a", b"GIF89a")):
        return None, []
    out = bytearray(data[:13])
    removed: list[str] = []
    pos = 13
    n = len(data)

    flags = data[10]
    if flags & 0x80:                             # global colour table
        size = 3 * (2 ** ((flags & 0x07) + 1))
        out += data[pos:pos + size]
        pos += size

    def skip_blocks(p: int) -> int:
        while p < n and data[p] != 0:
            p += 1 + data[p]
        return p + 1

    while pos < n:
        marker = data[pos]
        if marker == 0x3B:                       # trailer
            out += b"\x3b"
            break
        if marker == 0x21:                       # extension
            label = data[pos + 1]
            end = skip_blocks(pos + 2)
            if label in (0xFE, 0xFF):            # comment, application
                removed.append("comment" if label == 0xFE else "application block")
            else:
                out += data[pos:end]
            pos = end
            continue
        if marker == 0x2C:                       # image descriptor
            out += data[pos:pos + 10]
            local = data[pos + 9]
            pos += 10
            if local & 0x80:
                size = 3 * (2 ** ((local & 0x07) + 1))
                out += data[pos:pos + size]
                pos += size
            out += data[pos:pos + 1]             # LZW minimum code size
            pos += 1
            end = skip_blocks(pos)
            out += data[pos:end]
            pos = end
            continue
        return None, []                          # unexpected byte; do not guess
    return bytes(out), removed


def strip(path: str) -> tuple[bytes | None, list[str]]:
    """Dispatch on content. Returns (bytes, removed labels) or (None, [])."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, []
    for fn in (strip_png, strip_jpeg, strip_gif):
        result, removed = fn(data)
        if result is not None:
            return result, removed
    return None, []
