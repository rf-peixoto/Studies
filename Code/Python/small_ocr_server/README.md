# OCR API Server

A lightweight REST API that extracts text from images using **Tesseract OCR** and **FastAPI**.

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.9+ | `python3 --version` |
| Tesseract OCR | Installed automatically by `install.sh` |

---

## Quick Start

```bash
# 1. Make scripts executable
chmod +x install.sh start.sh

# 2. Install system deps + Python venv
./install.sh

# 3. Start the server (default: http://0.0.0.0:8000)
./start.sh
```

---

## API Endpoints

### `GET /health`
Simple health check.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

### `POST /ocr`
Extract text from a **single** image (JPG, JPEG or PNG).

```bash
curl -X POST http://localhost:8000/ocr \
     -F "file=@/path/to/image.png"
```

**Response:**
```json
{
  "filename": "image.png",
  "text": "Hello, World!",
  "character_count": 13
}
```

---

### `POST /ocr/batch`
Extract text from **multiple** images in one request.

```bash
curl -X POST http://localhost:8000/ocr/batch \
     -F "files=@image1.png" \
     -F "files=@image2.jpg"
```

**Response:**
```json
{
  "results": [
    { "filename": "image1.png", "text": "...", "character_count": 42, "error": null },
    { "filename": "image2.jpg", "text": "...", "character_count": 17, "error": null }
  ]
}
```

---

## Interactive Docs

Once the server is running, open your browser at:

- **Swagger UI** → http://localhost:8000/docs  
- **ReDoc**      → http://localhost:8000/redoc

---

## Configuration

All settings are controlled via environment variables:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | TCP port |
| `WORKERS` | `1` | Uvicorn worker processes |
| `LOG_LEVEL` | `info` | Uvicorn log level |
| `RELOAD` | `false` | Hot-reload (dev mode) |

```bash
# Example: production on port 9000 with 4 workers
PORT=9000 WORKERS=4 ./start.sh

# Example: development mode with hot-reload
RELOAD=true ./start.sh
```
