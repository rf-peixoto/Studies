"""File classification.

Extension is a hint, never a decision. Every file is opened by the library that
claims it before we act on it, so a .jpg that is really a video (or really a zip)
gets classified by content, not by what the uploader named it.
"""
from __future__ import annotations

import os

IMAGE_EXT = {
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".bmp", ".tif", ".tiff",
    ".webp", ".avif", ".heic", ".heif", ".ppm", ".pgm", ".tga", ".ico",
}
VIDEO_EXT = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".flv",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv",
}
AUDIO_EXT = {
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus",
    ".wma", ".aiff", ".aif", ".alac", ".ape", ".mka",
}
PDF_EXT = {".pdf"}

ALL_EXT = IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | PDF_EXT

# Magic numbers we can settle without opening a decoder.
_SIGNATURES = [
    (b"%PDF-", "pdf"),
    (b"\xff\xd8\xff", "image"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"BM", "image"),
    (b"II\x2a\x00", "image"),      # little-endian TIFF
    (b"MM\x00\x2a", "image"),      # big-endian TIFF
]


def sniff(path: str) -> str:
    """Return one of: image, video, audio, pdf, unknown."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return "unknown"

    for sig, kind in _SIGNATURES:
        if head.startswith(sig):
            return kind

    if head[4:12] in (b"ftypavif", b"ftypavis") or head[4:8] == b"ftyp" and head[8:12] in (
        b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis",
    ):
        return "image"

    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio"

    # Containers need a real probe to tell audio-only from audio+video.
    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT or ext in AUDIO_EXT:
        return probe_av(path, ext)
    return probe_av(path, ext)


def probe_av(path: str, ext: str = "") -> str:
    """Open with PyAV and decide audio vs video by what streams exist."""
    try:
        import av
        import av.stream
    except ImportError:
        return "video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else "unknown"

    try:
        with av.open(path) as container:
            has_video = False
            has_audio = False
            for stream in container.streams:
                if stream.type == "audio":
                    has_audio = True
                elif stream.type == "video":
                    # Embedded cover art is a single-frame video stream. It is
                    # artwork attached to an audio file, not a video track.
                    attached = bool(stream.disposition & av.stream.Disposition.attached_pic)
                    if not attached:
                        has_video = True
            if has_video:
                return "video"
            if has_audio:
                return "audio"
    except Exception:
        pass
    return "unknown"


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"
