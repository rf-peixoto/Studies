"""
OCR + Logo Detection API  — v3.0.0
────────────────────────────────────────────────────────────────────────────────
Features
  • OCR  : extract text from JPG / JPEG / PNG images (single or batch)
  • Logos: register reference logos, auto-compute & cache ORB + SIFT descriptors
  • Detect with ORB  → POST /logos/detect/orb   (fast, patent-free)
  • Detect with SIFT → POST /logos/detect/sift  (slower, more accurate)

Descriptor caching
  At registration time both ORB and SIFT descriptors are computed once and
  saved as .npy files inside logo_store/.  Detection calls load these files
  directly — no re-extraction ever happens, so detection speed stays constant
  regardless of how large your logo library grows.
────────────────────────────────────────────────────────────────────────────────
"""

import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Storage paths ──────────────────────────────────────────────────────────────
LOGO_STORE_DIR  = Path("logo_store")
LOGO_INDEX_FILE = LOGO_STORE_DIR / "index.json"
LOGO_STORE_DIR.mkdir(exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OCR + Logo Detection API",
    description=__doc__,
    version="3.0.0",
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS    = {".jpg", ".jpeg", ".png"}

# ── Matching tuning ────────────────────────────────────────────────────────────
ORB_MIN_MATCHES  = 15     # good-match floor for ORB
SIFT_MIN_MATCHES = 10     # SIFT produces fewer but higher-quality matches
LOWE_RATIO       = 0.75   # Lowe's ratio-test threshold


# ══════════════════════════════════════════════════════════════════════════════
# Feature engines
# ══════════════════════════════════════════════════════════════════════════════

# ORB — fast, patent-free, binary descriptors → Hamming distance
_orb    = cv2.ORB_create(nfeatures=1000)
_bf_orb = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

# SIFT — slower, float descriptors, superior scale/rotation invariance → L2
_sift    = cv2.SIFT_create()
_bf_sift = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)


