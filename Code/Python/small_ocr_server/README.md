# OCR + Logo Detection API

A lightweight REST API that:
- **Extracts text** from images using Tesseract OCR
- **Detects client logos** using OpenCV ORB feature matching (no ML model needed)

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.9+ | `python3 --version` |
| Tesseract OCR | Auto-installed by `install.sh` |
| libgl1 (Linux) | Auto-installed by `install.sh` |

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
```json
{ "filename": "photo.png", "text": "Hello World", "character_count": 11 }
```

### `POST /ocr/batch`
```bash
curl -X POST http://localhost:8000/ocr/batch \
     -F "files=@img1.png" -F "files=@img2.jpg"
```

---

## Logo Detection Endpoints

The detector works purely on **visual shape features** — it ignores text entirely and focuses on the graphic structure of logos. It uses **ORB feature matching** with **Lowe's ratio test**, which handles logos at different scales, rotations, and with moderate perspective distortion.

---

### `POST /logos/register` — Upload a reference logo

```bash
curl -X POST "http://localhost:8000/logos/register?name=Acme+Corp" \
     -F "file=@acme_logo.png"
```

```json
{
  "logo_id": "d3f1a2b4-...",
  "name": "Acme Corp",
  "feature_count": 342,
  "message": "Logo registered successfully."
}
```

> **Tips for best results:**
> - Use a clean, isolated version of the logo (white or transparent background)
> - Minimum 100×100 px recommended
> - Avoid blurry or heavily JPEG-compressed images

---

### `GET /logos` — List registered logos

```bash
curl http://localhost:8000/logos
```

---

### `DELETE /logos/{logo_id}` — Remove a logo

```bash
curl -X DELETE http://localhost:8000/logos/d3f1a2b4-...
```

---

### `POST /logos/detect` — Find logos in an image

```bash
curl -X POST "http://localhost:8000/logos/detect?threshold=15" \
     -F "file=@document_photo.jpg"
```

```json
{
  "filename": "document_photo.jpg",
  "logos_checked": 3,
  "logos_detected": 1,
  "results": [
    {
      "logo_id": "d3f1a2b4-...",
      "name": "Acme Corp",
      "detected": true,
      "match_count": 47,
      "threshold": 15,
      "confidence": 100.0
    },
    {
      "logo_id": "e9c2b1a0-...",
      "name": "Other Corp",
      "detected": false,
      "match_count": 3,
      "threshold": 15,
      "confidence": 20.0
    }
  ]
}
```

#### Tuning the `threshold` parameter

| Scenario | Recommended threshold |
|---|---|
| Logo is large and clearly visible | `15–20` (default) |
| Logo is small or partially cropped | `8–12` |
| Logo appears at a strong angle | `8–12` |
| Many false positives | Increase to `25–40` |

---

## How Logo Detection Works

```
Query image                Reference logos
     │                          │
     ▼                          ▼
 ORB keypoints             ORB keypoints
 + descriptors             + descriptors
          \                   /
           ▼                 ▼
         BFMatcher (Hamming distance)
                   │
          Lowe's ratio test
          (filters ambiguous matches)
                   │
          good_matches >= threshold?
                   │
            YES → detected ✓
            NO  → not found ✗
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | TCP port |
| `WORKERS` | `1` | Uvicorn worker processes |
| `LOG_LEVEL` | `info` | Log verbosity |
| `RELOAD` | `false` | Hot-reload (dev mode) |

```bash
PORT=9000 WORKERS=4 ./start.sh
RELOAD=true ./start.sh
```
