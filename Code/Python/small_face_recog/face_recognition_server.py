"""
Face Recognition API  — v1.0.0
────────────────────────────────────────────────────────────────────────────────
Designed to help people with prosopagnosia link faces to people they know.

Features
  • Faces : register reference face photos, auto-compute & cache 128-d encodings
  • Detect: POST /faces/detect — returns every registered person found in an image

Encoding cache
  At registration time the face encoding (128-d vector) is computed once and
  saved as a .npy file inside face_store/.  Detection loads these files
  directly — no re-extraction ever happens, so detection speed stays constant
  regardless of how large your face library grows.

Tips for best accuracy
  • Use a clear, well-lit, front-facing photo for registration.
  • One face per registration photo is strongly recommended.
  • Detection works on group photos — all registered faces are checked at once.
  • Default match tolerance is 0.55 (lower = stricter). Tune via the
    `tolerance` query parameter on /faces/detect.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import face_recognition
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Storage paths ──────────────────────────────────────────────────────────────
FACE_STORE_DIR  = Path("face_store")
FACE_INDEX_FILE = FACE_STORE_DIR / "index.json"
FACE_STORE_DIR.mkdir(exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Face Recognition API",
    description=__doc__,
    version="1.0.0",
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS    = {".jpg", ".jpeg", ".png"}

# ── Matching tuning ────────────────────────────────────────────────────────────
DEFAULT_TOLERANCE = 0.55   # Euclidean distance threshold — lower = stricter
                           # face_recognition's own default is 0.6; 0.55 reduces
                           # false positives at a small cost in recall.


# ══════════════════════════════════════════════════════════════════════════════
# Encoding cache  (disk-backed .npy files)
# ══════════════════════════════════════════════════════════════════════════════

def _cache_path(face_id: str) -> Path:
    return FACE_STORE_DIR / f"{face_id}_encoding.npy"


def _save_encoding(face_id: str, encoding: np.ndarray) -> None:
    np.save(str(_cache_path(face_id)), encoding)


def _load_encoding(face_id: str) -> np.ndarray | None:
    path = _cache_path(face_id)
    if not path.exists():
        return None
    return np.load(str(path))


# ══════════════════════════════════════════════════════════════════════════════
# Face index helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_index() -> dict:
    if FACE_INDEX_FILE.exists():
        return json.loads(FACE_INDEX_FILE.read_text())
    return {}


def _save_index(index: dict) -> None:
    FACE_INDEX_FILE.write_text(json.dumps(index, indent=2))


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
# Encoding helper
# ══════════════════════════════════════════════════════════════════════════════

def _encode_image(raw: bytes) -> list[np.ndarray]:
    """
    Decode raw image bytes and return a list of 128-d face encodings,
    one per face detected in the image.
    Returns an empty list if no faces are found.
    """
    img = face_recognition.load_image_file(__import__("io").BytesIO(raw))
    return face_recognition.face_encodings(img)


# ══════════════════════════════════════════════════════════════════════════════
# Detection core
# ══════════════════════════════════════════════════════════════════════════════

def _run_detection(query_encodings: list[np.ndarray], index: dict, tolerance: float) -> list[dict]:
    """
    Compare every face found in the query image against every registered
    face encoding. A registered person is considered detected if at least
    one query face is within `tolerance` distance of their stored encoding.

    Returns a list of result dicts sorted by detected-first / distance asc.
    """
    results = []

    for face_id, meta in index.items():
        ref_encoding = _load_encoding(face_id)

        if ref_encoding is None:
            logger.warning(
                "No encoding cache for face '%s' (%s) — skipping.",
                meta["name"], face_id,
            )
            continue

        if len(query_encodings) == 0:
            detected = False
            best_distance = None
        else:
            # face_distance returns one distance per query face
            distances = face_recognition.face_distance(query_encodings, ref_encoding)
            best_distance = float(np.min(distances))
            detected = bool(best_distance <= tolerance)

        confidence = None
        if best_distance is not None:
            # Map distance [0, tolerance] → confidence [100, 0] %
            # Distances above tolerance are capped at 0 % confidence
            raw_conf = max(0.0, (tolerance - best_distance) / tolerance) * 100
            confidence = round(raw_conf, 1)

        logger.info(
            "%-30s best_distance=%.4f (tolerance=%.2f) → %s",
            f"'{meta['name']}':",
            best_distance if best_distance is not None else -1,
            tolerance,
            "DETECTED" if detected else "not found",
        )

        results.append(
            {
                "face_id":       face_id,
                "name":          meta["name"],
                "detected":      detected,
                "best_distance": best_distance,
                "tolerance":     tolerance,
                "confidence":    confidence,
            }
        )

    results.sort(key=lambda r: (not r["detected"], r["best_distance"] or 9.0))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", summary="Health check", tags=["General"])
def health():
    """Returns 200 OK when the service is up."""
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Face Management
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/faces/register", summary="Register a face", tags=["Face Management"])
async def register_face(
    file: UploadFile = File(...),
    name: str        = "",
):
    """
    Upload a reference photo to register a person's face.

    **What happens at registration:**
    - The first face found in the photo is encoded into a 128-d vector.
    - The encoding is saved as a `.npy` file in `face_store/`.
    - Detection calls load this file directly — no re-encoding ever occurs.

    **Tips for best accuracy:**
    - Use a clear, well-lit, **front-facing** photo.
    - One face per photo. If multiple faces are present, only the first is used.
    - Preferred format: **JPEG or PNG**, at least 150×150 px.
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    encodings = _encode_image(raw)

    if not encodings:
        raise HTTPException(
            status_code=422,
            detail=(
                "No face detected in the uploaded photo. "
                "Ensure the face is clearly visible, well-lit, and at least 150×150 px."
            ),
        )

    if len(encodings) > 1:
        logger.warning(
            "Multiple faces detected in registration photo — using the first one only."
        )

    face_id  = str(uuid.uuid4())
    ext      = Path(file.filename or "face.jpg").suffix.lower() or ".jpg"
    img_path = FACE_STORE_DIR / f"{face_id}{ext}"
    img_path.write_bytes(raw)

    _save_encoding(face_id, encodings[0])

    face_name = name.strip() or Path(file.filename or "").stem or face_id

    entry = {
        "id":            face_id,
        "name":          face_name,
        "filename":      img_path.name,
        "original_file": file.filename,
        "registered_at": datetime.utcnow().isoformat() + "Z",
    }

    index = _load_index()
    index[face_id] = entry
    _save_index(index)

    logger.info("Registered face '%s' — id: %s", face_name, face_id)

    return {
        "face_id": face_id,
        "name":    face_name,
        "message": "Face registered and encoding cached.",
    }


