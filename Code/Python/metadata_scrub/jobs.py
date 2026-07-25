"""Job tracking.

A job has two phases. Uploading runs inspection only: every file is classified
and read for metadata, and nothing is modified. The user sees what is in their
files and then chooses settings. Processing starts on a second, explicit call.

Work runs in a thread pool rather than processes because the expensive parts
(PyAV encode/decode, Pillow, zlib) release the GIL in C, so they genuinely run
in parallel while progress state stays trivial to share.

Every job owns a directory under one temp root. Nothing is written anywhere
else, nothing is named from user input, and a reaper thread deletes each job
directory once it passes its TTL. A TTL of 0 means keep until told otherwise.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from scrub import detect, images, inspector, media, pdfs

MAX_LOG_LINES = 400


def _safe_stem(name: str) -> str:
    stem = os.path.splitext(os.path.basename(name))[0]
    keep = [c if (c.isalnum() or c in "-_. ") else "_" for c in stem]
    out = "".join(keep).strip(" .")[:80]
    return out or "file"


@dataclass
class Item:
    id: str
    name: str
    kind: str = "unknown"
    status: str = "inspecting"   # inspecting|ready|queued|running|done|error|skipped
    pct: int = 0
    stage: str = "reading"
    size_in: int = 0
    size_out: int = 0
    error: str = ""
    out_path: str = ""
    out_name: str = ""
    src_path: str = ""
    inspection: dict = field(default_factory=dict)
    log: list = field(default_factory=list)

    def public(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("src_path", "out_path", "log")}
        d["log"] = self.log[-40:]
        if self.size_in and self.size_out:
            d["delta"] = round(100.0 * (self.size_in - self.size_out) / self.size_in, 1)
        else:
            d["delta"] = None
        return d


class Job:
    def __init__(self, root: str, ttl: int):
        self.id = uuid.uuid4().hex
        self.dir = os.path.join(root, self.id)
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        self.opts: dict = {}
        self.items: list[Item] = []
        self.created = time.time()
        self.ttl = ttl
        # ttl 0 means never expire; the user deletes it when they are done.
        self.expires = None if ttl <= 0 else self.created + ttl
        self.phase = "inspecting"     # inspecting | ready | processing | finished
        self.lock = threading.Lock()

    def add(self, upload, index: int) -> Item:
        item = Item(id=f"{index:03d}", name=os.path.basename(upload.filename or "file"))
        src = os.path.join(self.dir, f"in_{item.id}")
        upload.save(src)
        item.src_path = src
        item.size_in = os.path.getsize(src)
        item.kind = detect.sniff(src)
        if item.kind == "unknown":
            item.status = "skipped"
            item.stage = "unsupported format"
            item.error = "not a recognised image, audio, video or PDF file"
        self.items.append(item)
        return item

    def touch(self) -> None:
        """Push the deletion deadline out while the job is still in use."""
        if self.ttl > 0:
            self.expires = time.time() + self.ttl

    def state(self) -> dict:
        with self.lock:
            items = [i.public() for i in self.items]
            phase = self.phase
        pending = [i for i in items
                   if i["status"] in ("inspecting", "queued", "running")]
        totals = {"high": 0, "medium": 0, "active": 0, "low": 0}
        for i in items:
            for level, n in (i.get("inspection") or {}).get("counts", {}).items():
                totals[level] = totals.get(level, 0) + n
        return {
            "id": self.id,
            "phase": phase,
            "items": items,
            "finished": phase == "finished" and not pending,
            "inspected": phase in ("ready", "processing", "finished"),
            "findings": totals,
            "total_in": sum(i["size_in"] for i in items),
            "total_out": sum(i["size_out"] for i in items
                             if i["status"] == "done"),
            "seconds_left": (None if self.expires is None
                             else max(0, int(self.expires - time.time()))),
        }

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


class Registry:
    def __init__(self, workers: int = 2, ttl: int = 1800, max_jobs: int = 8):
        self.root = tempfile.mkdtemp(prefix="scrub_")
        os.chmod(self.root, 0o700)
        self.ttl = ttl
        self.max_jobs = max_jobs
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers,
                                       thread_name_prefix="scrub")
        threading.Thread(target=self._reaper, daemon=True).start()

    # -- lifecycle ---------------------------------------------------------

    def new_job(self) -> Job | None:
        """None when too many jobs are already live -- a crude admission gate."""
        with self.lock:
            live = sum(1 for j in self.jobs.values()
                       if j.phase in ("inspecting", "ready", "processing"))
            if live >= self.max_jobs:
                return None
            job = Job(self.root, self.ttl)
            self.jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def inspect(self, job: Job) -> None:
        for item in job.items:
            if item.status == "inspecting":
                self.pool.submit(self._inspect_one, job, item)

    def _inspect_one(self, job: Job, item: Item) -> None:
        try:
            result = inspector.inspect(item.src_path, item.kind,
                                       job.opts.get("pdf_open_password", ""))
        except Exception as exc:
            result = {"findings": [], "counts": {},
                      "error": f"{type(exc).__name__}: {exc}"}
        with job.lock:
            item.inspection = result
            item.status = "ready"
            item.stage = "inspected"
            counts = result.get("counts", {})
            notable = counts.get("high", 0) + counts.get("active", 0)
            item.log.append(
                f"{time.strftime('%H:%M:%S')} inspected: "
                f"{len(result.get('findings', []))} finding(s)"
                + (f", {notable} worth attention" if notable else ""))
            if all(i.status in ("ready", "skipped") for i in job.items):
                job.phase = "ready"

    def start(self, job: Job, opts: dict) -> None:
        with job.lock:
            job.opts = opts
            job.phase = "processing"
            for item in job.items:
                if item.status == "ready":
                    item.status = "queued"
                    item.stage = "waiting"
                    item.pct = 0
        job.touch()
        for item in job.items:
            if item.status == "queued":
                self.pool.submit(self._run, job, item)

    # -- processing --------------------------------------------------------

    def _run(self, job: Job, item: Item) -> None:
        def log(msg: str) -> None:
            with job.lock:
                item.log.append(f"{time.strftime('%H:%M:%S')} {msg}")
                del item.log[:-MAX_LOG_LINES]

        def progress(pct: int) -> None:
            with job.lock:
                item.pct = max(item.pct, min(99, int(pct)))

        with job.lock:
            item.status = "running"
            item.stage = "cleaning"
            item.pct = 1
        started = time.time()
        work_dir = os.path.join(job.dir, f"w_{item.id}")
        os.makedirs(work_dir, exist_ok=True)

        try:
            log(f"{item.name} -> {item.kind}, {detect.human_size(item.size_in)}")
            if item.kind == "image":
                out = images.process(item.src_path, work_dir, job.opts, log, progress)
            elif item.kind == "video":
                out = media.process_video(item.src_path, work_dir, job.opts, log, progress)
            elif item.kind == "audio":
                out = media.process_audio(item.src_path, work_dir, job.opts, log, progress)
            elif item.kind == "pdf":
                out = pdfs.process(item.src_path, work_dir, job.opts, log, progress)
            else:
                raise ValueError("unsupported file type")

            ext = os.path.splitext(out)[1]
            with job.lock:
                item.out_path = out
                item.out_name = f"{_safe_stem(item.name)}.scrubbed{ext}"
                item.size_out = os.path.getsize(out)
                item.pct = 100
                item.status = "done"
                item.stage = "clean"
            delta = 100.0 * (item.size_in - item.size_out) / max(item.size_in, 1)
            verdict = (f"{delta:.1f}% smaller" if delta >= 0
                       else f"{-delta:.1f}% larger")
            log(f"done in {time.time() - started:.1f}s -- "
                f"{detect.human_size(item.size_in)} -> "
                f"{detect.human_size(item.size_out)} ({verdict})")
        except Exception as exc:
            with job.lock:
                item.status = "error"
                item.stage = "failed"
                item.error = f"{type(exc).__name__}: {exc}"[:300]
            log(f"failed: {item.error}")
        finally:
            # The upload is gone the moment we no longer need it.
            try:
                os.remove(item.src_path)
            except OSError:
                pass
            with job.lock:
                if all(i.status in ("done", "error", "skipped") for i in job.items):
                    job.phase = "finished"
            job.touch()

    # -- output ------------------------------------------------------------

    def zip_path(self, job: Job) -> str | None:
        """Build the archive on disk. Holding it in memory would mean holding
        every result in memory at once, which for a batch of video is fatal."""
        path = os.path.join(job.dir, "results.zip")
        wrote = 0
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
            used: set[str] = set()
            for item in job.items:
                if item.status != "done" or not os.path.exists(item.out_path):
                    continue
                name = item.out_name
                n = 1
                while name in used:
                    stem, ext = os.path.splitext(item.out_name)
                    name = f"{stem}_{n}{ext}"
                    n += 1
                used.add(name)
                zf.write(item.out_path, name)
                wrote += 1
        if not wrote:
            os.remove(path)
            return None
        return path

    # -- housekeeping ------------------------------------------------------

    def _reaper(self) -> None:
        while True:
            time.sleep(30)
            now = time.time()
            with self.lock:
                stale = [j for j in self.jobs.values()
                         if j.expires is not None and j.expires < now]
                for job in stale:
                    self.jobs.pop(job.id, None)
            for job in stale:
                job.cleanup()

    def forget(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.pop(job_id, None)
        if job is None:
            return False
        job.cleanup()
        return True

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False)
        shutil.rmtree(self.root, ignore_errors=True)
