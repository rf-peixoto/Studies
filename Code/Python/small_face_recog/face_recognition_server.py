"""
Face Recognition API  — v2.0.0
────────────────────────────────────────────────────────────────────────────────
Designed to help people with prosopagnosia link faces to people they know.

Backend: InsightFace (ArcFace / buffalo_l model via ONNX Runtime)
  → No C++ compilation required — pure pip install.
  → Models are downloaded automatically on first start (~300 MB, once only).

Features
  • Faces : register reference face photos, auto-compute & cache 512-d ArcFace
            embeddings as .npy files in face_store/
  • Detect: POST /faces/detect — returns every registered person found in an image

Embedding cache
  At registration time the face embedding (512-d vector) is computed once and
  saved as a .npy file inside face_store/.  Detection loads these files
  directly — no re-encoding ever happens, so detection speed stays constant
  regardless of how large your face library grows.

Tips for best accuracy
  • Use a clear, well-lit, front-facing photo for registration.
  • One face per registration photo is strongly recommended.
  • Detection works on group photos — all registered faces are checked at once.
  • Default similarity threshold is 0.40 on cosine distance (lower = stricter).
    Tune via the `threshold` query parameter on /faces/detect.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis
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

# ── InsightFace model ──────────────────────────────────────────────────────────
# ctx_id=-1 → CPU only (no GPU required)
# Models download automatically to ~/.insightface/ on first start.
logger.info("Loading InsightFace model (may download ~300 MB on first run)...")
_face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
_face_app.prepare(ctx_id=-1, det_size=(640, 640))
logger.info("InsightFace model ready.")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Face Recognition API",
    description=__doc__,
    version="2.0.0",
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS    = {".jpg", ".jpeg", ".png"}

# ── Matching tuning ────────────────────────────────────────────────────────────
DEFAULT_THRESHOLD = 0.40   # Cosine distance threshold — lower = stricter
                           # Typical range: 0.30 (strict) – 0.55 (lenient)


# ══════════════════════════════════════════════════════════════════════════════
# Embedding cache  (disk-backed .npy files)
# ══════════════════════════════════════════════════════════════════════════════

def _cache_path(face_id: str) -> Path:
    return FACE_STORE_DIR / f"{face_id}_embedding.npy"


def _save_embedding(face_id: str, embedding: np.ndarray) -> None:
    np.save(str(_cache_path(face_id)), embedding)


def _load_embedding(face_id: str) -> np.ndarray | None:
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

def _get_embeddings(raw: bytes) -> list[np.ndarray]:
    """
    Decode raw image bytes and return a list of 512-d ArcFace embeddings,
    one per face detected in the image.
    Returns an empty list if no faces are found.
    """
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")

    faces = _face_app.get(img)
    return [face.embedding for face in faces]


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine distance in [0, 2]. Lower means more similar."""
    a = a / (np.linalg.norm(a) + 1e-10)
    b = b / (np.linalg.norm(b) + 1e-10)
    return float(1.0 - np.dot(a, b))


# ══════════════════════════════════════════════════════════════════════════════
# Detection core
# ══════════════════════════════════════════════════════════════════════════════

def _run_detection(
    query_embeddings: list[np.ndarray],
    index: dict,
    threshold: float,
) -> list[dict]:
    """
    Compare every face found in the query image against every registered
    face embedding. A registered person is considered detected if at least
    one query face is within `threshold` cosine distance of their stored embedding.

    Returns a list of result dicts sorted by detected-first / distance asc.
    """
    results = []

    for face_id, meta in index.items():
        ref_embedding = _load_embedding(face_id)

        if ref_embedding is None:
            logger.warning(
                "No embedding cache for '%s' (%s) — skipping.", meta["name"], face_id
            )
            continue

        if not query_embeddings:
            detected     = False
            best_distance = None
        else:
            distances    = [_cosine_distance(q, ref_embedding) for q in query_embeddings]
            best_distance = float(min(distances))
            detected     = best_distance <= threshold

        confidence = None
        if best_distance is not None:
            raw_conf   = max(0.0, (threshold - best_distance) / threshold) * 100
            confidence = round(raw_conf, 1)

        logger.info(
            "%-30s best_distance=%.4f (threshold=%.2f) → %s",
            f"'{meta['name']}':",
            best_distance if best_distance is not None else -1,
            threshold,
            "DETECTED" if detected else "not found",
        )

        results.append({
            "face_id":       face_id,
            "name":          meta["name"],
            "detected":      detected,
            "best_distance": best_distance,
            "threshold":     threshold,
            "confidence":    confidence,
        })

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
    - The first face found in the photo is encoded into a 512-d ArcFace vector.
    - The embedding is saved as a `.npy` file in `face_store/`.
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

    embeddings = _get_embeddings(raw)

    if not embeddings:
        raise HTTPException(
            status_code=422,
            detail=(
                "No face detected in the uploaded photo. "
                "Ensure the face is clearly visible, well-lit, and at least 150×150 px."
            ),
        )

    if len(embeddings) > 1:
        logger.warning("Multiple faces in registration photo — using the first one only.")

    face_id  = str(uuid.uuid4())
    ext      = Path(file.filename or "face.jpg").suffix.lower() or ".jpg"
    img_path = FACE_STORE_DIR / f"{face_id}{ext}"
    img_path.write_bytes(raw)

    _save_embedding(face_id, embeddings[0])

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
        "message": "Face registered and embedding cached.",
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
    (reference photo + embedding cache).
    """
    index = _load_index()
    if face_id not in index:
        raise HTTPException(status_code=404, detail=f"Face '{face_id}' not found.")

    entry = index.pop(face_id)

    for path in [FACE_STORE_DIR / entry["filename"], _cache_path(face_id)]:
        if path.exists():
            path.unlink()

    _save_index(index)
    logger.info("Deleted face '%s' (%s) and its embedding cache.", entry["name"], face_id)
    return {"message": f"Face '{entry['name']}' and its embedding deleted."}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Face Detection
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/faces/detect", summary="Detect registered faces in an image", tags=["Face Detection"])
async def detect_faces(
    file:      UploadFile = File(...),
    threshold: float      = DEFAULT_THRESHOLD,
):
    """
    Scan an image for any registered faces.

    Returns every registered person, sorted by detected-first then by distance.

    | Property | Detail |
    |---|---|
    | Model | InsightFace buffalo_l (ArcFace ResNet50) |
    | Embedding | 512-d cosine distance |
    | Default threshold | `0.40` |
    | `threshold` param | Lower → stricter. Range: `0.30` (strict) – `0.55` (lenient) |
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

    query_embeddings = _get_embeddings(raw)

    if not query_embeddings:
        logger.info("No faces found in query image '%s'.", file.filename)

    results        = _run_detection(query_embeddings, index, threshold)
    detected_count = sum(1 for r in results if r["detected"])

    logger.info(
        "Detection on '%s': %d face(s) in image, %d/%d registered people detected.",
        file.filename, len(query_embeddings), detected_count, len(results),
    )

    return JSONResponse({
        "filename":        file.filename,
        "faces_in_image":  len(query_embeddings),
        "people_checked":  len(results),
        "people_detected": detected_count,
        "threshold":       threshold,
        "results":         results,
    })
