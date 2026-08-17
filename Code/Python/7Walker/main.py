import asyncio
import csv
import datetime
import hashlib
import html
import io
import json
import logging
import logging.handlers
import os
import signal
import smtplib
import zipfile
from dataclasses import dataclass, field
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Set, Tuple

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError


# ============================================================
# Configuration
# ============================================================

# Telegram API
api_id = 0          # Replace with your API ID
api_hash = ''    # Replace with your API hash
phone = ''
session_name = "session_name"

# Files
KEYWORDS_FILE = "keywords.json"
LOG_DIR = "logs"
LOG_FILENAME = os.path.join(LOG_DIR, "bot.log")
EMAIL_ERROR_LOG_FILENAME = os.path.join(LOG_DIR, "email_errors.log")
MESSAGE_LOG_DIR = os.path.join(LOG_DIR, "messages")
EMAIL_LOGO_PATH = "logo.png"

# Timezone
TIMEZONE_OFFSET = -3  # GMT-3
USER_TIMEZONE = datetime.timezone(datetime.timedelta(hours=TIMEZONE_OFFSET))

# Alerting / refresh
REPORT_WINDOW_HOURS = 1
KEYWORDS_REFRESH_SECONDS = 15 * 60

# SMTP
SMTP_SERVER    = 'smtpout.secureserver.net'
SMTP_PORT      = 465
SMTP_USERNAME  = ''
SMTP_PASSWORD  = ''
EMAIL_FROM     = ''

# Email retry configuration
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY_SECONDS = 10

# Daily summary reset time
DAILY_RESET_HOUR = 18
DAILY_RESET_MINUTE = 0

# Logging
LOG_LEVEL = logging.INFO

# Log rotation: 10 MB max per file, keep 7 backups
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 7


# ============================================================
# Logging
# ============================================================

