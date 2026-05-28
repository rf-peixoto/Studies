"""
Face Recognition API  — v3.0.0
────────────────────────────────────────────────────────────────────────────────
Designed to help people with prosopagnosia link faces to people they know.

Backend
  • InsightFace buffalo_l  — ArcFace ResNet50 via ONNX Runtime (no compilation)
  • Qdrant                 — vector database for ANN search at any scale

Why Qdrant?
  The previous version stored embeddings as individual .npy files and compared
  them one by one at detection time (brute force, O(n)). That works fine for
  hundreds of faces but becomes unusably slow past ~100k.

  Qdrant uses an HNSW (Hierarchical Navigable Small World) index that finds the
  nearest vectors in O(log n) — hundreds of millions of faces, millisecond
  queries.

Minimal metadata
  Each registered face stores only: id (uuid) + filename (without path).
  The original image is kept on disk in face_store/images/.

Requirements
  Qdrant must be running before starting this server:
    docker compose up -d

  First start downloads InsightFace models (~300 MB, once only).
────────────────────────────────────────────────────────────────────────────────
"""

import logging
import uuid
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Storage ────────────────────────────────────────────────────────────────────
IMAGE_DIR = Path("face_store/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# ── Qdrant ─────────────────────────────────────────────────────────────────────
QDRANT_HOST       = "localhost"
QDRANT_PORT       = 6333
COLLECTION_NAME   = "faces"
EMBEDDING_DIM     = 512          # ArcFace ResNet50 output dimension

_qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def _ensure_collection() -> None:
    existing = {c.name for c in _qdrant.get_collections().collections}
    if COLLECTION_NAME not in existing:
        _qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'.", COLLECTION_NAME)
    else:
        logger.info("Qdrant collection '%s' already exists.", COLLECTION_NAME)

_ensure_collection()

# ── InsightFace ────────────────────────────────────────────────────────────────
logger.info("Loading InsightFace model (may download ~300 MB on first run)...")
_face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
_face_app.prepare(ctx_id=-1, det_size=(640, 640))
logger.info("InsightFace model ready.")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Face Recognition API",
    description=__doc__,
    version="3.0.0",
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
DEFAULT_THRESHOLD  = 0.40   # Cosine distance — lower = stricter
                             # Typical range: 0.30 (strict) – 0.55 (lenient)


# ══════════════════════════════════════════════════════════════════════════════
# Image helpers
# ══════════════════════════════════════════════════════════════════════════════

def _validate_image(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported extension '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )


def _get_embeddings(raw: bytes) -> list[np.ndarray]:
    """Return one 512-d ArcFace embedding per face found in the image."""
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")
    return [face.embedding for face in _face_app.get(img)]


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", summary="Health check", tags=["General"])
def health():
    """Returns 200 OK when the service is up."""
    info = _qdrant.get_collection(COLLECTION_NAME)
    return {
        "status":       "ok",
        "faces_indexed": info.points_count,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Face Management
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/faces/register", summary="Register a face", tags=["Face Management"])
async def register_face(file: UploadFile = File(...)):
    """
    Upload a reference photo to register a person's face.

    The filename (without extension) is used as the person's display name,
    so name your file accordingly — e.g. `john_smith.jpg`.

    If multiple faces are present in the photo, only the first is registered.
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

    # Save image to disk
    face_id  = str(uuid.uuid4())
    filename = Path(file.filename or f"{face_id}.jpg").name   # strip path
    img_path = IMAGE_DIR / f"{face_id}{Path(filename).suffix}"
    img_path.write_bytes(raw)

    # Upsert into Qdrant — minimal payload: filename only
    _qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=face_id,
                vector=embeddings[0].tolist(),
                payload={"filename": filename},
            )
        ],
    )

    logger.info("Registered face '%s' — id: %s", filename, face_id)
    return {"face_id": face_id, "filename": filename, "message": "Face registered."}


@app.get("/faces", summary="List all registered faces", tags=["Face Management"])
def list_faces(limit: int = 100, offset: int = 0):
    """
    Returns registered faces, paginated.
    Use `limit` and `offset` to walk through large collections.
    """
    results, _ = _qdrant.scroll(
        collection_name=COLLECTION_NAME,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    faces = [{"face_id": str(p.id), **p.payload} for p in results]
    total = _qdrant.get_collection(COLLECTION_NAME).points_count
    return {"total": total, "limit": limit, "offset": offset, "faces": faces}


@app.delete("/faces/{face_id}", summary="Remove a registered face", tags=["Face Management"])
def delete_face(face_id: str):
    """Delete a registered face, its image file, and its vector from Qdrant."""
    points = _qdrant.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[face_id],
        with_payload=True,
    )
    if not points:
        raise HTTPException(status_code=404, detail=f"Face '{face_id}' not found.")

    filename = points[0].payload.get("filename", "")

    # Remove image from disk
    for path in IMAGE_DIR.glob(f"{face_id}.*"):
        path.unlink()

    # Remove vector from Qdrant
    _qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=[face_id],
    )

    logger.info("Deleted face '%s' (%s).", filename, face_id)
    return {"message": f"Face '{filename}' deleted."}


# ══════════════════════════════════════════════════════════════════════════════
# Routes — Face Detection
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/faces/detect", summary="Detect registered faces in an image", tags=["Face Detection"])
async def detect_faces(
    file:      UploadFile = File(...),
    threshold: float      = DEFAULT_THRESHOLD,
    top_k:     int        = 5,
):
    """
    Scan an image for registered faces using ANN search.

    For each face found in the image, Qdrant returns the `top_k` closest
    registered faces. Only matches within `threshold` cosine distance are
    marked as detected.

    Works on group photos — every face in the image is checked.

    | Threshold | Behaviour |
    |-----------|-----------|
    | `0.30`    | Very strict |
    | `0.40`    | Default — good balance |
    | `0.55`    | Lenient |
    """
    _validate_image(file)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    total = _qdrant.get_collection(COLLECTION_NAME).points_count
    if total == 0:
        raise HTTPException(
            status_code=404,
            detail="No faces registered. Use POST /faces/register first.",
        )

    query_embeddings = _get_embeddings(raw)
    if not query_embeddings:
        logger.info("No faces found in query image '%s'.", file.filename)

    # For each face in the image, run an ANN search against Qdrant
    seen     = {}   # face_id → best result so far (dedup across query faces)
    for embedding in query_embeddings:
        hits = _qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=embedding.tolist(),
            limit=top_k,
            score_threshold=1.0 - threshold,   # Qdrant uses cosine similarity [−1,1]
                                                # distance = 1 − similarity
                                                # so score_threshold = 1 − threshold
        )
        for hit in hits:
            fid      = str(hit.id)
            distance = round(1.0 - hit.score, 4)
            if fid not in seen or distance < seen[fid]["best_distance"]:
                confidence = round(max(0.0, (threshold - distance) / threshold) * 100, 1)
                seen[fid] = {
                    "face_id":       fid,
                    "filename":      hit.payload.get("filename", ""),
                    "detected":      True,
                    "best_distance": distance,
                    "threshold":     threshold,
                    "confidence":    confidence,
                }

    results = sorted(seen.values(), key=lambda r: r["best_distance"])

    logger.info(
        "Detection on '%s': %d face(s) in image, %d registered people detected.",
        file.filename, len(query_embeddings), len(results),
    )

    return JSONResponse({
        "filename":        file.filename,
        "faces_in_image":  len(query_embeddings),
        "people_detected": len(results),
        "threshold":       threshold,
        "results":         results,
    })
