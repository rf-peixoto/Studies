import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

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

# ── Paths ──────────────────────────────────────────────────────────────────────
LOGO_STORE_DIR  = Path("logo_store")
LOGO_INDEX_FILE = LOGO_STORE_DIR / "index.json"
LOGO_STORE_DIR.mkdir(exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OCR + Logo Detection API",
    description=(
        "Extracts text from images (OCR) and detects client logos "
        "using ORB feature matching."
    ),
    version="2.0.0",
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS    = {".jpg", ".jpeg", ".png"}

# ── Tuning constants ──────────────────────────────────────────────────────────
# Minimum good feature matches to consider a logo "detected"
MIN_MATCH_COUNT = 15
# Lowe's ratio-test threshold  (lower = stricter matching)
LOWE_RATIO      = 0.75


# ══════════════════════════════════════════════════════════════════════════════
# Helpers — shared
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


def _bytes_to_cv2_gray(image_bytes: bytes) -> np.ndarray:
    """Decode raw image bytes into an OpenCV grayscale array."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ══════════════════════════════════════════════════════════════════════════════
# Logo index — persists metadata across restarts
# ══════════════════════════════════════════════════════════════════════════════

def _load_index() -> dict:
    if LOGO_INDEX_FILE.exists():
        return json.loads(LOGO_INDEX_FILE.read_text())
    return {}


def _save_index(index: dict) -> None:
    LOGO_INDEX_FILE.write_text(json.dumps(index, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# ORB Feature Engine
#
# ORB (Oriented FAST and Rotated BRIEF) is:
#  - Patent-free (unlike SIFT/SURF)
#  - Fast enough for real-time use
#  - Robust to scale, rotation, and moderate perspective changes
# ══════════════════════════════════════════════════════════════════════════════

_orb = cv2.ORB_create(nfeatures=1000)

# BFMatcher with Hamming distance — correct for ORB binary descriptors.
_bf  = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)


def _compute_descriptors(gray: np.ndarray):
    """Return (keypoints, descriptors) for a grayscale image."""
    return _orb.detectAndCompute(gray, None)


def _count_good_matches(des_query: np.ndarray, des_ref: np.ndarray) -> int:
    """
    Apply Lowe's ratio test and return the count of good feature matches.
    Returns 0 when either descriptor set is empty or too small.
    """
    if des_query is None or des_ref is None:
        return 0
    if len(des_query) < 2 or len(des_ref) < 2:
        return 0

    matches = _bf.knnMatch(des_ref, des_query, k=2)

    good = [
        m for pair in matches
        if len(pair) == 2
        for m, n in [pair]
        if m.distance < LOWE_RATIO * n.distance
    ]
    return len(good)


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — OCR
# ══════════════════════════════════════════════════════════════════════════════

def _run_ocr(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return pytesseract.image_to_string(image).strip()


@app.post("/ocr", summary="Extract text from an image")
async def ocr_endpoint(file: UploadFile = File(...)):
    """Upload a JPG/PNG and receive the extracted text."""
    _validate_image(file)
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    text = _run_ocr(image_bytes)
    logger.info("OCR: '%s' → %d chars", file.filename, len(text))
    return JSONResponse({"filename": file.filename, "text": text, "character_count": len(text)})


@app.post("/ocr/batch", summary="Extract text from multiple images")
async def ocr_batch_endpoint(files: list[UploadFile] = File(...)):
    """Upload multiple images and get OCR results for each."""
    results = []
    for file in files:
        try:
            _validate_image(file)
            text = _run_ocr(await file.read())
            results.append({"filename": file.filename, "text": text,
                            "character_count": len(text), "error": None})
        except HTTPException as exc:
            results.append({"filename": file.filename, "text": None, "error": exc.detail})
    return JSONResponse({"results": results})


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Logo Management
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/logos/register", summary="Register a reference logo", status_code=201)
async def register_logo(
    file: UploadFile = File(...),
    name: str        = "",
):
    """
    Upload a clean reference logo image to use as a detection template.

    - **name** — human-friendly label (e.g. `"Acme Corp"`). Defaults to filename stem.

    Returns a `logo_id` that you will see in `/logos/detect` results.

    **Tips for best results:**
    - Use a clean, isolated version of the logo (transparent or white background).
    - Minimum size of 100×100 px recommended.
    - Avoid heavily compressed or blurry images.
    """
    _validate_image(file)
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    # Verify the image has enough detectable features before saving
    gray = _bytes_to_cv2_gray(image_bytes)
    _, des = _compute_descriptors(gray)

    if des is None or len(des) == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No visual features could be extracted from this logo. "
                "Make sure it has distinct shapes/edges and is not too small or blurry."
            ),
        )

    logo_id   = str(uuid.uuid4())
    ext       = Path(file.filename or "logo.png").suffix.lower() or ".png"
    save_path = LOGO_STORE_DIR / f"{logo_id}{ext}"
    save_path.write_bytes(image_bytes)

    logo_name = name.strip() or Path(file.filename or "").stem or logo_id

    index = _load_index()
    index[logo_id] = {
        "id":            logo_id,
        "name":          logo_name,
        "filename":      save_path.name,
        "original_file": file.filename,
        "feature_count": int(len(des)),
        "registered_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_index(index)

    logger.info("Registered logo '%s' — %d features, id: %s", logo_name, len(des), logo_id)

    return {
        "logo_id":       logo_id,
        "name":          logo_name,
        "feature_count": int(len(des)),
        "message":       "Logo registered successfully.",
    }


@app.get("/logos", summary="List all registered logos")
def list_logos():
    """Returns every logo currently registered for detection."""
    index = _load_index()
    return {"count": len(index), "logos": list(index.values())}


@app.delete("/logos/{logo_id}", summary="Remove a registered logo")
def delete_logo(logo_id: str):
    """Delete a logo by its `logo_id`."""
    index = _load_index()
    if logo_id not in index:
        raise HTTPException(status_code=404, detail=f"Logo '{logo_id}' not found.")

    entry     = index.pop(logo_id)
    logo_path = LOGO_STORE_DIR / entry["filename"]
    if logo_path.exists():
        logo_path.unlink()

    _save_index(index)
    logger.info("Deleted logo '%s' (%s)", entry["name"], logo_id)
    return {"message": f"Logo '{entry['name']}' deleted successfully."}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Logo Detection
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/logos/detect", summary="Detect registered logos in an image")
async def detect_logos(
    file:      UploadFile = File(...),
    threshold: int        = MIN_MATCH_COUNT,
):
    """
    Upload any image and find which of your registered logos appear in it.

    The detector works **purely on visual shape features** — it intentionally
    ignores text and focuses on graphic elements like shapes, symbols and colour
    gradients that make up a logo.

    ### How it works
    1. ORB extracts keypoints and binary descriptors from both the query image
       and every reference logo.
    2. A Brute-Force matcher pairs descriptors, and Lowe's ratio test filters
       out ambiguous matches.
    3. If the number of surviving matches meets `threshold`, the logo is marked
       as **detected**.

    ### Parameters
    - **threshold** — minimum good matches required (default `15`).  
      Lower → more sensitive (may cause false positives).  
      Higher → stricter (may miss partially visible logos).

    ### Response fields
    | Field | Description |
    |---|---|
    | `detected` | `true` if `match_count >= threshold` |
    | `match_count` | number of good feature matches found |
    | `confidence` | `match_count / threshold` capped at 100 % |
    """
    _validate_image(file)
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    index = _load_index()
    if not index:
        raise HTTPException(
            status_code=404,
            detail="No logos registered yet. Use POST /logos/register first.",
        )

    # Compute query descriptors once — reused for every logo comparison
    query_gray   = _bytes_to_cv2_gray(image_bytes)
    _, query_des = _compute_descriptors(query_gray)

    if query_des is None or len(query_des) == 0:
        raise HTTPException(
            status_code=422,
            detail="No visual features found in the query image. Try a higher-resolution photo.",
        )

    results = []
    for logo_id, meta in index.items():
        logo_path = LOGO_STORE_DIR / meta["filename"]
        if not logo_path.exists():
            logger.warning("Missing logo file for id %s — skipping.", logo_id)
            continue

        ref_gray     = _bytes_to_cv2_gray(logo_path.read_bytes())
        _, ref_des   = _compute_descriptors(ref_gray)
        good_matches = _count_good_matches(query_des, ref_des)
        detected     = good_matches >= threshold

        logger.info(
            "Logo %-30s %3d matches (threshold=%d) → %s",
            f"'{meta['name']}':", good_matches, threshold,
            "DETECTED" if detected else "not found",
        )

        results.append(
            {
                "logo_id":     logo_id,
                "name":        meta["name"],
                "detected":    detected,
                "match_count": good_matches,
                "threshold":   threshold,
                # confidence: percentage relative to threshold, capped at 100
                "confidence":  round(min(good_matches / max(threshold, 1), 1.0) * 100, 1),
            }
        )

    # Sort: detected logos first, then by descending match count
    results.sort(key=lambda r: (not r["detected"], -r["match_count"]))

    detected_count = sum(1 for r in results if r["detected"])
    logger.info(
        "Detection complete — '%s': %d/%d logos detected.",
        file.filename, detected_count, len(results),
    )

    return JSONResponse(
        {
            "filename":       file.filename,
            "logos_checked":  len(results),
            "logos_detected": detected_count,
            "results":        results,
        }
    )
