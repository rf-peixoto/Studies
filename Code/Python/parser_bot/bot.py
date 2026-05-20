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

import py7zr
import rarfile
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# User-configurable settings
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
KEYWORDS_FILE = Path(os.getenv("KEYWORDS_FILE", "keywords.txt"))
ALLOWED_GROUP_ID = Your group ID goes here

WORK_ROOT = Path("./work").resolve()
RESULTS_DIR_NAME = "findings"

MAX_DOWNLOAD_MB = 1024
MAX_EXTRACTED_MB = 4096
MAX_FILE_READ_MB = 64
MAX_RESULT_FILE_MB = 128
MAX_TOTAL_RESULTS_MB = 512
MAX_KEYWORDS = 5000

LOG_FILE = "bot.log"
PROCESS_LOG_FILE = "processed_files.log"

ALLOWED_ARCHIVE_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".tar.gz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
}

TEXT_EXTENSIONS_PREFERRED = {
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".js",
    ".ts",
    ".py",
    ".php",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".rb",
    ".sh",
    ".ps1",
    ".conf",
    ".cfg",
    ".ini",
    ".env",
    ".yaml",
    ".yml",
    ".sql",
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

log = logging.getLogger("keyword-archive-bot")


@dataclass
class ScanSummary:
    archive_name: str
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
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


def is_group_message(update: Update) -> bool:
    chat = update.effective_chat

    if not chat:
        return False

    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return False

    return chat.id == ALLOWED_GROUP_ID


def log_file_entry(update: Update, filename: str, filesize: int | None) -> None:
    user = update.effective_user
    username = user.username if user and user.username else "-"
    user_id = user.id if user else "-"
    readable_size = human_size(filesize)

    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | "
        f"{username} | {user_id} | {filename} | {readable_size}\n"
    )

    with open(PROCESS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def safe_name(value: str, fallback: str = "keyword") -> str:
    value = value.strip()
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = value.strip("._-")
    return value[:120] or fallback


def archive_suffix(path: Path) -> str:
    name = path.name.lower()

    for ext in sorted(ALLOWED_ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if name.endswith(ext):
            return ext

    return path.suffix.lower()


def is_supported_archive(path: Path) -> bool:
    return archive_suffix(path) in ALLOWED_ARCHIVE_EXTENSIONS


def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"Keywords file not found: {KEYWORDS_FILE}")

    keywords: list[str] = []
    seen: set[str] = set()

    with KEYWORDS_FILE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            kw = line.strip()

            if not kw or kw.startswith("#"):
                continue

            if kw not in seen:
                seen.add(kw)
                keywords.append(kw)

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
            target = dest / member.filename
            ensure_inside(dest, target)

        zf.extractall(dest, pwd=pwd)


def safe_extract_tar(path: Path, dest: Path) -> None:
    with tarfile.open(path) as tf:
        for member in tf.getmembers():
            target = dest / member.name
            ensure_inside(dest, target)

        tf.extractall(dest)


def safe_extract_7z(path: Path, dest: Path, password: str | None) -> None:
    with py7zr.SevenZipFile(path, mode="r", password=password) as z:
        for name in z.getnames():
            target = dest / name
            ensure_inside(dest, target)

        z.extractall(path=dest)


def safe_extract_rar(path: Path, dest: Path, password: str | None) -> None:
    with rarfile.RarFile(path) as rf:
        for member in rf.infolist():
            target = dest / member.filename
            ensure_inside(dest, target)

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
        ".tar",
        ".tgz",
        ".tar.gz",
        ".tar.bz2",
        ".tbz2",
        ".tar.xz",
        ".txz",
    }:
        safe_extract_tar(path, dest)
    elif suffix == ".gz":
        extract_gzip_single_file(path, dest)
    else:
        raise ValueError(f"Unsupported archive type: {suffix}")


def directory_size_bytes(path: Path) -> int:
    total = 0

    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue

    return total


def looks_like_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS_PREFERRED:
        return True

    try:
        with path.open("rb") as f:
            chunk = f.read(4096)

        if b"\x00" in chunk:
            return False

        return True

    except OSError:
        return False


def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            yield p


