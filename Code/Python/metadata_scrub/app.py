"""scrub -- local metadata removal and recompression.

Run:  python app.py     then open http://127.0.0.1:5000

Binds to loopback by default. Nothing leaves the machine: no external fonts,
no CDN, no analytics, no network calls of any kind during processing.
"""
from __future__ import annotations

import atexit
import json
import os

from flask import (Flask, Response, abort, jsonify, render_template, request,
                   send_file)

from jobs import Registry
from scrub import media, pdfs

MAX_MB = int(os.environ.get("SCRUB_MAX_MB", "2048"))
WORKERS = int(os.environ.get("SCRUB_WORKERS", "2"))
TTL = int(os.environ.get("SCRUB_TTL", "1800"))
MAX_FILES = int(os.environ.get("SCRUB_MAX_FILES", "40"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False

registry = Registry(workers=WORKERS, ttl=TTL)
atexit.register(registry.shutdown)


@app.after_request
def harden(resp: Response) -> Response:
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error=f"Upload exceeds the {MAX_MB} MB limit. "
                         f"Raise it with SCRUB_MAX_MB if you need more."), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/capabilities")
def capabilities():
    return jsonify(
        video_codecs=media.available_video_encoders(),
        audio_codecs=media.available_audio_encoders(),
        max_mb=MAX_MB,
        max_files=MAX_FILES,
        ttl_minutes=TTL // 60,
        workers=WORKERS,
    )


@app.post("/api/password")
def password():
    body = request.get_json(silent=True) or {}
    pw, bits = pdfs.generate_password(
        length=int(body.get("length", 24)),
        symbols=bool(body.get("symbols", True)),
        avoid_ambiguous=bool(body.get("avoid_ambiguous", True)),
    )
    return jsonify(password=pw, bits=round(bits))


@app.post("/api/jobs")
def create_job():
    uploads = request.files.getlist("files")
    if not uploads:
        return jsonify(error="No files received."), 400
    if len(uploads) > MAX_FILES:
        return jsonify(error=f"Send at most {MAX_FILES} files per run."), 400

    try:
        opts = json.loads(request.form.get("options", "{}"))
    except ValueError:
        return jsonify(error="Options were not valid JSON."), 400
    if not isinstance(opts, dict):
        return jsonify(error="Options must be an object."), 400

    job = registry.new_job(opts)
    for i, upload in enumerate(uploads):
        if not upload.filename:
            continue
        job.add(upload, i)
    if not job.items:
        job.cleanup()
        return jsonify(error="No usable files in the upload."), 400

    registry.submit(job)
    return jsonify(job.state()), 202


@app.get("/api/jobs/<job_id>")
def job_state(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    return jsonify(job.state())


@app.get("/api/jobs/<job_id>/files/<item_id>")
def download(job_id: str, item_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    item = next((i for i in job.items if i.id == item_id), None)
    if item is None or item.status != "done" or not os.path.exists(item.out_path):
        abort(404)
    return send_file(item.out_path, as_attachment=True,
                     download_name=item.out_name)


@app.get("/api/jobs/<job_id>/archive")
def archive(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    buf = registry.zip_bytes(job)
    if buf.getbuffer().nbytes == 0:
        abort(404)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"scrubbed_{job.id[:8]}.zip")


@app.post("/api/jobs/<job_id>/forget")
def forget(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    with registry.lock:
        registry.jobs.pop(job_id, None)
    job.cleanup()
    return jsonify(ok=True)


if __name__ == "__main__":
    host = os.environ.get("SCRUB_HOST", "127.0.0.1")
    port = int(os.environ.get("SCRUB_PORT", "5000"))
    print(f"scrub -> http://{host}:{port}  "
          f"(limit {MAX_MB} MB, {WORKERS} workers, files held {TTL // 60} min)")
    app.run(host=host, port=port, threaded=True, debug=False)
