# OCR + Logo Detection API  v3

A lightweight REST API that:
- **Extracts text** from images using Tesseract OCR
- **Detects client logos** using OpenCV feature matching — with a choice of engine

---

## What's new in v3

| | v2 | v3 |
|---|---|---|
| Engines | ORB only | **ORB + SIFT** (separate endpoints) |
| Descriptor computation | On every `/detect` call | **Once at registration**, cached to `.npy` |
| Detection speed | Degrades with library size | **Constant** regardless of library size |
| `opencv` package | `opencv-python-headless` | `opencv-contrib-python-headless` |

---

## Quick Start

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

Interactive docs → **http://localhost:8000/docs**

---

## OCR Endpoints

### `POST /ocr`
```bash
curl -X POST http://localhost:8000/ocr -F "file=@photo.png"
```

### `POST /ocr/batch`
```bash
curl -X POST http://localhost:8000/ocr/batch -F "files=@a.png" -F "files=@b.jpg"
```

---

## Logo Management

### `POST /logos/register`

Uploads a reference logo. At registration time:
1. ORB descriptors are extracted and saved as `{id}_orb.npy`
2. SIFT descriptors are extracted and saved as `{id}_sift.npy`

No feature extraction happens at detection time — only file reads.

```bash
curl -X POST "http://localhost:8000/logos/register?name=Acme+Corp" \
     -F "file=@acme_logo.png"
```

```json
{
  "logo_id": "d3f1a2b4-...",
  "name": "Acme Corp",
  "orb_features": 521,
  "sift_features": 384,
  "message": "Logo registered and descriptors cached for both ORB and SIFT."
}
```

### `GET /logos`
```bash
curl http://localhost:8000/logos
```

### `DELETE /logos/{logo_id}`
Removes the logo image and **both** `.npy` cache files.
```bash
curl -X DELETE http://localhost:8000/logos/d3f1a2b4-...
```

---

## Logo Detection

Both endpoints return the same response shape. Choose based on your needs:

| | `POST /logos/detect/orb` | `POST /logos/detect/sift` |
|---|---|---|
| Speed | ⚡ Fast | 🐢 Slower |
| Accuracy | Good | Excellent |
| Best for | High volume / real-time | Quality-critical |
| Default threshold | 15 | 10 |
| Descriptor type | Binary (Hamming) | Float (L2) |

```bash
# ORB — fast
curl -X POST "http://localhost:8000/logos/detect/orb" \
     -F "file=@document.jpg"

# SIFT — accurate
curl -X POST "http://localhost:8000/logos/detect/sift?threshold=8" \
     -F "file=@document.jpg"
```

```json
{
  "filename": "document.jpg",
  "engine": "sift",
  "logos_checked": 3,
  "logos_detected": 1,
  "results": [
    {
      "logo_id": "d3f1a2b4-...",
      "name": "Acme Corp",
      "detected": true,
      "match_count": 31,
      "threshold": 10,
      "confidence": 100.0,
      "engine": "sift"
    },
    {
      "logo_id": "e9c2b1a0-...",
      "name": "Other Corp",
      "detected": false,
      "match_count": 2,
      "threshold": 10,
      "confidence": 20.0,
      "engine": "sift"
    }
  ]
}
```

### Threshold tuning guide

| Scenario | Recommended |
|---|---|
| Large, clearly visible logo | `15–20` (ORB) / `10–15` (SIFT) |
| Small or partially cropped | `8–12` (ORB) / `6–8` (SIFT) |
| Strong angle / perspective | `8–12` (ORB) / `6–8` (SIFT) |
| Too many false positives | Increase by `+5–10` |

---

## How Descriptor Caching Works

```
Registration (once)               Detection (every call)
──────────────────                ──────────────────────────────
Upload logo.png                   Upload query photo
       │                                   │
  ORB extraction ──→ id_orb.npy            │
  SIFT extraction ──→ id_sift.npy          ▼
       │                          Extract query descriptors
  Save image                               │
  Save index.json                  Load id_orb.npy  ← disk read only
                                           │
                                    kNN match + ratio test
                                           │
                                    match_count ≥ threshold?
```

The `.npy` files are binary NumPy arrays — loading them is a simple memory-map
operation, orders of magnitude faster than re-running ORB or SIFT on the
reference image.

---

## Configuration

```bash
HOST=0.0.0.0  PORT=8000  WORKERS=1  LOG_LEVEL=info  RELOAD=false
```

```bash
PORT=9000 WORKERS=4 ./start.sh    # production
RELOAD=true ./start.sh            # development
```
