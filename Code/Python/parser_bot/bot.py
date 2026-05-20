#!/usr/bin/env python3
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

import aiohttp
import py7zr
import rarfile
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# Config
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
KEYWORDS_FILE = Path(os.getenv("KEYWORDS_FILE", "keywords.txt"))

ALLOWED_GROUP_ID = None  # Example: -100xxxxxxxxxx

USE_LOCAL_BOT_API = True
LOCAL_BOT_API_BASE_URL = "http://127.0.0.1:8081/bot"
LOCAL_BOT_API_FILE_URL = "http://127.0.0.1:8081/file/bot"

WORK_ROOT = Path("./work").resolve()
RESULTS_DIR_NAME = "findings"

DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024
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

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

log = logging.getLogger("keyword-archive-bot")


@dataclass
class ScanSummary:
    input_name: str
    password_used: bool
    keywords_loaded: int
    files_scanned: int
    files_skipped: int
    matches: int
    result_archive: Path | None
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


def is_group_message(update: Update) -> bool:
    chat = update.effective_chat

    if not chat:
        return False

    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return False

    if ALLOWED_GROUP_ID is not None and chat.id != ALLOWED_GROUP_ID:
        return False

    return True


def log_file_entry(update: Update, filename: str, filesize: int | None) -> None:
    user = update.effective_user
    username = user.username if user and user.username else "-"
    user_id = user.id if user else "-"

    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | "
        f"{username} | {user_id} | {filename} | {human_size(filesize)}\n"
    )

    with open(PROCESS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


async def react_working(message) -> None:
    try:
        await message.set_reaction("👀")
    except Exception:
        log.debug("Could not react to message.", exc_info=True)


def is_image_document(document) -> bool:
    filename = document.file_name or ""
    suffix = Path(filename).suffix.lower()
    mime_type = document.mime_type or ""

    return suffix in IMAGE_EXTENSIONS or mime_type.startswith("image/")


def safe_name(value: str, fallback: str = "file") -> str:
    value = value.strip()
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = value.strip("._-")
    return value[:160] or fallback


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


def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"Keywords file not found: {KEYWORDS_FILE}")

    keywords: list[str] = []
    seen: set[str] = set()

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


def grep_recursive(
    input_dir: Path,
    findings_dir: Path,
    keywords: list[str],
) -> tuple[int, int, int]:
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


