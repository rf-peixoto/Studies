import io
import logging
from pathlib import Path

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

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OCR API",
    description="Extracts text from JPG, JPEG and PNG images using Tesseract OCR.",
    version="1.0.0",
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS    = {".jpg", ".jpeg", ".png"}


def _validate_image(file: UploadFile) -> None:
    """Raise HTTPException if the uploaded file is not an accepted image type."""
    ext = Path(file.filename or "").suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file extension '{ext}'. "
                f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported content-type '{file.content_type}'. "
                f"Allowed: {sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        )


def _run_ocr(image_bytes: bytes) -> str:
    """Open an image from raw bytes and run Tesseract OCR on it."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not decode image: {exc}",
        ) from exc

    # Convert palette / RGBA images so Tesseract handles them correctly
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    text: str = pytesseract.image_to_string(image)
    return text.strip()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
def health():
    """Returns 200 OK when the service is up."""
    return {"status": "ok"}


@app.post("/ocr", summary="Extract text from an image")
async def ocr_endpoint(file: UploadFile = File(...)):
    """
    Upload a **JPG**, **JPEG** or **PNG** image and receive the extracted text.

    - `text`          – the raw OCR output
    - `character_count` – total characters in the extracted text
    - `filename`      – original filename sent by the client
    """
    _validate_image(file)

    logger.info("Processing file: %s (%s)", file.filename, file.content_type)

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    text = _run_ocr(image_bytes)

    logger.info(
        "OCR complete for '%s' — %d characters extracted.",
        file.filename,
        len(text),
    )

    return JSONResponse(
        content={
            "filename":        file.filename,
            "text":            text,
            "character_count": len(text),
        }
    )


@app.post("/ocr/batch", summary="Extract text from multiple images")
async def ocr_batch_endpoint(files: list[UploadFile] = File(...)):
    """
    Upload **multiple** images at once.  
    Returns a list of results in the same order as the uploaded files.
    """
    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    results = []
    for file in files:
        try:
            _validate_image(file)
            image_bytes = await file.read()
            text = _run_ocr(image_bytes)
            results.append(
                {
                    "filename":        file.filename,
                    "text":            text,
                    "character_count": len(text),
                    "error":           None,
                }
            )
        except HTTPException as exc:
            results.append(
                {
                    "filename": file.filename,
                    "text":     None,
                    "error":    exc.detail,
                }
            )

    return JSONResponse(content={"results": results})
