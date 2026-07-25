"""Read-only inspection: what is actually hiding in this file?

Nothing here writes. The point is to show the user the GPS coordinates, the
device model and the author name *before* anything is stripped, so the tool is
something you can check rather than something you have to trust.

Findings carry a severity, which is about what the data reveals rather than how
technically interesting it is:

    high    identifies a person or a place -- GPS, names, serial numbers
    medium  identifies equipment or timing -- device model, software, timestamps
    active  executes or carries payload -- JavaScript, auto-actions, attachments
    low     technical residue with no personal content -- density, profiles
"""
from __future__ import annotations

import os
import re

HIGH, MEDIUM, ACTIVE, LOW = "high", "medium", "active", "low"

# EXIF tags worth naming explicitly, in the order a person would care about.
_EXIF_PERSONAL = {
    "Artist": HIGH, "Copyright": HIGH, "CameraOwnerName": HIGH,
    "BodySerialNumber": HIGH, "SerialNumber": HIGH, "ImageDescription": HIGH,
    "UserComment": HIGH, "XPAuthor": HIGH, "XPComment": HIGH, "XPTitle": HIGH,
    "XPSubject": HIGH, "XPKeywords": HIGH, "HostComputer": MEDIUM,
    "Make": MEDIUM, "Model": MEDIUM, "Software": MEDIUM, "LensModel": MEDIUM,
    "LensMake": MEDIUM, "DateTime": MEDIUM, "DateTimeOriginal": MEDIUM,
    "DateTimeDigitized": MEDIUM,
}

# QuickTime/MP4 keys that phones write. These are the ones that matter.
_AV_PERSONAL = {
    "location": HIGH, "location-eng": HIGH,
    "com.apple.quicktime.location.ISO6709": HIGH,
    "com.apple.quicktime.make": MEDIUM,
    "com.apple.quicktime.model": MEDIUM,
    "com.apple.quicktime.software": MEDIUM,
    "com.apple.quicktime.creationdate": MEDIUM,
    "artist": HIGH, "author": HIGH, "album_artist": HIGH, "composer": HIGH,
    "copyright": HIGH, "comment": HIGH, "description": HIGH, "title": HIGH,
    "album": MEDIUM, "date": MEDIUM, "creation_time": MEDIUM,
    "encoder": LOW, "handler_name": LOW, "language": LOW,
    "major_brand": LOW, "minor_version": LOW, "compatible_brands": LOW,
}

_PDF_INFO = {
    "/Author": HIGH, "/Title": HIGH, "/Subject": HIGH, "/Keywords": MEDIUM,
    "/Creator": MEDIUM, "/Producer": MEDIUM, "/CreationDate": MEDIUM,
    "/ModDate": MEDIUM, "/Company": HIGH, "/SourceModified": MEDIUM,
}

_IGNORE_INFO_KEYS = {"jfif", "jfif_version", "jfif_unit", "adobe", "adobe_transform"}


