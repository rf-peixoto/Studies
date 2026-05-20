#!/usr/bin/env python3
import asyncio
import gzip
import logging
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import py7zr
import rarfile
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import RPCError
from telethon.tl.types import DocumentAttributeFilename

# =========================
# Config
# =========================

load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()

KEYWORDS_FILE = Path(os.getenv("KEYWORDS_FILE", "keywords.txt"))

_allowed_group_raw = os.getenv("ALLOWED_GROUP_ID", "").strip()
ALLOWED_GROUP_ID = int(_allowed_group_raw) if _allowed_group_raw else None

SESSION_NAME = "keyword_parser_bot"

WORK_ROOT = Path("./work").resolve()
RESULTS_DIR_NAME = "findings"

DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 10
STATUS_INTERVAL_SECONDS = 20

MAX_KEYWORDS = 5000

LOG_FILE = "bot.log"
PROCESS_LOG_FILE = "processed_files.log"

ALLOWED_ARCHIVE_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".tar", ".gz", ".tgz",
    ".tar.gz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".svg", ".ico", ".heic", ".heif", ".avif",
}

TEXT_EXTENSIONS_PREFERRED = {
    ".txt", ".log", ".csv", ".json", ".xml", ".html", ".htm", ".js", ".ts",
    ".py", ".php", ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb",
    ".sh", ".ps1", ".conf", ".cfg", ".ini", ".env", ".yaml", ".yml", ".sql",
    ".md", ".rtf", ".ndjson", ".jsonl", ".tsv", ".lst", ".list",
}

# =========================
# Logging
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)

logging.getLogger("telethon").setLevel(logging.WARNING)
log = logging.getLogger("keyword-telethon-bot")


@dataclass
class ScanSummary:
    input_name: str
    password_used: bool
    keywords_loaded: int = 0
    files_scanned: int = 0
    files_skipped: int = 0
    matches: int = 0
    result_archive: Path | None = None
    error: str | None = None


def human_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"

    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


def safe_name(value: str, fallback: str = "file") -> str:
    value = value.strip()
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = value.strip("._-")
    return value[:180] or fallback


def archive_suffix(path: Path) -> str:
    name = path.name.lower()

    for ext in sorted(ALLOWED_ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if name.endswith(ext):
            return ext

    return path.suffix.lower()


def is_supported_archive(path: Path) -> bool:
    return archive_suffix(path) in ALLOWED_ARCHIVE_EXTENSIONS


def is_supported_plain_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS_PREFERRED


def is_image_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def get_document_filename(message) -> str:
    if not message.document:
        return "uploaded_file"

    for attr in message.document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name or "uploaded_file"

    return "uploaded_file"


def get_document_size(message) -> int | None:
    if message.document and getattr(message.document, "size", None):
        return int(message.document.size)
    return None


def log_file_entry(event, filename: str, filesize: int | None) -> None:
    sender = event.sender
    username = getattr(sender, "username", None) or "-"
    user_id = getattr(sender, "id", None) or event.sender_id or "-"

    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | "
        f"{username} | {user_id} | {filename} | {human_size(filesize)}\n"
    )

    with open(PROCESS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"Keywords file not found: {KEYWORDS_FILE}")

    keywords = []
    seen = set()

    with KEYWORDS_FILE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            keyword = line.strip()

            if not keyword or keyword.startswith("#"):
                continue

            if keyword not in seen:
                seen.add(keyword)
                keywords.append(keyword)

    if not keywords:
        raise ValueError("Keywords file is empty.")

    if len(keywords) > MAX_KEYWORDS:
        raise ValueError(f"Too many keywords. Limit is {MAX_KEYWORDS}.")

    return keywords


def ensure_inside(base: Path, target: Path) -> None:
    base = base.resolve()
    target = target.resolve()

    if base != target and base not in target.parents:
        raise ValueError(f"Unsafe archive path traversal blocked: {target}")


def safe_extract_zip(path: Path, dest: Path, password: str | None) -> None:
    pwd = password.encode() if password else None

    with zipfile.ZipFile(path) as zf:
        for member in zf.infolist():
            ensure_inside(dest, dest / member.filename)

        zf.extractall(dest, pwd=pwd)


def safe_extract_tar(path: Path, dest: Path) -> None:
    with tarfile.open(path) as tf:
        for member in tf.getmembers():
            ensure_inside(dest, dest / member.name)

        tf.extractall(dest)