def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("tg_monitor")
    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # General rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILENAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def setup_email_error_logger() -> logging.Logger:
    """
    Dedicated logger for email delivery failures.
    Each entry is a structured JSON line for easy parsing / alerting.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    email_logger = logging.getLogger("tg_monitor.email_errors")
    email_logger.setLevel(logging.ERROR)
    email_logger.propagate = False

    if email_logger.handlers:
        return email_logger

    handler = logging.handlers.RotatingFileHandler(
        EMAIL_ERROR_LOG_FILENAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.ERROR)
    # JSON-structured formatter so the file can be ingested by log aggregators
    handler.setFormatter(logging.Formatter("%(message)s"))
    email_logger.addHandler(handler)

    return email_logger


logger = setup_logger()
email_error_logger = setup_email_error_logger()


def log_email_error(
    to_email: str,
    subject: str,
    attempt: int,
    exc: Exception,
    final: bool = False,
) -> None:
    """Write one JSON-line entry to the dedicated email error log."""
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "to": to_email,
        "subject": subject,
        "attempt": attempt,
        "final_failure": final,
        "error": repr(exc),
    }
    email_error_logger.error(json.dumps(entry, ensure_ascii=False))


# ============================================================
# Global State
# ============================================================

file_lock = asyncio.Lock()
keywords_lock = asyncio.Lock()
state_lock = asyncio.Lock()
msg_log_lock = asyncio.Lock()
stop_event = asyncio.Event()

keywords_data: Dict[str, Dict[str, object]] = {}

# Key: (bucket_start_local, author_id, message_hash)
pending_alerts: Dict[Tuple[datetime.datetime, str, str], "PendingAlert"] = {}

# Global total monitored messages counter
total_messages_counter: int = 0
counter_window_start_local: datetime.datetime = datetime.datetime.now(USER_TIMEZONE)

# Dedup tracker for the daily message log: maps date → set of hashes already written
#   Reset automatically when the date rolls over.
_msg_log_seen_hashes: Dict[str, Set[str]] = {}   # key: "YYYY-MM-DD"


# ============================================================
# Data Models
# ============================================================

@dataclass
class AlertRow:
    message_dt_utc: datetime.datetime
    client: str
    keyword: str
    telegram_group_name: str
    telegram_group_id: str
    message_author_username: str
    message_author_id: str
    message_author_phone: str
    message_content: str
    duplicates: int = 1

    def to_csv_row(self) -> List[object]:
        return [
            self.message_dt_utc.astimezone(USER_TIMEZONE).strftime("%d-%m-%Y %H:%M"),
            self.client,
            self.keyword,
            self.telegram_group_name,
            self.telegram_group_id,
            self.message_author_username,
            self.message_author_id,
            self.message_author_phone,
            self.message_content,
            self.duplicates,
        ]


@dataclass
class PendingAlert:
    bucket_start_local: datetime.datetime
    message_hash: str
    author_id: str
    first_seen_utc: datetime.datetime
    last_seen_utc: datetime.datetime
    duplicates: int = 1
    groups_seen: Set[Tuple[str, str]] = field(default_factory=set)
    rows_by_key: Dict[Tuple[str, str], AlertRow] = field(default_factory=dict)

    def register_seen(
        self,
        group_name: str,
        group_id: str,
        seen_at_utc: datetime.datetime,
    ) -> None:
        self.duplicates += 1
        self.last_seen_utc = seen_at_utc
        self.groups_seen.add((group_name, group_id))
        for row in self.rows_by_key.values():
            row.duplicates = self.duplicates


# ============================================================
# Constants / Headers
# ============================================================

CSV_HEADER = [
    "datetime",
    "client",
    "keyword",
    "telegram_group_name",
    "telegram_group_id",
    "message_author_username",
    "message_author_id",
    "message_author_phone",
    "message_content",
    "duplicates",
]

# Columns written to the daily all-messages log (no client / keyword columns)
MSG_LOG_HEADER = [
    "datetime",
    "telegram_group_name",
    "telegram_group_id",
    "message_author_username",
    "message_author_id",
    "message_author_phone",
    "message_content",
    "duplicates",
]


# ============================================================
# Helpers
# ============================================================

def ensure_aware_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def local_now() -> datetime.datetime:
    return datetime.datetime.now(USER_TIMEZONE)


def safe_str(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def truncate_for_log(text: str, limit: int = 99_999_999_999) -> str:
    """Sanitise text for safe inclusion in log lines. No practical size limit."""
    text = text.replace("\n", "\\n").replace("\r", "\\r")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def compute_message_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_bucket_start_local(message_dt_utc: datetime.datetime) -> datetime.datetime:
    local_dt = ensure_aware_utc(message_dt_utc).astimezone(USER_TIMEZONE)
    return local_dt.replace(minute=0, second=0, microsecond=0)


def get_csv_filepath(message_dt_utc: datetime.datetime) -> str:
    """
    Hourly CSV file path:
    tg_data/YYYY/MM/DD/DDMMYY_HH00.csv
    """
    local_dt = ensure_aware_utc(message_dt_utc).astimezone(USER_TIMEZONE)
    folder = os.path.join(
        "tg_data",
        local_dt.strftime("%Y"),
        local_dt.strftime("%m"),
        local_dt.strftime("%d"),
    )
    os.makedirs(folder, exist_ok=True)

    filename = local_dt.strftime("%d%m%y") + f"_{local_dt.hour:02d}00.csv"
    return os.path.join(folder, filename)


def get_message_log_filepath(local_dt: datetime.datetime) -> str:
    """
    Daily message-log CSV path:
    logs/messages/YYYY-MM-DD.csv

    A new file is created for each calendar day (local timezone), making
    daily backups trivial — just copy yesterday's file.
    """
    os.makedirs(MESSAGE_LOG_DIR, exist_ok=True)
    filename = local_dt.strftime("%Y-%m-%d") + ".csv"
    return os.path.join(MESSAGE_LOG_DIR, filename)


async def append_to_message_log(
    message_dt_utc: datetime.datetime,
    group_name: str,
    group_id: str,
    username: str,
    author_id: str,
    phone_num: str,
    text: str,
    message_hash: str,
    duplicates: int,
) -> None:
    """
    Append one row to the daily all-messages CSV.

    Deduplication is enforced in memory (per calendar day): if *message_hash*
    was already written today the call is a no-op, otherwise the row is
    appended and the hash recorded so future duplicates are silently skipped.

    The 'duplicates' column is always written with the latest count so the
    last entry for a given hash reflects the total number of times the bot
    saw that exact message text during the day — callers must update it
    before calling here when a duplicate is detected.
    """
    global _msg_log_seen_hashes

    local_dt = ensure_aware_utc(message_dt_utc).astimezone(USER_TIMEZONE)
    date_key = local_dt.strftime("%Y-%m-%d")
    filepath = get_message_log_filepath(local_dt)

    def _write(is_new_hash: bool) -> None:
        file_exists = os.path.isfile(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.writerow(MSG_LOG_HEADER)
            writer.writerow([
                local_dt.strftime("%d-%m-%Y %H:%M"),
                group_name,
                group_id,
                username,
                author_id,
                phone_num,
                text,
                duplicates,
            ])

    async with msg_log_lock:
        # Purge stale date keys to keep memory tidy across midnight
        stale = [k for k in _msg_log_seen_hashes if k != date_key]
        for k in stale:
            del _msg_log_seen_hashes[k]

        day_hashes = _msg_log_seen_hashes.setdefault(date_key, set())

        if message_hash in day_hashes:
            # Already logged today — skip (duplicate will be counted elsewhere)
            return

        day_hashes.add(message_hash)

    try:
        async with file_lock:
            await asyncio.to_thread(_write, True)
        logger.debug(
            "Message logged. hash=%s group='%s' date=%s",
            message_hash[:12],
            group_name,
            date_key,
        )
    except Exception:
        logger.exception(
            "Error writing to daily message log: %s", filepath
        )


def format_local_window(
    start_local: datetime.datetime,
    end_local: datetime.datetime,
) -> Tuple[str, str]:
    return (
        start_local.strftime("%d-%m-%Y %H:%M"),
        end_local.strftime("%d-%m-%Y %H:%M"),
    )


def get_next_daily_reset_time(now_local: datetime.datetime) -> datetime.datetime:
    target = now_local.replace(
        hour=DAILY_RESET_HOUR,
        minute=DAILY_RESET_MINUTE,
        second=0,
        microsecond=0,
    )
    if now_local >= target:
        target += datetime.timedelta(days=1)
    return target


# ============================================================
# Keywords Validation / Load
# ============================================================

def validate_and_normalize_keywords(raw_data: object) -> Dict[str, Dict[str, object]]:
    if not isinstance(raw_data, dict):
        raise ValueError("keywords.json must contain a top-level JSON object.")

    normalized: Dict[str, Dict[str, object]] = {}

    for customer_id, info in raw_data.items():
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValueError("Each customer id must be a non-empty string.")

        if not isinstance(info, dict):
            raise ValueError(f"Customer '{customer_id}' must contain an object.")

        email = info.get("email", "")
        keywords = info.get("keywords", [])

        if not isinstance(email, str):
            raise ValueError(f"Customer '{customer_id}' has invalid email value.")

        if not isinstance(keywords, list):
            raise ValueError(
                f"Customer '{customer_id}' has invalid keywords value; expected list."
            )

        cleaned_keywords: List[str] = []
        for keyword in keywords:
            if isinstance(keyword, str):
                keyword = keyword.strip()
                if keyword:
                    cleaned_keywords.append(keyword)

        normalized[customer_id] = {
            "email": email.strip(),
            "keywords": cleaned_keywords,
        }

    return normalized


def load_keywords_file_sync() -> Dict[str, Dict[str, object]]:
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return validate_and_normalize_keywords(raw)


def get_all_recipient_emails(snapshot: Dict[str, Dict[str, object]]) -> List[str]:
    emails: Set[str] = set()
    for info in snapshot.values():
        email = safe_str(info.get("email", "")).strip()
        if email:
            emails.add(email)
    return sorted(emails)


# ============================================================
# CSV / ZIP Builders
# ============================================================

def build_csv_bytes(rows: List[AlertRow]) -> bytes:
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(row.to_csv_row())
    return csv_buffer.getvalue().encode("utf-8")


def compress_to_zip(csv_bytes: bytes, inner_filename: str) -> bytes:
    """
    Wrap *csv_bytes* inside an in-memory ZIP archive.

    Using ZIP_DEFLATED gives typically 70-90 % size reduction on CSV data,
    keeping email attachments small even for large alert batches.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        zf.writestr(inner_filename, csv_bytes)
    return zip_buffer.getvalue()


