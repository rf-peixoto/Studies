"""Job tracking.

Work runs in a thread pool. Threads rather than processes because the expensive
parts (PyAV encode/decode, Pillow, zlib) release the GIL in C, so they genuinely
run in parallel, and sharing the progress state stays trivial.

Every job owns a directory under one temp root. Nothing is written anywhere
else, nothing is named from user input, and a reaper thread deletes each job
directory once it passes its TTL so uploads do not accumulate on disk.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from scrub import detect, images, media, pdfs

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
    status: str = "queued"      # queued | running | done | error | skipped
    pct: int = 0
    stage: str = "waiting"
    size_in: int = 0
    size_out: int = 0
    error: str = ""
    out_path: str = ""
    out_name: str = ""
    src_path: str = ""
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
    def __init__(self, root: str, opts: dict, ttl: int):
        self.id = uuid.uuid4().hex
        self.dir = os.path.join(root, self.id)
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        self.opts = opts
        self.items: list[Item] = []
        self.created = time.time()
        self.expires = self.created + ttl
        self.lock = threading.Lock()
        self.password = ""      # shown once, never persisted to disk

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

    def state(self) -> dict:
        with self.lock:
            items = [i.public() for i in self.items]
        active = [i for i in items if i["status"] in ("queued", "running")]
        total_in = sum(i["size_in"] for i in items)
        total_out = sum(i["size_out"] for i in items if i["status"] == "done")
        return {
            "id": self.id,
            "items": items,
            "finished": not active,
            "total_in": total_in,
            "total_out": total_out,
            "seconds_left": max(0, int(self.expires - time.time())),
        }

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


class Registry:
    def __init__(self, workers: int = 2, ttl: int = 1800):
        self.root = tempfile.mkdtemp(prefix="scrub_")
        os.chmod(self.root, 0o700)
        self.ttl = ttl
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers,
                                       thread_name_prefix="scrub")
        threading.Thread(target=self._reaper, daemon=True).start()

    def new_job(self, opts: dict) -> Job:
        job = Job(self.root, opts, self.ttl)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def submit(self, job: Job) -> None:
        for item in job.items:
            if item.status == "queued":
                self.pool.submit(self._run, job, item)

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
            item.stage = "reading"
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

    def zip_bytes(self, job: Job) -> io.BytesIO:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
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
        buf.seek(0)
        return buf

    def _reaper(self) -> None:
        while True:
            time.sleep(30)
            now = time.time()
            with self.lock:
                stale = [j for j in self.jobs.values() if j.expires < now]
                for job in stale:
                    self.jobs.pop(job.id, None)
            for job in stale:
                job.cleanup()

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False)
        shutil.rmtree(self.root, ignore_errors=True)
