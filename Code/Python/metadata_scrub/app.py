"""scrub -- local metadata removal and recompression.

Run:  python3 app.py     then open http://127.0.0.1:5000

On start it asks two questions: how large an upload to accept, and how long to
keep files. Both have environment-variable equivalents for unattended use, and
the prompts are skipped automatically when there is no terminal attached.

Binds to loopback by default. Nothing leaves the machine: no external fonts, no
CDN, no analytics, no network calls of any kind during processing.
"""
from __future__ import annotations

import atexit
import json
import os
import sys

from flask import (Flask, Response, abort, jsonify, render_template, request,
                   send_file)

from jobs import Registry
from scrub import media, pdfs

CONFIG = {
    "max_mb": int(os.environ.get("SCRUB_MAX_MB", "2048")),
    "ttl": int(os.environ.get("SCRUB_TTL", "1800")),
    "workers": int(os.environ.get("SCRUB_WORKERS", "2")),
    "max_files": int(os.environ.get("SCRUB_MAX_FILES", "40")),
    "max_jobs": int(os.environ.get("SCRUB_MAX_JOBS", "8")),
}

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
registry: Registry | None = None


# --------------------------------------------------------------------------
# startup questions
# --------------------------------------------------------------------------

DIM, BOLD, AMBER, OFF = "\033[2m", "\033[1m", "\033[33m", "\033[0m"


def _ask(question: str, default: str, hint: str = "") -> str:
    if hint:
        print(f"  {DIM}{hint}{OFF}")
    try:
        answer = input(f"  {question} {DIM}[{default}]{OFF} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer or default


def _ask_int(question: str, default: int, hint: str = "",
             low: int = 0, high: int = 10 ** 9) -> int:
    while True:
        raw = _ask(question, str(default), hint)
        try:
            value = int(float(raw))
        except ValueError:
            print(f"  {AMBER}Not a number. Try again.{OFF}")
            continue
        if not low <= value <= high:
            print(f"  {AMBER}Enter something between {low} and {high}.{OFF}")
            continue
        return value


def prompt_settings() -> None:
    """Ask the two questions that decide how much of the disk this can use."""
    if not sys.stdin.isatty() or "--no-prompt" in sys.argv:
        return

    print(f"\n  {BOLD}scrub{OFF} {DIM}— setup{OFF}")
    print(f"  {DIM}{'─' * 56}{OFF}")

    CONFIG["max_mb"] = _ask_int(
        "Maximum upload size, in MB?", CONFIG["max_mb"],
        "Applies to one batch in total, not per file.",
        low=1, high=1024 * 1024)

    minutes = _ask_int(
        "Keep uploaded files for how many minutes?", CONFIG["ttl"] // 60,
        "0 keeps them until you delete them yourself.",
        low=0, high=60 * 24 * 365)
    CONFIG["ttl"] = minutes * 60

    print(f"  {DIM}{'─' * 56}{OFF}")
    retention = ("kept until deleted by hand" if minutes == 0
                 else f"deleted after {minutes} min")
    print(f"  limit {BOLD}{CONFIG['max_mb']} MB{OFF} · files {BOLD}{retention}{OFF}")
    if minutes == 0:
        print(f"  {AMBER}Nothing will be cleaned up on its own. "
              f"Files stay on disk until you remove them.{OFF}")
    print()


# --------------------------------------------------------------------------
# app plumbing
# --------------------------------------------------------------------------

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
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    resp.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), interest-cohort=()")
    return resp


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error=f"Upload exceeds the {CONFIG['max_mb']} MB limit for "
                         f"this session. Restart and raise it, or send fewer "
                         f"files at a time."), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/capabilities")
def capabilities():
    return jsonify(
        video_codecs=media.available_video_encoders(),
        audio_codecs=media.available_audio_encoders(),
        max_mb=CONFIG["max_mb"],
        max_files=CONFIG["max_files"],
        ttl_minutes=CONFIG["ttl"] // 60,
        keeps_forever=CONFIG["ttl"] <= 0,
        workers=CONFIG["workers"],
        threads_each=media.encoder_threads(),
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
    """Upload and inspect. Nothing is modified until /run is called."""
    uploads = request.files.getlist("files")
    if not uploads:
        return jsonify(error="No files received."), 400
    if len(uploads) > CONFIG["max_files"]:
        return jsonify(error=f"Send at most {CONFIG['max_files']} files per run."), 400

    job = registry.new_job()
    if job is None:
        return jsonify(error="Too many jobs are already in flight. Finish or "
                             "delete one and try again."), 429

    for i, upload in enumerate(uploads):
        if upload.filename:
            job.add(upload, i)
    if not job.items:
        registry.forget(job.id)
        return jsonify(error="No usable files in the upload."), 400

    registry.inspect(job)
    return jsonify(job.state()), 202


@app.post("/api/jobs/<job_id>/run")
def run_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    if job.phase == "processing":
        return jsonify(error="This job is already running."), 409

    opts = request.get_json(silent=True)
    if not isinstance(opts, dict):
        return jsonify(error="Options must be a JSON object."), 400
    if not any(i.status == "ready" for i in job.items):
        return jsonify(error="Nothing left to process in this job."), 400

    registry.start(job, opts)
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
    job.touch()
    return send_file(item.out_path, as_attachment=True,
                     download_name=item.out_name)


@app.get("/api/jobs/<job_id>/archive")
def archive(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    path = registry.zip_path(job)
    if path is None:
        abort(404)
    job.touch()
    return send_file(path, mimetype="application/zip", as_attachment=True,
                     download_name=f"scrubbed_{job.id[:8]}.zip")


@app.post("/api/jobs/<job_id>/forget")
def forget(job_id: str):
    if not registry.forget(job_id):
        abort(404)
    return jsonify(ok=True)


def main() -> None:
    global registry
    prompt_settings()
    os.environ["SCRUB_WORKERS"] = str(CONFIG["workers"])   # read by media.py
    app.config["MAX_CONTENT_LENGTH"] = CONFIG["max_mb"] * 1024 * 1024
    registry = Registry(workers=CONFIG["workers"], ttl=CONFIG["ttl"],
                        max_jobs=CONFIG["max_jobs"])
    atexit.register(registry.shutdown)

    host = os.environ.get("SCRUB_HOST", "127.0.0.1")
    port = int(os.environ.get("SCRUB_PORT", "5000"))
    retention = ("kept until deleted" if CONFIG["ttl"] <= 0
                 else f"held {CONFIG['ttl'] // 60} min")
    print(f"  scrub -> http://{host}:{port}   "
          f"({CONFIG['max_mb']} MB limit, {CONFIG['workers']} workers "
          f"x {media.encoder_threads()} threads, files {retention})\n")
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