def grep_recursive(
    extracted_dir: Path,
    findings_dir: Path,
    keywords: list[str],
) -> tuple[int, int, int]:
    files_scanned = 0
    files_skipped = 0
    total_matches = 0
    result_sizes: dict[str, int] = {}

    compiled = [(kw, re.compile(re.escape(kw), re.IGNORECASE)) for kw in keywords]

    handles = {}

    try:
        for file_path in iter_files(extracted_dir):
            try:
                size = file_path.stat().st_size
            except OSError:
                files_skipped += 1
                continue

            if size > MAX_FILE_READ_MB * 1024 * 1024:
                files_skipped += 1
                continue

            if not looks_like_text_file(file_path):
                files_skipped += 1
                continue

            files_scanned += 1

            try:
                rel = file_path.relative_to(extracted_dir)

                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, start=1):
                        for keyword, pattern in compiled:
                            if pattern.search(line):
                                out_name = safe_name(keyword) + ".txt"
                                out_path = findings_dir / out_name

                                current_size = result_sizes.get(out_name, 0)

                                if current_size >= MAX_RESULT_FILE_MB * 1024 * 1024:
                                    continue

                                if out_name not in handles:
                                    handles[out_name] = out_path.open(
                                        "a",
                                        encoding="utf-8",
                                        errors="replace",
                                    )

                                record = f"{rel}:{line_no}: {line}"
                                handles[out_name].write(record)

                                written = len(record.encode("utf-8", errors="replace"))
                                result_sizes[out_name] = current_size + written
                                total_matches += 1

                total_result_size = sum(result_sizes.values())

                if total_result_size > MAX_TOTAL_RESULTS_MB * 1024 * 1024:
                    raise RuntimeError(
                        f"Total findings exceeded {MAX_TOTAL_RESULTS_MB} MB limit."
                    )

            except UnicodeError:
                files_skipped += 1
            except OSError:
                files_skipped += 1

    finally:
        for h in handles.values():
            h.close()

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
            f"Archive: {summary.archive_name}\n"
            f"Error: {summary.error}"
        )

    return (
        "Processing completed.\n\n"
        f"Archive: {summary.archive_name}\n"
        f"Password supplied: {'yes' if summary.password_used else 'no'}\n"
        f"Keywords loaded: {summary.keywords_loaded}\n"
        f"Files scanned: {summary.files_scanned}\n"
        f"Files skipped: {summary.files_skipped}\n"
        f"Matches found: {summary.matches}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_message(update):
        return

    await update.message.reply_text(
        "Send a compressed archive to this group. "
        "If the archive has a password, put the password in the message caption."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_message(update):
        return

    message = update.message
    document = message.document
    password = message.caption.strip() if message.caption else None

    if not document:
        return

    original_name = document.file_name or "uploaded_archive"
    safe_archive_name = safe_name(original_name, fallback="uploaded_archive")

    log_file_entry(update, original_name, document.file_size)

    if not is_supported_archive(Path(safe_archive_name)):
        await message.reply_text(
            "Unsupported archive type. Supported: zip, 7z, rar, tar, gz, tgz, "
            "tar.gz, tar.bz2, tar.xz."
        )
        return

    if document.file_size and document.file_size > MAX_DOWNLOAD_MB * 1024 * 1024:
        await message.reply_text(f"File too large. Limit is {MAX_DOWNLOAD_MB} MB.")
        return

    await message.chat.send_action(ChatAction.TYPING)
    await message.reply_text("File received. Processing started.")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    job_dir = Path(tempfile.mkdtemp(prefix="tg_keyword_job_", dir=WORK_ROOT))
    archive_path = job_dir / safe_archive_name
    extracted_dir = job_dir / "extracted"
    findings_dir = job_dir / RESULTS_DIR_NAME

    extracted_dir.mkdir()
    findings_dir.mkdir()

    summary = ScanSummary(
        archive_name=original_name,
        password_used=bool(password),
        keywords_loaded=0,
        files_scanned=0,
        files_skipped=0,
        matches=0,
        result_archive=None,
    )

    try:
        tg_file = await document.get_file()
        await tg_file.download_to_drive(custom_path=archive_path)

        keywords = load_keywords()
        summary.keywords_loaded = len(keywords)

        await message.chat.send_action(ChatAction.TYPING)
        extract_archive(archive_path, extracted_dir, password)

        extracted_size = directory_size_bytes(extracted_dir)

        if extracted_size > MAX_EXTRACTED_MB * 1024 * 1024:
            raise RuntimeError(f"Extracted content exceeded {MAX_EXTRACTED_MB} MB limit.")

        await message.chat.send_action(ChatAction.TYPING)

        files_scanned, files_skipped, matches = grep_recursive(
            extracted_dir=extracted_dir,
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
    print(update.effective_chat.id)
    if not is_group_message(update):
        return

    await update.message.reply_text(
        "Please send a compressed file as a Telegram document. "
        "Use the caption as the archive password if needed."
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Put it in .env.")

    if not KEYWORDS_FILE.exists():
        raise SystemExit(f"Keywords file not found: {KEYWORDS_FILE}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(~filters.Document.ALL, handle_non_document))

    log.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()