#!/usr/bin/env python3
"""
watermark_check.py

Usage:
  python watermark_check.py /path/to/image.jpg \
    --templates ./templates \
    --ocr \
    --min-score 0.78

What it does:
  1) Checks for C2PA/Content Credentials metadata and other provenance-like fields.
  2) Scans for metadata strings that often appear in AI-generated images.
  3) Optionally runs visible watermark detection:
     - Template matching (logo templates you provide)
     - OCR for text watermarks (requires pytesseract + system tesseract)

Notes:
  - Most social platforms strip metadata; absence of metadata is NOT evidence of no watermark.
  - Invisible watermark detection is vendor-specific; this script cannot reliably detect those without
    the corresponding detector/key.

pip install pillow opencv-python pytesseract
# Also install system tesseract (package name varies by OS)
python watermark_check.py image.jpg --templates ./templates --ocr

"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

# ----------------------------
# Data structures
# ----------------------------

@dataclass
class Finding:
    kind: str
    confidence: float
    details: str

# ----------------------------
# Metadata helpers
# ----------------------------

def _pil_get_exif(image: Image.Image) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        exif = image.getexif()
        if not exif:
            return out
        tagmap = {v: k for k, v in ExifTags.TAGS.items()}
        for tag_id, value in exif.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            # Avoid huge blobs
            s = str(value)
            if len(s) > 4096:
                s = s[:4096] + "…(truncated)"
            out[name] = s
    except Exception:
        return out
    return out


def _pil_get_xmp_bytes(image_path: str) -> Optional[bytes]:
    """
    XMP is often embedded as a packet in JPEG/PNG as raw bytes.
    PIL does not robustly expose it, so we do a shallow binary scan.

    This is heuristic but works often enough for forensic triage.
    """
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        # XMP packets are usually inside <x:xmpmeta ...> ... </x:xmpmeta>
        m = re.search(rb"<x:xmpmeta\b.*?</x:xmpmeta>", data, re.DOTALL)
        if m:
            return m.group(0)
    except Exception:
        pass
    return None


def _extract_c2pa_like(image_path: str) -> List[Finding]:
    """
    Heuristic detection of C2PA / Content Credentials manifests.

    C2PA can be stored in various ways depending on container and tooling.
    Without a full C2PA parser, we do robust string/marker scans.

    This yields "likely present" signals; it is not a full verification.
    """
    findings: List[Finding] = []
    try:
        with open(image_path, "rb") as f:
            data = f.read()

        # Common markers seen in files with C2PA / CAI related structures
        markers = [
            b"c2pa", b"C2PA", b"contentcredentials", b"ContentCredentials",
            b"urn:ietf:params:xml:ns:c2pa", b"com.adobe.xmp",
            b"manifest", b"assertion", b"provenance",
        ]
        hits = [m for m in markers if m in data]
        if hits:
            findings.append(Finding(
                kind="provenance:c2pa_candidate",
                confidence=min(0.95, 0.55 + 0.05 * len(hits)),
                details=f"Binary markers suggest possible C2PA/CAI data present (hits={len(hits)})."
            ))
    except Exception as e:
        findings.append(Finding(
            kind="error:read_binary",
            confidence=0.2,
            details=f"Failed to read file bytes for provenance scan: {e}"
        ))
    return findings


def _metadata_string_hints(exif: Dict[str, str], xmp_bytes: Optional[bytes]) -> List[Finding]:
    """
    Looks for strings that often appear in generated images.
    These are not definitive; they are hints.
    """
    findings: List[Finding] = []
    hay = " ".join([f"{k}={v}" for k, v in exif.items()])
    if xmp_bytes:
        try:
            hay += " " + xmp_bytes.decode("utf-8", errors="ignore")
        except Exception:
            pass

    # Add/adjust tokens as needed for your environment
    tokens = [
        ("OpenAI", "metadata:token"),
        ("DALL", "metadata:token"),
        ("Stable Diffusion", "metadata:token"),
        ("Midjourney", "metadata:token"),
        ("Adobe Firefly", "metadata:token"),
        ("ComfyUI", "metadata:token"),
        ("AUTOMATIC1111", "metadata:token"),
        ("InvokeAI", "metadata:token"),
        ("SDXL", "metadata:token"),
        ("negative prompt", "metadata:token"),
        ("seed", "metadata:token"),
        ("sampler", "metadata:token"),
        ("Steps:", "metadata:token"),
    ]

    for t, kind in tokens:
        if t.lower() in hay.lower():
            findings.append(Finding(
                kind=kind,
                confidence=0.65,
                details=f"Found metadata hint token: '{t}'."
            ))

    # "Software" EXIF tag is sometimes populated
    if "Software" in exif and exif["Software"].strip():
        findings.append(Finding(
            kind="metadata:software",
            confidence=0.55,
            details=f"EXIF Software: {exif['Software']}"
        ))

    return findings


# ----------------------------
# Visible watermark detection
# ----------------------------

def _load_templates(templates_dir: str) -> List[Tuple[str, np.ndarray]]:
    templates: List[Tuple[str, np.ndarray]] = []
    if not templates_dir:
        return templates
    if not os.path.isdir(templates_dir):
        raise FileNotFoundError(f"Templates directory not found: {templates_dir}")

    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    for fn in sorted(os.listdir(templates_dir)):
        if fn.lower().endswith(exts):
            path = os.path.join(templates_dir, fn)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            templates.append((fn, img))
    return templates


def _template_match(gray: np.ndarray, templates: List[Tuple[str, np.ndarray]], min_score: float) -> List[Finding]:
    """
    Naive template matching. Works best when:
      - watermark is visible
      - size/aspect are similar to template
      - watermark is not heavily distorted

    For robustness, you may add multi-scale matching (slower).
    """
    findings: List[Finding] = []
    for name, templ in templates:
        if templ.shape[0] > gray.shape[0] or templ.shape[1] > gray.shape[1]:
            continue
        res = cv2.matchTemplate(gray, templ, cv2.TM_CCOEFF_NORMED)
        minv, maxv, minloc, maxloc = cv2.minMaxLoc(res)
        if maxv >= min_score:
            findings.append(Finding(
                kind="visible:template_match",
                confidence=float(maxv),
                details=f"Template '{name}' matched with score={maxv:.3f} at location={maxloc}."
            ))
    return findings


def _ocr_text_watermark(bgr: np.ndarray) -> List[Finding]:
    """
    OCR-based detection of text overlays.
    Requires:
      pip install pytesseract
    And system tesseract installed.

    This is heuristic: OCR errors are common.
    """
    findings: List[Finding] = []
    try:
        import pytesseract  # type: ignore
    except Exception:
        findings.append(Finding(
            kind="warning:ocr_unavailable",
            confidence=0.4,
            details="OCR requested but pytesseract is not installed. Install with: pip install pytesseract"
        ))
        return findings

    # Preprocess for OCR: grayscale + threshold
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 3)

    text = pytesseract.image_to_string(thr)
    text_norm = re.sub(r"\s+", " ", text).strip()

    if text_norm:
        # Heuristic: if watermark-like keywords exist, increase confidence
        keywords = ["watermark", "sample", "preview", "generated", "ai", "midjourney", "stable", "openai"]
        hit = any(k in text_norm.lower() for k in keywords)
        findings.append(Finding(
            kind="visible:ocr_text",
            confidence=0.75 if hit else 0.55,
            details=f"OCR extracted text (truncated): {text_norm[:200]}{'…' if len(text_norm)>200 else ''}"
        ))
    else:
        findings.append(Finding(
            kind="visible:ocr_text",
            confidence=0.25,
            details="OCR did not extract any text."
        ))

    return findings


# ----------------------------
# Main analysis
# ----------------------------

def analyze_image(path: str, templates_dir: Optional[str], do_ocr: bool, min_score: float) -> List[Finding]:
    findings: List[Finding] = []

    # Load with PIL for EXIF
    try:
        pil_img = Image.open(path)
    except Exception as e:
        return [Finding(kind="error:open", confidence=0.1, details=f"Failed to open image: {e}")]

    exif = _pil_get_exif(pil_img)
    xmp = _pil_get_xmp_bytes(path)

    # Provenance and metadata
    findings.extend(_extract_c2pa_like(path))
    findings.extend(_metadata_string_hints(exif, xmp))

    # Visible watermark checks using OpenCV
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        findings.append(Finding(kind="error:cv2_read", confidence=0.2, details="OpenCV failed to read the image."))
        return findings

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Template matching
    if templates_dir:
        try:
            templates = _load_templates(templates_dir)
            if not templates:
                findings.append(Finding(
                    kind="warning:no_templates",
                    confidence=0.35,
                    details=f"No templates found in: {templates_dir}"
                ))
            else:
                findings.extend(_template_match(gray, templates, min_score))
        except Exception as e:
            findings.append(Finding(kind="error:templates", confidence=0.2, details=f"Template load/match failed: {e}"))

    # OCR
    if do_ocr:
        findings.extend(_ocr_text_watermark(bgr))

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Check an image for known/probable watermark/provenance indicators.")
    ap.add_argument("image", help="Path to image file (jpg/png/webp/...)")
    ap.add_argument("--templates", default=None, help="Directory with watermark/logo template images for matching.")
    ap.add_argument("--ocr", action="store_true", help="Run OCR to detect text watermarks (requires pytesseract).")
    ap.add_argument("--min-score", type=float, default=0.78, help="Min template match score (0..1). Default: 0.78")
    ap.add_argument("--json", action="store_true", help="Output findings as JSON.")
    args = ap.parse_args()

    findings = analyze_image(args.image, args.templates, args.ocr, args.min_score)

    # Sort: highest confidence first
    findings.sort(key=lambda f: f.confidence, reverse=True)

    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        print(f"File: {args.image}")
        print("=" * 72)
        if not findings:
            print("No findings.")
            return 0
        for f in findings:
            print(f"[{f.confidence:0.2f}] {f.kind}: {f.details}")

        print("\nNotes:")
        print("- Missing metadata is not proof of no watermark; platforms often strip it.")
        print("- Invisible watermark detection is generally vendor-specific and not reliably detectable here.")
        print("- Template matching only works if you provide suitable watermark/logo templates.")

    # Return non-zero if something likely found
    likely = any(f.confidence >= 0.75 and not f.kind.startswith("warning") and not f.kind.startswith("error") for f in findings)
    return 1 if likely else 0


if __name__ == "__main__":
    raise SystemExit(main())