def safe_extract_7z(path: Path, dest: Path, password: str | None) -> None:
    with py7zr.SevenZipFile(path, mode="r", password=password) as z:
        for name in z.getnames():
            ensure_inside(dest, dest / name)

        z.extractall(path=dest)


def safe_extract_rar(path: Path, dest: Path, password: str | None) -> None:
    with rarfile.RarFile(path) as rf:
        for member in rf.infolist():
            ensure_inside(dest, dest / member.filename)

        rf.extractall(path=dest, pwd=password)


def extract_gzip_single_file(path: Path, dest: Path) -> None:
    output_name = path.name

    if output_name.lower().endswith(".gz"):
        output_name = output_name[:-3]

    if not output_name:
        output_name = "decompressed_gzip_output"

    output_path = dest / output_name
    ensure_inside(dest, output_path)

    with gzip.open(path, "rb") as src, output_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)


def extract_archive(path: Path, dest: Path, password: str | None) -> None:
    suffix = archive_suffix(path)

    if suffix == ".zip":
        safe_extract_zip(path, dest, password)
    elif suffix == ".7z":
        safe_extract_7z(path, dest, password)
    elif suffix == ".rar":
        safe_extract_rar(path, dest, password)
    elif suffix in {
        ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
    }:
        safe_extract_tar(path, dest)
    elif suffix == ".gz":
        extract_gzip_single_file(path, dest)
    else:
        raise ValueError(f"Unsupported archive type: {suffix}")


def looks_like_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS_PREFERRED:
        return True

    try:
        with path.open("rb") as f:
            chunk = f.read(4096)

        return b"\x00" not in chunk

    except OSError:
        return False


def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            yield p


def grep_recursive(input_dir: Path, findings_dir: Path, keywords: list[str]) -> tuple[int, int, int]:
    files_scanned = 0
    files_skipped = 0
    total_matches = 0

    compiled = [(kw, re.compile(re.escape(kw), re.IGNORECASE)) for kw in keywords]
    handles = {}

    try:
        for file_path in iter_files(input_dir):
            if not looks_like_text_file(file_path):
                files_skipped += 1
                continue

            files_scanned += 1

            try:
                rel = file_path.relative_to(input_dir)

                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, start=1):
                        for keyword, pattern in compiled:
                            if pattern.search(line):
                                out_name = safe_name(keyword, fallback="keyword") + ".txt"
                                out_path = findings_dir / out_name

                                if out_name not in handles:
                                    handles[out_name] = out_path.open(
                                        "a",
                                        encoding="utf-8",
                                        errors="replace",
                                    )

                                handles[out_name].write(f"{rel}:{line_no}: {line}")
                                total_matches += 1

            except OSError:
                files_skipped += 1

    finally:
        for handle in handles.values():
            handle.close()

    return files_scanned, files_skipped, total_matches


def make_results_archive(findings_dir: Path, job_dir: Path) -> Path:
    archive_base = job_dir / "findings"

    archive_path = shutil.make_archive(
        base_name=str(archive_base),
        format="zip",
        root_dir=findings_dir,
    )

    return Path(archive_path)


def format_summary(summary: ScanSummary) -> str:
    if summary.error:
        return (
            "Processing failed.\n\n"
            f"Input: {summary.input_name}\n"
            f"Error: {summary.error}"
        )

    return (
        "Processing completed.\n\n"
        f"Input: {summary.input_name}\n"
        f"Password supplied: {'yes' if summary.password_used else 'no'}\n"
        f"Keywords loaded: {summary.keywords_loaded}\n"
        f"Files scanned: {summary.files_scanned}\n"
        f"Files skipped: {summary.files_skipped}\n"
        f"Matches found: {summary.matches}"
    )


async def send_status(event, text: str) -> None:
    try:
        await event.reply(text)
    except RPCError:
        log.exception("Failed to send status message.")


async def react_working(event) -> None:
    try:
        await event.message.react("👀")
    except Exception:
        log.debug("Could not react to message.", exc_info=True)


class DownloadProgress:
    def __init__(self, filename: str):
        self.filename = filename
        self.last_log = 0.0

    def __call__(self, current: int, total: int) -> None:
        now = asyncio.get_event_loop().time()

        if now - self.last_log < DOWNLOAD_PROGRESS_INTERVAL_SECONDS:
            return

        self.last_log = now

        if total:
            pct = (current / total) * 100
            log.info(
                "Downloading %s: %s / %s %.2f%%",
                self.filename,
                human_size(current),
                human_size(total),
                pct,
            )
        else:
            log.info("Downloading %s: %s", self.filename, human_size(current))