def _bytes_to_gray(image_bytes: bytes) -> np.ndarray:
    """Decode raw image bytes to a grayscale OpenCV array."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _extract_orb(gray: np.ndarray) -> np.ndarray | None:
    """Return ORB descriptors (uint8) or None if no keypoints found."""
    _, des = _orb.detectAndCompute(gray, None)
    return des


def _extract_sift(gray: np.ndarray) -> np.ndarray | None:
    """Return SIFT descriptors (float32) or None if no keypoints found."""
    _, des = _sift.detectAndCompute(gray, None)
    return des


def _good_matches(des_query: np.ndarray, des_ref: np.ndarray, matcher) -> int:
    """
    Apply kNN matching + Lowe's ratio test.
    Returns the count of good matches, or 0 on failure.
    """
    if des_query is None or des_ref is None:
        return 0
    if len(des_query) < 2 or len(des_ref) < 2:
        return 0

    matches = matcher.knnMatch(des_ref, des_query, k=2)
    good = [
        m for pair in matches
        if len(pair) == 2
        for m, n in [pair]
        if m.distance < LOWE_RATIO * n.distance
    ]
    return len(good)


# ══════════════════════════════════════════════════════════════════════════════
# Descriptor cache  (disk-backed .npy files)
# ══════════════════════════════════════════════════════════════════════════════

def _cache_path(logo_id: str, engine: Literal["orb", "sift"]) -> Path:
    return LOGO_STORE_DIR / f"{logo_id}_{engine}.npy"


def _save_descriptors(logo_id: str, engine: Literal["orb", "sift"],
                      des: np.ndarray) -> None:
    np.save(str(_cache_path(logo_id, engine)), des)


def _load_descriptors(logo_id: str, engine: Literal["orb", "sift"]) -> np.ndarray | None:
    path = _cache_path(logo_id, engine)
    if not path.exists():
        return None
    return np.load(str(path))


# ══════════════════════════════════════════════════════════════════════════════
# Logo index helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_index() -> dict:
    if LOGO_INDEX_FILE.exists():
        return json.loads(LOGO_INDEX_FILE.read_text())
    return {}


def _save_index(index: dict) -> None:
    LOGO_INDEX_FILE.write_text(json.dumps(index, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# Image validation
# ══════════════════════════════════════════════════════════════════════════════

def _validate_image(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported extension '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content-type '{file.content_type}'.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Detection core — shared by both /detect/orb and /detect/sift
# ══════════════════════════════════════════════════════════════════════════════

def _run_detection(
    query_des:  np.ndarray,
    index:      dict,
    engine:     Literal["orb", "sift"],
    threshold:  int,
    matcher,
) -> list[dict]:
    """
    Compare query descriptors against every cached reference descriptor.
    Returns a list of result dicts sorted by detected-first / match-count desc.
    """
    results = []

    for logo_id, meta in index.items():
        ref_des = _load_descriptors(logo_id, engine)

        if ref_des is None:
            logger.warning(
                "No %s cache for logo '%s' (%s) — recomputing from image.",
                engine.upper(), meta["name"], logo_id,
            )
            logo_path = LOGO_STORE_DIR / meta["filename"]
            if not logo_path.exists():
                logger.error("Logo image missing for %s — skipping.", logo_id)
                continue
            gray    = _bytes_to_gray(logo_path.read_bytes())
            ref_des = _extract_orb(gray) if engine == "orb" else _extract_sift(gray)
            if ref_des is not None:
                _save_descriptors(logo_id, engine, ref_des)

        n_good   = _good_matches(query_des, ref_des, matcher)
        detected = n_good >= threshold

        logger.info(
            "[%s] %-30s %3d matches (threshold=%d) → %s",
            engine.upper(), f"'{meta['name']}':", n_good, threshold,
            "DETECTED" if detected else "not found",
        )

        results.append(
            {
                "logo_id":     logo_id,
                "name":        meta["name"],
                "detected":    detected,
                "match_count": n_good,
                "threshold":   threshold,
                "confidence":  round(min(n_good / max(threshold, 1), 1.0) * 100, 1),
                "engine":      engine,
            }
        )

    results.sort(key=lambda r: (not r["detected"], -r["match_count"]))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", summary="Health check", tags=["General"])
def health():
    """Returns 200 OK when the service is up."""
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — OCR
# ══════════════════════════════════════════════════════════════════════════════

def _run_ocr(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return pytesseract.image_to_string(image).strip()


@app.post("/ocr", summary="Extract text from an image", tags=["OCR"])
async def ocr_endpoint(file: UploadFile = File(...)):
    """Upload a JPG/PNG and receive the extracted text."""
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    text = _run_ocr(raw)
    logger.info("OCR '%s' → %d chars", file.filename, len(text))
    return {"filename": file.filename, "text": text, "character_count": len(text)}


@app.post("/ocr/batch", summary="Extract text from multiple images", tags=["OCR"])
async def ocr_batch_endpoint(files: list[UploadFile] = File(...)):
    """Upload multiple images and receive OCR results for each."""
    results = []
    for file in files:
        try:
            _validate_image(file)
            text = _run_ocr(await file.read())
            results.append({"filename": file.filename, "text": text,
                             "character_count": len(text), "error": None})
        except HTTPException as exc:
            results.append({"filename": file.filename, "text": None, "error": exc.detail})
    return {"results": results}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Logo Management
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/logos/register",
    summary="Register a reference logo",
    status_code=201,
    tags=["Logo Management"],
)
async def register_logo(
    file: UploadFile = File(...),
    name: str        = "",
):
    """
    Upload a clean reference logo image.

    **What happens at registration:**
    - Both **ORB** and **SIFT** descriptors are computed immediately and stored
      as `.npy` binary files on disk.
    - Detection calls load these cached files — no re-extraction ever occurs.

    **Tips for best accuracy:**
    - Preferred format: **PNG** (lossless, no compression artefacts).
    - Recommended size: **300–500 px** on the longest side.
    - Use an isolated logo on a white or transparent background.
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    gray     = _bytes_to_gray(raw)
    orb_des  = _extract_orb(gray)
    sift_des = _extract_sift(gray)

    if orb_des is None and sift_des is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No visual features could be extracted. "
                "Ensure the logo is at least 100×100 px, not blurry, and has distinct edges."
            ),
        )

    logo_id   = str(uuid.uuid4())
    ext       = Path(file.filename or "logo.png").suffix.lower() or ".png"
    img_path  = LOGO_STORE_DIR / f"{logo_id}{ext}"
    img_path.write_bytes(raw)

    # ── Cache descriptors ──────────────────────────────────────────────────────
    orb_count  = 0
    sift_count = 0

    if orb_des is not None:
        _save_descriptors(logo_id, "orb", orb_des)
        orb_count = int(len(orb_des))

    if sift_des is not None:
        _save_descriptors(logo_id, "sift", sift_des)
        sift_count = int(len(sift_des))

    # ── Persist metadata ───────────────────────────────────────────────────────
    logo_name = name.strip() or Path(file.filename or "").stem or logo_id

    entry = {
        "id":            logo_id,
        "name":          logo_name,
        "filename":      img_path.name,
        "original_file": file.filename,
        "orb_features":  orb_count,
        "sift_features": sift_count,
        "registered_at": datetime.utcnow().isoformat() + "Z",
    }

    index = _load_index()
    index[logo_id] = entry
    _save_index(index)

    logger.info(
        "Registered logo '%s' — ORB: %d features, SIFT: %d features, id: %s",
        logo_name, orb_count, sift_count, logo_id,
    )

    return {
        "logo_id":       logo_id,
        "name":          logo_name,
        "orb_features":  orb_count,
        "sift_features": sift_count,
        "message":       "Logo registered and descriptors cached for both ORB and SIFT.",
    }