async def download_telegram_file_chunked(document, destination: Path) -> None:
    try:
        tg_file = await document.get_file()
    except BadRequest as e:
        if "file is too big" in str(e).lower():
            raise RuntimeError(
                "Telegram refused getFile because the file is too big. "
                "Chunked download cannot bypass this on the public Bot API. "
                "Run a local Telegram Bot API server and set USE_LOCAL_BOT_API=True."
            ) from e
        raise

    file_path = tg_file.file_path

    if not file_path:
        raise RuntimeError("Telegram did not return file_path.")

    local_path = Path(file_path)

    if local_path.is_absolute() and local_path.exists():
        shutil.copy2(local_path, destination)
        return

    if file_path.startswith("http://") or file_path.startswith("https://"):
        download_url = file_path
    elif USE_LOCAL_BOT_API:
        download_url = f"{LOCAL_BOT_API_FILE_URL}{BOT_TOKEN}/{file_path}"
    else:
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=60, sock_read=300)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(download_url) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(
                    f"File download failed with HTTP {response.status}: {body[:500]}"
                )

            with destination.open("wb") as f:
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_message(update):
        return

    await update.message.reply_text(
        "Send a compressed archive or plain text-like file with `/analyze` in the caption. "
        "If the archive has a password, put it after `/analyze`."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_message(update):
        return

    message = update.message
    document = message.document

    if not document:
        return

    if is_image_document(document):
        return

    caption = message.caption.strip() if message.caption else ""

    if not caption.startswith("/analyze"):
        return

    await react_working(message)

    parts = caption.split(maxsplit=1)
    password = parts[1].strip() if len(parts) > 1 else None

    original_name = document.file_name or "uploaded_file"
    safe_file_name = safe_name(original_name, fallback="uploaded_file")
    safe_file_path = Path(safe_file_name)

    log_file_entry(update, original_name, document.file_size)

    is_archive = is_supported_archive(safe_file_path)
    is_plain_text = is_supported_plain_text(safe_file_path)

    if not is_archive and not is_plain_text:
        await message.reply_text(
            "Unsupported file type. Supported archives: zip, 7z, rar, tar, gz, tgz, "
            "tar.gz, tar.bz2, tar.xz. Supported plain files: txt, csv, json, sql, "
            "log, xml, html, js, py, conf, ini, env, yaml, yml, md and similar."
        )
        return

    await message.chat.send_action(ChatAction.TYPING)
    await message.reply_text("File received. Processing started.")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    job_dir = Path(tempfile.mkdtemp(prefix="tg_keyword_job_", dir=WORK_ROOT))
    downloaded_path = job_dir / safe_file_name
    input_dir = job_dir / "input"
    findings_dir = job_dir / RESULTS_DIR_NAME

    input_dir.mkdir()
    findings_dir.mkdir()

    summary = ScanSummary(
        input_name=original_name,
        password_used=bool(password) and is_archive,
        keywords_loaded=0,
        files_scanned=0,
        files_skipped=0,
        matches=0,
        result_archive=None,
    )

    try:
        await download_telegram_file_chunked(document, downloaded_path)

        keywords = load_keywords()
        summary.keywords_loaded = len(keywords)

        await message.chat.send_action(ChatAction.TYPING)

        if is_archive:
            extract_archive(downloaded_path, input_dir, password)
        else:
            plain_target = input_dir / safe_file_name
            ensure_inside(input_dir, plain_target)
            shutil.copy2(downloaded_path, plain_target)

        await message.chat.send_action(ChatAction.TYPING)

        files_scanned, files_skipped, matches = grep_recursive(
            input_dir=input_dir,
            findings_dir=findings_dir,
            keywords=keywords,
        )

        summary.files_scanned = files_scanned
        summary.files_skipped = files_skipped
        summary.matches = matches

        if matches == 0:
            await message.reply_text(
                format_summary(summary) + "\n\nNo findings archive was generated."
            )
            return

        result_archive = make_results_archive(findings_dir, job_dir)
        summary.result_archive = result_archive

        await message.reply_text(format_summary(summary))
        await message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)

        with result_archive.open("rb") as f:
            await message.reply_document(
                document=f,
                filename="findings.zip",
                caption="Keyword findings.",
            )

    except Exception as e:
        log.exception("Processing failed")
        summary.error = str(e)
        await message.reply_text(format_summary(summary))

    finally:
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            log.exception("Cleanup failed for job directory: %s", job_dir)


async def handle_non_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_message(update):
        return

    message = update.message

    if (
        message.sticker
        or message.photo
        or message.animation
        or message.video
        or message.video_note
        or message.voice
        or message.audio
    ):
        return

    text = message.text or ""

    if not text.startswith("/analyze"):
        return

    await message.reply_text(
        "Please send `/analyze` as the caption of a compressed or plain text-like file, "
        "not as a standalone message."
    )


def build_application():
    builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(60)
        .read_timeout(300)
        .write_timeout(300)
        .pool_timeout(60)
        .media_write_timeout(300)
    )

    if USE_LOCAL_BOT_API:
        builder = (
            builder
            .base_url(LOCAL_BOT_API_BASE_URL)
            .base_file_url(LOCAL_BOT_API_FILE_URL)
            .local_mode(True)
        )

    return builder.build()


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Put it in .env.")

    if not KEYWORDS_FILE.exists():
        raise SystemExit(f"Keywords file not found: {KEYWORDS_FILE}")

    app = build_application()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(~filters.Document.ALL, handle_non_document))

    log.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