def _clean(value, limit: int = 160) -> str:
    """Make an arbitrary metadata value printable."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
        # EXIF UserComment is prefixed with an 8-byte character-set marker.
        value = re.sub(r"^(ASCII|UNICODE|JIS)\x00*", "", value)
        value = value.replace("\x00", "")
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit] + ("…" if len(text) > limit else "")


_NS = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/": "exif",
}


def _short_ns(key: str) -> str:
    """Turn {http://purl.org/dc/elements/1.1/}creator into dc:creator."""
    match = re.match(r"^\{([^}]+)\}(.+)$", str(key))
    if not match:
        return str(key)
    uri, name = match.groups()
    return f"{_NS.get(uri, uri.rstrip('/').rsplit('/', 1)[-1])}:{name}"


def _finding(label, value, severity, note="") -> dict:
    return {"label": label, "value": _clean(value), "severity": severity,
            "note": note}


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------

def _gps_decimal(coord, ref) -> float | None:
    """EXIF stores GPS as degrees/minutes/seconds rationals plus a hemisphere."""
    try:
        d, m, s = [float(x) for x in coord]
    except (TypeError, ValueError):
        return None
    value = d + m / 60.0 + s / 3600.0
    if str(ref).upper() in ("S", "W"):
        value = -value
    return round(value, 6)


def inspect_image(path: str) -> list[dict]:
    from PIL import ExifTags, Image

    out: list[dict] = []
    with Image.open(path) as im:
        out.append(_finding("format",
                            f"{im.format} {im.size[0]}×{im.size[1]} {im.mode}",
                            LOW))

        try:
            exif = im.getexif()
        except Exception:
            exif = {}

        if exif:
            names = {v: k for k, v in ExifTags.TAGS.items()}
            merged = dict(exif)
            for ifd_tag in (0x8769, 0xA005):     # Exif IFD, Interop IFD
                try:
                    merged.update(exif.get_ifd(ifd_tag))
                except Exception:
                    pass

            for name, severity in _EXIF_PERSONAL.items():
                tag = names.get(name)
                if tag is None or tag not in merged:
                    continue
                value = merged[tag]
                if value in (None, "", b""):
                    continue
                out.append(_finding(name, value, severity))

            if 0x0112 in merged and merged[0x0112] not in (0, 1):
                out.append(_finding("Orientation", merged[0x0112], LOW,
                                    "rotation is applied to the pixels, then removed"))

            # GPS lives in its own IFD.
            try:
                gps = exif.get_ifd(0x8825)
            except Exception:
                gps = {}
            if gps:
                lat = _gps_decimal(gps.get(2), gps.get(1))
                lon = _gps_decimal(gps.get(4), gps.get(3))
                if lat is not None and lon is not None:
                    out.append(_finding("GPS position", f"{lat}, {lon}", HIGH,
                                        "the exact place this was taken"))
                else:
                    out.append(_finding("GPS data", f"{len(gps)} field(s)", HIGH))
                if 6 in gps:
                    try:
                        out.append(_finding("GPS altitude",
                                            f"{float(gps[6]):.0f} m", HIGH))
                    except Exception:
                        pass

            other = len(merged) - sum(1 for f in out if f["severity"] != LOW)
            if other > 0:
                out.append(_finding("other EXIF tags", f"{other} more", LOW))

        if im.info.get("XML:com.adobe.xmp") or im.info.get("xmp"):
            raw = im.info.get("XML:com.adobe.xmp") or im.info.get("xmp")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            creators = re.findall(r"<dc:creator>.*?<rdf:li[^>]*>(.*?)</rdf:li>",
                                  raw, re.S)
            out.append(_finding("XMP packet", f"{len(raw)} bytes", HIGH,
                                f"names {creators[0]}" if creators else
                                "editor metadata, often survives other tools"))

        if im.info.get("icc_profile"):
            out.append(_finding("colour profile",
                                f"{len(im.info['icc_profile'])} bytes", LOW,
                                "converted to sRGB, then removed"))

        for key, value in im.info.items():
            if key in _IGNORE_INFO_KEYS or key in ("exif", "icc_profile",
                                                   "XML:com.adobe.xmp", "xmp"):
                continue
            if isinstance(value, str) and value.strip():
                out.append(_finding(f"text chunk: {key}", value, MEDIUM))

        try:
            if getattr(im, "n_frames", 1) > 1:
                out.append(_finding("frames", im.n_frames, LOW,
                                    "animation is preserved"))
        except Exception:
            pass

    return out


# --------------------------------------------------------------------------
# audio and video
# --------------------------------------------------------------------------

def inspect_av(path: str) -> list[dict]:
    import av
    import av.stream

    out: list[dict] = []
    with av.open(path) as container:
        seen: set[str] = set()

        for key, value in container.metadata.items():
            if not str(value).strip():
                continue
            severity = _AV_PERSONAL.get(key.lower(), MEDIUM)
            out.append(_finding(key, value, severity))
            seen.add(key.lower())

        for stream in container.streams:
            if stream.type == "video" and \
                    (stream.disposition & av.stream.Disposition.attached_pic):
                out.append(_finding("cover art", "1 embedded image", MEDIUM,
                                    "artwork can carry its own EXIF"))
                continue

            codec = stream.codec_context.name
            if stream.type == "video":
                out.append(_finding(
                    "video stream",
                    f"{codec} {stream.codec_context.width}×"
                    f"{stream.codec_context.height}", LOW))
                if codec in ("h264", "hevc"):
                    out.append(_finding("encoder banner", f"likely, {codec}", MEDIUM,
                                        "x264/x265 write a build string inside "
                                        "the bitstream itself"))
                rot = _rotation(stream)
                if rot:
                    out.append(_finding("display rotation", f"{rot}°", LOW,
                                        "applied to the pixels, then removed"))
            elif stream.type == "audio":
                ctx = stream.codec_context
                out.append(_finding(
                    "audio stream",
                    f"{codec} {ctx.sample_rate} Hz "
                    f"{getattr(ctx, 'channels', '?')} ch", LOW))

            for key, value in stream.metadata.items():
                if not str(value).strip() or key.lower() in seen:
                    continue
                severity = _AV_PERSONAL.get(key.lower(), MEDIUM)
                out.append(_finding(f"{stream.type}: {key}", value, severity))

        if container.duration:
            out.append(_finding("duration",
                                f"{container.duration / av.time_base:.1f} s", LOW))
    return out


def _rotation(stream) -> int:
    try:
        rot = stream.metadata.get("rotate")
        if rot:
            return int(float(rot)) % 360
    except Exception:
        pass
    try:
        for side in stream.side_data:
            if "DISPLAYMATRIX" in str(side.type):
                return int(round(float(side.rotation))) % 360
    except Exception:
        pass
    return 0


# --------------------------------------------------------------------------
# pdf
# --------------------------------------------------------------------------

def inspect_pdf(path: str, password: str = "") -> list[dict]:
    import pikepdf

    out: list[dict] = []
    try:
        pdf = pikepdf.open(path, password=password)
    except pikepdf.PasswordError:
        return [_finding("encrypted", "needs a password to inspect", MEDIUM,
                         "enter the source password in the PDF settings")]

    with pdf:
        out.append(_finding("document",
                            f"{len(pdf.pages)} page(s), PDF {pdf.pdf_version}", LOW))
        if pdf.is_encrypted:
            out.append(_finding("encrypted", "yes", LOW))

        try:
            for key, value in pdf.docinfo.items():
                text = _clean(value)
                if not text:
                    continue
                out.append(_finding(str(key).lstrip("/"), text,
                                    _PDF_INFO.get(str(key), MEDIUM)))
        except Exception:
            pass

        try:
            with pdf.open_metadata(set_pikepdf_as_editor=False,
                                   update_docinfo=False) as meta:
                keys = list(meta.keys())
                for key in keys[:12]:
                    try:
                        value = meta[key]
                        if isinstance(value, (list, tuple)):
                            value = ", ".join(str(v) for v in value)
                        out.append(_finding(_short_ns(key), value, HIGH))
                    except Exception:
                        pass
                if len(keys) > 12:
                    out.append(_finding("XMP", f"{len(keys) - 12} more properties",
                                        MEDIUM))
        except Exception:
            pass

        names = pdf.Root.get("/Names")
        if names is not None:
            if "/JavaScript" in names:
                out.append(_finding("JavaScript", "embedded in the document",
                                    ACTIVE, "runs when the file is opened"))
            if "/EmbeddedFiles" in names:
                out.append(_finding("attachments", "embedded file(s)", ACTIVE,
                                    "travel invisibly inside the document"))
        if "/OpenAction" in pdf.Root:
            action = pdf.Root["/OpenAction"]
            if isinstance(action, pikepdf.Dictionary) and \
                    action.get("/S") == "/JavaScript":
                out.append(_finding("auto-run script", "on open", ACTIVE))
        if "/AA" in pdf.Root:
            out.append(_finding("additional actions", "document level", ACTIVE))

        page_meta = 0
        attach_annots = 0
        for page in pdf.pages:
            obj = page.obj
            page_meta += sum(1 for k in ("/Metadata", "/PieceInfo", "/LastModified")
                             if k in obj)
            for annot in (obj.get("/Annots") or []):
                try:
                    if annot.get("/Subtype") == "/FileAttachment" or "/EF" in annot:
                        attach_annots += 1
                except Exception:
                    pass
        if page_meta:
            out.append(_finding("page-level metadata", f"{page_meta} entries",
                                MEDIUM, "editor scratch data, per page"))
        if attach_annots:
            out.append(_finding("attachment annotations", attach_annots, ACTIVE))

        images = 0
        pixels = 0
        for page in pdf.pages:
            try:
                for raw in page.images.values():
                    images += 1
                    pixels += int(raw.get("/Width", 0)) * int(raw.get("/Height", 0))
            except Exception:
                pass
        if images:
            out.append(_finding("embedded images",
                                f"{images}, {pixels / 1e6:.1f} megapixels total", LOW,
                                "usually where the file size is"))
    return out


# --------------------------------------------------------------------------

def inspect(path: str, kind: str, password: str = "") -> dict:
    """Return {findings, counts} for one file. Never raises."""
    try:
        if kind == "image":
            findings = inspect_image(path)
        elif kind in ("audio", "video"):
            findings = inspect_av(path)
        elif kind == "pdf":
            findings = inspect_pdf(path, password)
        else:
            findings = []
    except Exception as exc:
        findings = [_finding("inspection failed", f"{type(exc).__name__}: {exc}",
                             LOW)]

    counts = {level: sum(1 for f in findings if f["severity"] == level)
              for level in (HIGH, MEDIUM, ACTIVE, LOW)}
    return {"findings": findings, "counts": counts,
            "size": os.path.getsize(path) if os.path.exists(path) else 0}