@app.get("/logos", summary="List all registered logos", tags=["Logo Management"])
def list_logos():
    """Returns every logo currently registered, including their cached feature counts."""
    index = _load_index()
    return {"count": len(index), "logos": list(index.values())}


@app.delete("/logos/{logo_id}", summary="Remove a registered logo", tags=["Logo Management"])
def delete_logo(logo_id: str):
    """
    Delete a logo and all its associated files (image + ORB cache + SIFT cache).
    """
    index = _load_index()
    if logo_id not in index:
        raise HTTPException(status_code=404, detail=f"Logo '{logo_id}' not found.")

    entry = index.pop(logo_id)

    for path in [
        LOGO_STORE_DIR / entry["filename"],
        _cache_path(logo_id, "orb"),
        _cache_path(logo_id, "sift"),
    ]:
        if path.exists():
            path.unlink()

    _save_index(index)
    logger.info("Deleted logo '%s' (%s) and its descriptor caches.", entry["name"], logo_id)
    return {"message": f"Logo '{entry['name']}' and all cached descriptors deleted."}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Logo Detection  (ORB)
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/logos/detect/orb",
    summary="Detect logos — ORB engine (fast)",
    tags=["Logo Detection"],
)
async def detect_logos_orb(
    file:      UploadFile = File(...),
    threshold: int        = ORB_MIN_MATCHES,
):
    """
    Detect registered logos using the **ORB** feature matcher.

    | Property | Detail |
    |---|---|
    | Speed | ⚡ Fast — binary descriptors + Hamming distance |
    | Accuracy | Good for clean, high-contrast logos |
    | Best for | Real-time / high-volume scenarios |
    | Default threshold | `15` good matches |

    ORB descriptors are loaded from the pre-computed cache — no re-extraction
    happens at detection time.
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    index = _load_index()
    if not index:
        raise HTTPException(
            status_code=404,
            detail="No logos registered. Use POST /logos/register first.",
        )

    query_des = _extract_orb(_bytes_to_gray(raw))
    if query_des is None or len(query_des) == 0:
        raise HTTPException(
            status_code=422,
            detail="No ORB features found in the query image. Try a higher-resolution photo.",
        )

    results        = _run_detection(query_des, index, "orb", threshold, _bf_orb)
    detected_count = sum(1 for r in results if r["detected"])

    logger.info(
        "[ORB] Detection on '%s': %d/%d logos detected.",
        file.filename, detected_count, len(results),
    )

    return JSONResponse({
        "filename":       file.filename,
        "engine":         "orb",
        "logos_checked":  len(results),
        "logos_detected": detected_count,
        "results":        results,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Logo Detection  (SIFT)
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/logos/detect/sift",
    summary="Detect logos — SIFT engine (accurate)",
    tags=["Logo Detection"],
)
async def detect_logos_sift(
    file:      UploadFile = File(...),
    threshold: int        = SIFT_MIN_MATCHES,
):
    """
    Detect registered logos using the **SIFT** feature matcher.

    | Property | Detail |
    |---|---|
    | Speed | 🐢 Slower — float descriptors + L2 distance |
    | Accuracy | Excellent — handles scale, rotation, lighting changes |
    | Best for | Quality-critical or low-volume scenarios |
    | Default threshold | `10` good matches (SIFT matches are higher quality) |

    SIFT descriptors are loaded from the pre-computed cache — no re-extraction
    happens at detection time.
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    index = _load_index()
    if not index:
        raise HTTPException(
            status_code=404,
            detail="No logos registered. Use POST /logos/register first.",
        )

    query_des = _extract_sift(_bytes_to_gray(raw))
    if query_des is None or len(query_des) == 0:
        raise HTTPException(
            status_code=422,
            detail="No SIFT features found in the query image. Try a higher-resolution photo.",
        )

    results        = _run_detection(query_des, index, "sift", threshold, _bf_sift)
    detected_count = sum(1 for r in results if r["detected"])

    logger.info(
        "[SIFT] Detection on '%s': %d/%d logos detected.",
        file.filename, detected_count, len(results),
    )

    return JSONResponse({
        "filename":       file.filename,
        "engine":         "sift",
        "logos_checked":  len(results),
        "logos_detected": detected_count,
        "results":        results,
    })
