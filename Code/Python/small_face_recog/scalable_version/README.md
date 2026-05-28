# Face Recognition API

A simple REST API to help people with **prosopagnosia** link faces to people they know.
Register a reference photo for each person, then send any image to find out who is in it.

Built to scale — from a handful of faces to hundreds of millions.

---

## How it works

Each registered face is encoded into a 512-dimensional vector (ArcFace) and stored in
**Qdrant**, a vector database that uses an HNSW index for approximate nearest-neighbor
search. Detection queries run in O(log n) regardless of how many faces are registered,
making response times stay flat as the dataset grows.

---

## Requirements

- Python 3.10–3.12
- Docker (for Qdrant)

---

## Setup

```bash
chmod +x install.sh start.sh
./install.sh
```

No C++ compilation required — all dependencies install as pre-built wheels.

---

## Starting the server

Qdrant must be running before the server starts. Both steps only need to be done once
per machine restart:

```bash
docker compose up -d   # start Qdrant in the background
./start.sh             # start the API server
```

The API is available at `http://localhost:8000`.
Interactive docs are available at `http://localhost:8000/docs`.

> **First start only:** InsightFace downloads its models (~300 MB) to `~/.insightface/`.
> Qdrant data is persisted in a Docker volume and survives restarts.

---

## Endpoints

### `POST /faces/register`
Register a person by uploading a reference photo.

The **filename** (without extension) is used as the person's display identifier,
so name your files accordingly — e.g. `john_smith.jpg`.

```bash
curl -X POST http://localhost:8000/faces/register \
  -F "file=@john_smith.jpg"
```

**Tips for best results:**
- Use a clear, well-lit, front-facing portrait.
- One face per photo. If multiple faces are present, only the first is used.
- Minimum recommended size: 150×150 px.
- If recognition feels unreliable for someone, re-registering with a better photo is the first thing to try.
- You can register the same person multiple times with different photos (different angles, lighting) to improve coverage.

**Response:**
```json
{
  "face_id": "a1b2c3...",
  "filename": "john_smith.jpg",
  "message": "Face registered."
}
```

---

### `POST /faces/detect`
Scan an image for registered faces. Works on group photos.

```bash
curl -X POST http://localhost:8000/faces/detect \
  -F "file=@group_photo.jpg"
```

With a custom threshold or top_k:

```bash
curl -X POST "http://localhost:8000/faces/detect?threshold=0.35&top_k=3" \
  -F "file=@group_photo.jpg"
```

**Parameters:**

| Parameter   | Default | Description |
|-------------|---------|-------------|
| `threshold` | `0.40`  | Cosine distance cutoff. Lower = stricter. |
| `top_k`     | `5`     | How many candidates Qdrant returns per face before threshold filtering. |

**Threshold guide:**

| Value  | Behaviour |
|--------|-----------|
| `0.30` | Very strict — fewer false positives, may miss some matches |
| `0.40` | Default — good balance for clear photos |
| `0.55` | Lenient — catches more matches but risks false positives |

**Response:**
```json
{
  "filename": "group_photo.jpg",
  "faces_in_image": 3,
  "people_detected": 2,
  "threshold": 0.40,
  "results": [
    {
      "face_id": "a1b2c3...",
      "filename": "john_smith.jpg",
      "detected": true,
      "best_distance": 0.28,
      "threshold": 0.40,
      "confidence": 30.0
    }
  ]
}
```

Results are sorted by distance (closest match first).

---

### `GET /faces`
List registered faces, paginated.

```bash
curl "http://localhost:8000/faces?limit=100&offset=0"
```

---

### `DELETE /faces/{face_id}`
Remove a registered face.

```bash
curl -X DELETE http://localhost:8000/faces/a1b2c3...
```

---

### `GET /health`
Check that the server and Qdrant are up.

```bash
curl http://localhost:8000/health
```

---

## Storage

```
face_store/
└── images/
    └── <face_id>.jpg    ← original reference photos (disk)

Qdrant volume:           ← 512-d ArcFace vectors + {filename} payload (Docker volume)
```

Vectors and metadata live in Qdrant. Images stay on disk. There is no `index.json`.

---

## Scaling notes

| Faces      | Expected behaviour |
|------------|--------------------|
| < 100k     | Instant queries, minimal RAM |
| 1M–10M     | Still fast; Qdrant HNSW handles this range comfortably on a single node |
| 100M+      | Works; consider enabling Qdrant's quantization to cut memory usage by ~4× |

For very large datasets, Qdrant supports scalar and product quantization via its
config — no changes to this server's code are needed to enable it.
