# Face Recognition API

A simple REST API to help people with **prosopagnosia** link faces to people they know.
Register a reference photo for each person, then send any image to find out who is in it.

---

## Setup

```bash
chmod +x install.sh start.sh
./install.sh
```

No compilation required — all dependencies install as pre-built wheels.

---

## Starting the server

```bash
./start.sh
```

The server starts at `http://localhost:8000`.
Interactive API docs are available at `http://localhost:8000/docs`.

> **First start only:** InsightFace will download its face recognition models (~300 MB) to `~/.insightface/`. This happens once and is automatic.

---

## Endpoints

### `POST /faces/register`
Register a person by uploading a reference photo.

```bash
curl -X POST http://localhost:8000/faces/register \
  -F "file=@john.jpg" \
  -F "name=John Smith"
```

**Tips for best results:**
- Use a clear, well-lit, front-facing portrait.
- One face per registration photo. If multiple faces are present, only the first is used.
- Minimum recommended size: 150×150 px.
- If recognition feels unreliable for someone, re-registering with a better photo is the first thing to try.

**Response:**
```json
{
  "face_id": "a1b2c3...",
  "name": "John Smith",
  "message": "Face registered and embedding cached."
}
```

---

### `POST /faces/detect`
Scan an image for any registered faces. Works on group photos.

```bash
curl -X POST http://localhost:8000/faces/detect \
  -F "file=@group_photo.jpg"
```

With a custom threshold (default is `0.40`):

```bash
curl -X POST "http://localhost:8000/faces/detect?threshold=0.35" \
  -F "file=@group_photo.jpg"
```

**Threshold guide:**

| Value | Behaviour |
|-------|-----------|
| `0.30` | Very strict — fewer false positives, may miss some matches |
| `0.40` | Default — good balance for clear photos |
| `0.55` | Lenient — catches more matches but risks false positives |

**Response:**
```json
{
  "filename": "group_photo.jpg",
  "faces_in_image": 3,
  "people_checked": 5,
  "people_detected": 2,
  "threshold": 0.40,
  "results": [
    {
      "face_id": "a1b2c3...",
      "name": "John Smith",
      "detected": true,
      "best_distance": 0.28,
      "threshold": 0.40,
      "confidence": 30.0
    },
    ...
  ]
}
```

Results are sorted with detected people first, then by distance.

---

### `GET /faces`
List all registered people.

```bash
curl http://localhost:8000/faces
```

---

### `DELETE /faces/{face_id}`
Remove a registered person and their data.

```bash
curl -X DELETE http://localhost:8000/faces/a1b2c3...
```

---

### `GET /health`
Check that the server is running.

```bash
curl http://localhost:8000/health
```

---

## Storage

All data is stored locally in the `face_store/` directory created next to the server file:

```
face_store/
├── index.json                  ← registry of all people and their metadata
├── <face_id>.jpg               ← original reference photos
└── <face_id>_embedding.npy     ← cached 512-d ArcFace embeddings
```

Embeddings are computed once at registration and cached — detection never re-processes the reference photos.

---

## Accuracy notes

- The underlying model is **InsightFace buffalo_l** (ArcFace ResNet50), one of the most accurate publicly available face recognition models.
- Similarity is measured as **cosine distance** on 512-d embeddings. Values closer to 0 mean a stronger match.
- Real-world accuracy depends heavily on photo quality. Well-lit, front-facing photos significantly outperform candid or low-resolution ones.
- Multiple reference photos of the same person are not supported in a single registration call, but you can register the same person **multiple times** under the same name with different photos to improve coverage across angles and lighting conditions.