@app.get("/faces", summary="List all registered faces", tags=["Face Management"])
def list_faces():
    """Returns every person currently registered."""
    index = _load_index()
    return {"count": len(index), "faces": list(index.values())}


@app.delete("/faces/{face_id}", summary="Remove a registered face", tags=["Face Management"])
def delete_face(face_id: str):
    """
    Delete a registered face and all its associated files
    (reference photo + encoding cache).
    """
    index = _load_index()
    if face_id not in index:
        raise HTTPException(status_code=404, detail=f"Face '{face_id}' not found.")

    entry = index.pop(face_id)

    for path in [
        FACE_STORE_DIR / entry["filename"],
        _cache_path(face_id),
    ]:
        if path.exists():
            path.unlink()

    _save_index(index)
    logger.info("Deleted face '%s' (%s) and its encoding cache.", entry["name"], face_id)
    return {"message": f"Face '{entry['name']}' and its encoding deleted."}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Face Detection
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/faces/detect", summary="Detect registered faces in an image", tags=["Face Detection"])
async def detect_faces(
    file:      UploadFile = File(...),
    tolerance: float      = DEFAULT_TOLERANCE,
):
    """
    Scan an image for any registered faces.

    Returns every registered person, sorted by detected-first then by
    match confidence.

    | Property | Detail |
    |---|---|
    | Model | `face_recognition` (dlib ResNet — 99.38 % accuracy on LFW) |
    | Encoding | 128-d Euclidean distance |
    | Default tolerance | `0.55` (stricter than library default of 0.6) |
    | `tolerance` param | Lower → stricter. Range: `0.4` (strict) – `0.7` (lenient) |
    | Multi-face images | ✅ All faces in the photo are checked against all registered people |
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    index = _load_index()
    if not index:
        raise HTTPException(
            status_code=404,
            detail="No faces registered. Use POST /faces/register first.",
        )

    query_encodings = _encode_image(raw)

    if not query_encodings:
        logger.info("No faces found in query image '%s'.", file.filename)

    results        = _run_detection(query_encodings, index, tolerance)
    detected_count = sum(1 for r in results if r["detected"])

    logger.info(
        "Detection on '%s': %d face(s) in image, %d/%d registered people detected.",
        file.filename, len(query_encodings), detected_count, len(results),
    )

    return JSONResponse({
        "filename":         file.filename,
        "faces_in_image":   len(query_encodings),
        "people_checked":   len(results),
        "people_detected":  detected_count,
        "tolerance":        tolerance,
        "results":          results,
    })