async def handle_analyze(event) -> None:
    if event.is_private:
        return

    if ALLOWED_GROUP_ID is not None and event.chat_id != ALLOWED_GROUP_ID:
        return

    if not event.message.document:
        return

    text = event.raw_text or ""

    if not text.startswith("/analyze"):
        return

    filename = get_document_filename(event.message)

    if is_image_filename(filename):
        return

    safe_file_name = safe_name(filename, fallback="uploaded_file")
    safe_file_path = Path(safe_file_name)

    is_archive = is_supported_archive(safe_file_path)
    is_plain_text = is_supported_plain_text(safe_file_path)

    if not is_archive and not is_plain_text:
        await event.reply(
            "Unsupported file type. Supported archives: zip, 7z, rar, tar, gz, tgz, "
            "tar.gz, tar.bz2, tar.xz. Supported plain files: txt, csv, json, sql, "
            "log, xml, html, js, py, conf, ini, env, yaml, yml, md and similar."
        )
        return

    await react_working(event)

    parts = text.split(maxsplit=1)
    password = parts[1].strip() if len(parts) > 1 else None

    filesize = get_document_size(event.message)
    log_file_entry(event, filename, filesize)

    await event.reply("File received. Processing started.")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    job_dir = Path(tempfile.mkdtemp(prefix="tg_keyword_job_", dir=WORK_ROOT))
    downloaded_path = job_dir / safe_file_name
    input_dir = job_dir / "input"
    findings_dir = job_dir / RESULTS_DIR_NAME

    input_dir.mkdir()
    findings_dir.mkdir()

    summary = ScanSummary(
        input_name=filename,
        password_used=bool(password) and is_archive,
    )

    try:
        await event.client.download_media(
            event.message,
            file=str(downloaded_path),
            progress_callback=DownloadProgress(filename),
        )

        keywords = load_keywords()
        summary.keywords_loaded = len(keywords)

        if is_archive:
            await send_status(event, "Download finished. Extracting archive.")
            extract_archive(downloaded_path, input_dir, password)
        else:
            plain_target = input_dir / safe_file_name
            ensure_inside(input_dir, plain_target)
            shutil.copy2(downloaded_path, plain_target)

        await send_status(event, "Searching keywords.")

        files_scanned, files_skipped, matches = grep_recursive(
            input_dir=input_dir,
            findings_dir=findings_dir,
            keywords=keywords,
        )

        summary.files_scanned = files_scanned
        summary.files_skipped = files_skipped
        summary.matches = matches

        if matches == 0:
            await event.reply(format_summary(summary) + "\n\nNo findings archive was generated.")
            return

        result_archive = make_results_archive(findings_dir, job_dir)
        summary.result_archive = result_archive

        await event.reply(format_summary(summary))

        await event.client.send_file(
            entity=event.chat_id,
            file=str(result_archive),
            caption="Keyword findings.",
            reply_to=event.message.id,
        )

    except Exception as e:
        log.exception("Processing failed")
        summary.error = str(e)
        await event.reply(format_summary(summary))

    finally:
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            log.exception("Cleanup failed for job directory: %s", job_dir)


async def handle_text_command(event) -> None:
    if event.is_private:
        return

    if ALLOWED_GROUP_ID is not None and event.chat_id != ALLOWED_GROUP_ID:
        return

    text = event.raw_text or ""

    if text.startswith("/analyze") and not event.message.document:
        await event.reply(
            "Please send `/analyze` as the caption of a compressed or plain text-like file, "
            "not as a standalone message."
        )


def validate_config() -> None:
    if not TG_API_ID:
        raise SystemExit("TG_API_ID is missing in .env.")

    if not TG_API_HASH:
        raise SystemExit("TG_API_HASH is missing in .env.")

    if not TG_BOT_TOKEN:
        raise SystemExit("TG_BOT_TOKEN is missing in .env.")

    if not KEYWORDS_FILE.exists():
        raise SystemExit(f"Keywords file not found: {KEYWORDS_FILE}")


async def main() -> None:
    validate_config()

    client = TelegramClient(
        SESSION_NAME,
        TG_API_ID,
        TG_API_HASH,
        sequential_updates=True,
    )

    await client.start(bot_token=TG_BOT_TOKEN)

    me = await client.get_me()
    log.info("Telethon client started as @%s", getattr(me, "username", None))

    client.add_event_handler(handle_analyze, events.NewMessage)
    client.add_event_handler(handle_text_command, events.NewMessage(pattern=r"^/analyze"))

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