# ============================================================
# Keywords Reload
# ============================================================

async def update_keywords_data() -> None:
    global keywords_data

    try:
        data = await asyncio.to_thread(load_keywords_file_sync)
        async with keywords_lock:
            keywords_data = data
        logger.info("Keywords file loaded successfully. Customers=%d", len(data))
    except Exception:
        logger.exception("Failed to load keywords file. Keeping previous configuration.")


async def periodic_keywords_update_task() -> None:
    await update_keywords_data()

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=KEYWORDS_REFRESH_SECONDS)
            return
        except asyncio.TimeoutError:
            await update_keywords_data()


async def get_keywords_snapshot() -> Dict[str, Dict[str, object]]:
    async with keywords_lock:
        snapshot: Dict[str, Dict[str, object]] = {}
        for customer_id, info in keywords_data.items():
            snapshot[customer_id] = {
                "email": info.get("email", ""),
                "keywords": list(info.get("keywords", [])),
            }
        return snapshot


# ============================================================
# CSV Persistence
# ============================================================

async def write_records_to_filepath(filepath: str, rows: List[AlertRow]) -> None:
    def _write() -> None:
        file_exists = os.path.isfile(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.writerow(CSV_HEADER)
            for row in rows:
                writer.writerow(row.to_csv_row())

    try:
        async with file_lock:
            await asyncio.to_thread(_write)
        logger.info("Saved %d record(s) to %s", len(rows), filepath)
    except Exception:
        logger.exception("Error while writing records to CSV: %s", filepath)


# ============================================================
# Email (with compression + retry)
# ============================================================

def send_email_sync(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_mime_type: Tuple[str, str] = ("application", "zip"),
) -> None:
    """
    Build and deliver one email message.

    *attachment_bytes* may be raw CSV or a ZIP archive; the caller decides.
    *attachment_mime_type* should match whatever bytes are passed
    (default ``("application", "zip")``).
    """
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email

    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)

    alternative.attach(MIMEText(body_text, "plain", "utf-8"))

    html_parts = ["<html><body>"]

    if os.path.isfile(EMAIL_LOGO_PATH):
        html_parts.append('<img src="cid:logo"><br><br>')

    escaped_body = html.escape(body_text).replace("\n", "<br>")
    html_parts.append(
        f'<div style="font-family: monospace; white-space: pre-wrap;">'
        f"{escaped_body}</div>"
    )
    html_parts.append("</body></html>")

    alternative.attach(MIMEText("".join(html_parts), "html", "utf-8"))

    if os.path.isfile(EMAIL_LOGO_PATH):
        try:
            with open(EMAIL_LOGO_PATH, "rb") as img_f:
                img = MIMEImage(img_f.read())
                img.add_header("Content-ID", "<logo>")
                img.add_header(
                    "Content-Disposition",
                    "inline",
                    filename=os.path.basename(EMAIL_LOGO_PATH),
                )
                msg.attach(img)
        except Exception:
            logger.exception("Could not attach logo from %s", EMAIL_LOGO_PATH)

    if attachment_bytes is not None and attachment_filename:
        main_type, sub_type = attachment_mime_type
        part = MIMEBase(main_type, sub_type)
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", "attachment", filename=attachment_filename
        )
        msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(msg)


async def send_email_async(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_mime_type: Tuple[str, str] = ("application", "zip"),
) -> None:
    """
    Async wrapper around *send_email_sync* with exponential-backoff retry.

    Failures on every attempt are written to the dedicated email error log.
    Only the final permanent failure is promoted to a general-logger ERROR so
    that transient SMTP hiccups don't pollute the main log with false alarms.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, EMAIL_MAX_RETRIES + 1):
        try:
            await asyncio.to_thread(
                send_email_sync,
                to_email,
                subject,
                body_text,
                attachment_bytes,
                attachment_filename,
                attachment_mime_type,
            )
            logger.info(
                "Email sent successfully. to=%s attempt=%d subject='%s'",
                to_email,
                attempt,
                subject,
            )
            return  # success — exit early

        except Exception as exc:
            last_exc = exc
            is_final = attempt == EMAIL_MAX_RETRIES

            # Always write to the dedicated email-error log
            log_email_error(to_email, subject, attempt, exc, final=is_final)

            if is_final:
                # Escalate to main logger on permanent failure
                logger.error(
                    "Email delivery permanently failed after %d attempt(s). "
                    "to=%s subject='%s' error=%r",
                    EMAIL_MAX_RETRIES,
                    to_email,
                    subject,
                    exc,
                )
            else:
                delay = EMAIL_RETRY_DELAY_SECONDS * attempt  # linear back-off
                logger.warning(
                    "Email attempt %d/%d failed for %s; retrying in %ds. error=%r",
                    attempt,
                    EMAIL_MAX_RETRIES,
                    to_email,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)


# ============================================================
# Flush Pending Alerts
# ============================================================

async def flush_alert_buckets(force: bool = False) -> None:
    now_local_dt = local_now()

    async with state_lock:
        keys_to_flush: List[Tuple[datetime.datetime, str, str]] = []

        for key, pending in pending_alerts.items():
            bucket_end = pending.bucket_start_local + datetime.timedelta(
                hours=REPORT_WINDOW_HOURS
            )
            if force or now_local_dt >= bucket_end:
                keys_to_flush.append(key)

        flushed_items: List[PendingAlert] = [
            pending_alerts.pop(key) for key in keys_to_flush
        ]

    if not flushed_items:
        label = "Forced" if force else "Hourly"
        logger.info("%s flush executed: no pending alerts.", label)
        return

    keywords_snapshot = await get_keywords_snapshot()

    rows_by_file: Dict[str, List[AlertRow]] = {}
    rows_by_customer: Dict[Tuple[str, str], List[AlertRow]] = {}

    for pending in flushed_items:
        for row in pending.rows_by_key.values():
            filepath = get_csv_filepath(row.message_dt_utc)
            rows_by_file.setdefault(filepath, []).append(row)

            customer_email = safe_str(
                keywords_snapshot.get(row.client, {}).get("email", "")
            ).strip()
            rows_by_customer.setdefault((row.client, customer_email), []).append(row)

    # Persist CSVs first
    for filepath, rows in rows_by_file.items():
        await write_records_to_filepath(filepath, rows)

    email_tasks: List[asyncio.Task] = []

    for (customer_id, customer_email), rows in rows_by_customer.items():
        if not customer_email:
            logger.warning(
                "Skipping alert email for '%s' because no email is configured.",
                customer_id,
            )
            continue

        bucket_start_local = min(
            row.message_dt_utc.astimezone(USER_TIMEZONE) for row in rows
        ).replace(minute=0, second=0, microsecond=0)
        bucket_end_local = bucket_start_local + datetime.timedelta(
            hours=REPORT_WINDOW_HOURS
        )

        start_str, end_str = format_local_window(bucket_start_local, bucket_end_local)
        unique_rows = len(rows)
        total_sightings = sum(row.duplicates for row in rows)

        # Build CSV then compress to ZIP
        csv_inner_filename = (
            f"alerts_{customer_id}_{local_now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
        )
        csv_bytes = build_csv_bytes(rows)
        zip_bytes = compress_to_zip(csv_bytes, csv_inner_filename)
        zip_filename = csv_inner_filename.replace(".csv", ".zip")

        logger.info(
            "Compressed alert CSV for '%s': %d bytes → %d bytes (%.1f%% reduction)",
            customer_id,
            len(csv_bytes),
            len(zip_bytes),
            (1 - len(zip_bytes) / max(len(csv_bytes), 1)) * 100,
        )

        subject = (
            f"[Alert] {customer_id} — {unique_rows} unique match(es) in last 1 hour"
        )
        body = (
            f"Customer: {customer_id}\n"
            f"Reporting window: {start_str} – {end_str} (GMT -3)\n"
            f"Unique matched rows: {unique_rows}\n"
            f"Total sightings represented in those rows: {total_sightings}\n\n"
            f"The attached ZIP archive contains the full alert data in CSV format.\n\n"
            f"Please do not reply to this email."
        )

        email_tasks.append(
            asyncio.create_task(
                send_email_async(
                    to_email=customer_email,
                    subject=subject,
                    body_text=body,
                    attachment_bytes=zip_bytes,
                    attachment_filename=zip_filename,
                    attachment_mime_type=("application", "zip"),
                )
            )
        )

    if email_tasks:
        await asyncio.gather(*email_tasks, return_exceptions=True)
        logger.info(
            "Hourly flush completed. Customer email tasks dispatched=%d", len(email_tasks)
        )


async def hourly_flush_task() -> None:
    while not stop_event.is_set():
        now_local_dt = local_now()
        next_hour = (now_local_dt + datetime.timedelta(hours=1)).replace(
            minute=0,
            second=5,
            microsecond=0,
        )
        wait_seconds = max((next_hour - now_local_dt).total_seconds(), 5.0)

        logger.info(
            "Next hourly flush scheduled for %s",
            next_hour.strftime("%d-%m-%Y %H:%M:%S"),
        )

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
            return
        except asyncio.TimeoutError:
            await flush_alert_buckets(force=False)


# ============================================================
# Daily Monitoring Summary
# ============================================================

async def daily_monitoring_summary_task() -> None:
    global total_messages_counter
    global counter_window_start_local

    while not stop_event.is_set():
        target = get_next_daily_reset_time(local_now())
        wait_seconds = max((target - local_now()).total_seconds(), 0.0)

        logger.info(
            "Next daily summary scheduled for %s",
            target.strftime("%d-%m-%Y %H:%M:%S"),
        )

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
            return
        except asyncio.TimeoutError:
            pass

        keywords_snapshot = await get_keywords_snapshot()
        recipients = get_all_recipient_emails(keywords_snapshot)

        async with state_lock:
            monitored_messages = total_messages_counter
            window_start_local = counter_window_start_local
            window_end_local = target
            total_messages_counter = 0
            counter_window_start_local = target

        if not recipients:
            logger.warning(
                "Daily monitoring summary skipped: no recipient emails found."
            )
            continue

        start_str, end_str = format_local_window(window_start_local, window_end_local)

        subject = (
            f"[Monitoring Summary] {monitored_messages} message(s) "
            f"monitored in last 24 hours"
        )
        body = (
            f"Daily monitoring summary\n"
            f"Window: {start_str} – {end_str} (GMT -3)\n"
            f"Total messages monitored across all chats/groups: {monitored_messages}\n\n"
            f"Please do not reply to this email."
        )

        await asyncio.gather(
            *(send_email_async(email, subject, body) for email in recipients),
            return_exceptions=True,
        )

        logger.info(
            "Daily monitoring summary dispatched to %d recipient(s). Counter reset.",
            len(recipients),
        )


# ============================================================
# Message Handler
# ============================================================

async def handle_new_message(event) -> None:
    global total_messages_counter

    try:
        message = event.message
        text = message.message or ""
        message_dt_utc = ensure_aware_utc(message.date)

        group = event.chat
        group_name = safe_str(getattr(group, "title", "Unknown"))
        group_id = safe_str(getattr(group, "id", "Unknown"))

        async with state_lock:
            total_messages_counter += 1
            current_counter = total_messages_counter

        logger.info(
            "Message received. counter=%d group='%s' group_id=%s has_text=%s preview='%s'",
            current_counter,
            group_name,
            group_id,
            bool(text.strip()),
            truncate_for_log(text),
        )

        if not text.strip():
            logger.debug(
                "Ignoring message with no text. group='%s' group_id=%s",
                group_name,
                group_id,
            )
            return

        keywords_snapshot = await get_keywords_snapshot()

        message_lower = text.lower()

        # Resolve sender early so we have author info for the message log
        # regardless of whether any keyword matches.
        try:
            sender = await event.get_sender()
        except FloodWaitError as e:
            logger.warning("FloodWait in get_sender: sleeping %ss.", e.seconds)
            await asyncio.sleep(e.seconds)
            return

        username = safe_str(getattr(sender, "username", ""))
        author_id = safe_str(getattr(sender, "id", ""))
        phone_num = safe_str(getattr(sender, "phone", ""))

        message_hash = compute_message_hash(text)
        bucket_start_local = get_bucket_start_local(message_dt_utc)
        signature = (bucket_start_local, author_id, message_hash)

        # ── Daily message log ────────────────────────────────────────────────
        # Written for EVERY message that has text, regardless of keyword match.
        # append_to_message_log handles in-memory deduplication per calendar
        # day, so each unique message hash is written exactly once.
        await append_to_message_log(
            message_dt_utc=message_dt_utc,
            group_name=group_name,
            group_id=group_id,
            username=username,
            author_id=author_id,
            phone_num=phone_num,
            text=text,
            message_hash=message_hash,
            duplicates=1,
        )
        # ────────────────────────────────────────────────────────────────────

        if not keywords_snapshot:
            logger.warning(
                "No keywords loaded; skipping match check. group='%s' group_id=%s",
                group_name,
                group_id,
            )
            return

        # --- Keyword matching (case-insensitive, all matches collected) ---
        matched_targets: List[Tuple[str, str, str]] = []
        for customer_id, info in keywords_snapshot.items():
            customer_email = safe_str(info.get("email", "")).strip()
            keywords = info.get("keywords", [])

            for keyword in keywords:
                if isinstance(keyword, str) and keyword.lower() in message_lower:
                    matched_targets.append((customer_id, customer_email, keyword))

        if not matched_targets:
            logger.debug(
                "No keyword match. group='%s' group_id=%s preview='%s'",
                group_name,
                group_id,
                truncate_for_log(text),
            )
            return

        logger.info(
            "Keyword match found. group='%s' group_id=%s matches=%d preview='%s'",
            group_name,
            group_id,
            len(matched_targets),
            truncate_for_log(text),
        )

        async with state_lock:
            pending = pending_alerts.get(signature)

            if pending is None:
                pending = PendingAlert(
                    bucket_start_local=bucket_start_local,
                    message_hash=message_hash,
                    author_id=author_id,
                    first_seen_utc=message_dt_utc,
                    last_seen_utc=message_dt_utc,
                    duplicates=1,
                    groups_seen={(group_name, group_id)},
                )
                pending_alerts[signature] = pending
                logger.info(
                    "New pending alert bucket created. author_id=%s group='%s'",
                    author_id,
                    group_name,
                )
            else:
                pending.register_seen(group_name, group_id, message_dt_utc)
                logger.info(
                    "Duplicate detected. author_id=%s duplicates=%d group='%s'",
                    author_id,
                    pending.duplicates,
                    group_name,
                )

            for customer_id, _customer_email, keyword in matched_targets:
                row_key = (customer_id, keyword)

                if row_key not in pending.rows_by_key:
                    pending.rows_by_key[row_key] = AlertRow(
                        message_dt_utc=message_dt_utc,
                        client=customer_id,
                        keyword=keyword,
                        telegram_group_name=group_name,
                        telegram_group_id=group_id,
                        message_author_username=username,
                        message_author_id=author_id,
                        message_author_phone=phone_num,
                        message_content=text,
                        duplicates=pending.duplicates,
                    )
                    logger.info(
                        "Row queued. customer='%s' keyword='%s' author_id=%s "
                        "group='%s' duplicates=%d",
                        customer_id,
                        keyword,
                        author_id,
                        group_name,
                        pending.duplicates,
                    )
                else:
                    pending.rows_by_key[row_key].duplicates = pending.duplicates
                    logger.debug(
                        "Row duplicate count updated. customer='%s' keyword='%s' "
                       "author_id=%s duplicates=%d",
                        customer_id,
                        keyword,
                        author_id,
                        pending.duplicates,
                    )

    except FloodWaitError as e:
        logger.warning("FloodWait in handler: sleeping %ss.", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception:
        logger.exception("Unhandled error while processing new message.")


# ============================================================
# Shutdown / Signals
# ============================================================

def register_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    def _handle_signal(signum, _frame) -> None:
        logger.info("Signal %s received. Starting graceful shutdown...", signum)
        loop.call_soon_threadsafe(stop_event.set)

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handle_signal)


async def shutdown(
    client: TelegramClient, background_tasks: List[asyncio.Task]
) -> None:
    logger.info("Shutdown started.")
    stop_event.set()

    for task in background_tasks:
        task.cancel()

    for task in background_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task failed during shutdown.")

    try:
        await flush_alert_buckets(force=True)
    except Exception:
        logger.exception("Failed to flush pending alerts during shutdown.")

    try:
        if client.is_connected():
            await client.disconnect()
    except Exception:
        logger.exception("Failed to disconnect Telegram client cleanly.")

    logger.info("Shutdown finished.")


# ============================================================
# Main
# ============================================================

async def main() -> None:
    global counter_window_start_local

    counter_window_start_local = local_now()

    client = TelegramClient(session_name, api_id, api_hash)
    background_tasks: List[asyncio.Task] = []

    loop = asyncio.get_running_loop()
    register_signal_handlers(loop)

    try:
        await update_keywords_data()

        await client.start(phone=phone)
        logger.info("Telegram client started successfully.")

        client.add_event_handler(handle_new_message, events.NewMessage)
        logger.info("NewMessage handler registered.")

        background_tasks = [
            asyncio.create_task(
                periodic_keywords_update_task(), name="keywords_refresh"
            ),
            asyncio.create_task(hourly_flush_task(), name="hourly_flush"),
            asyncio.create_task(
                daily_monitoring_summary_task(), name="daily_summary"
            ),
        ]

        logger.info("Bot is running. Listening for new messages...")

        disconnect_task = asyncio.create_task(
            client.run_until_disconnected(),
            name="telegram_disconnect_waiter",
        )
        stop_task = asyncio.create_task(
            stop_event.wait(),
            name="stop_waiter",
        )

        done, pending = await asyncio.wait(
            {disconnect_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if stop_task in done and stop_event.is_set():
            logger.info("Stop requested by signal or internal event.")
        elif disconnect_task in done:
            logger.warning("Telegram client disconnected unexpectedly.")
            stop_event.set()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
        stop_event.set()
    except Exception:
        logger.exception("Unhandled error in main loop.")
        stop_event.set()
    finally:
        await shutdown(client, background_tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Unhandled top-level exception:")
