import asyncio
import csv
import datetime
import logging
import logging.handlers
import os
import signal
from typing import List

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
LOG_DIR = "logs"
LOG_FILENAME = os.path.join(LOG_DIR, "bot.log")
MESSAGE_LOG_DIR = os.path.join(LOG_DIR, "messages")

# Timezone
TIMEZONE_OFFSET = -3  # GMT-3
USER_TIMEZONE = datetime.timezone(datetime.timedelta(hours=TIMEZONE_OFFSET))

# Hour (local time) at which the collection statistics are logged and reset
DAILY_STATS_HOUR = 18
DAILY_STATS_MINUTE = 0

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

    logger = logging.getLogger("tg_collector")
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


logger = setup_logger()


# ============================================================
# Global State
# ============================================================

file_lock = asyncio.Lock()
state_lock = asyncio.Lock()
stop_event = asyncio.Event()

# Total messages collected since the last statistics reset
total_messages_counter: int = 0
counter_window_start_local: datetime.datetime = datetime.datetime.now(USER_TIMEZONE)


# ============================================================
# Constants / Headers
# ============================================================

MSG_LOG_HEADER = [
    "datetime",
    "message_id",
    "telegram_group_name",
    "telegram_group_id",
    "message_author_username",
    "message_author_id",
    "message_author_phone",
    "has_media",
    "message_content",
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


def truncate_for_log(text: str, limit: int = 200) -> str:
    """Sanitise text for safe inclusion in log lines."""
    text = text.replace("\n", "\\n").replace("\r", "\\r")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


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


def get_next_daily_stats_time(now_local: datetime.datetime) -> datetime.datetime:
    target = now_local.replace(
        hour=DAILY_STATS_HOUR,
        minute=DAILY_STATS_MINUTE,
        second=0,
        microsecond=0,
    )
    if now_local >= target:
        target += datetime.timedelta(days=1)
    return target


# ============================================================
# Message Persistence
# ============================================================

async def append_to_message_log(
    message_dt_utc: datetime.datetime,
    message_id: str,
    group_name: str,
    group_id: str,
    username: str,
    author_id: str,
    phone_num: str,
    has_media: bool,
    text: str,
) -> None:
    """
    Append one row to the daily all-messages CSV.

    Every message observed is written, with no filtering and no
    deduplication — this is a raw collection log.
    """
    local_dt = ensure_aware_utc(message_dt_utc).astimezone(USER_TIMEZONE)
    filepath = get_message_log_filepath(local_dt)

    def _write() -> None:
        file_exists = os.path.isfile(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.writerow(MSG_LOG_HEADER)
            writer.writerow([
                local_dt.strftime("%d-%m-%Y %H:%M"),
                message_id,
                group_name,
                group_id,
                username,
                author_id,
                phone_num,
                "yes" if has_media else "no",
                text,
            ])

    try:
        async with file_lock:
            await asyncio.to_thread(_write)
        logger.debug(
            "Message saved. id=%s group='%s' file=%s",
            message_id,
            group_name,
            filepath,
        )
    except Exception:
        logger.exception("Error writing to daily message log: %s", filepath)


# ============================================================
# Daily Statistics
# ============================================================

async def daily_stats_task() -> None:
    """Log how many messages were collected in the last window, then reset."""
    global total_messages_counter
    global counter_window_start_local

    while not stop_event.is_set():
        target = get_next_daily_stats_time(local_now())
        wait_seconds = max((target - local_now()).total_seconds(), 0.0)

        logger.info(
            "Next daily statistics scheduled for %s",
            target.strftime("%d-%m-%Y %H:%M:%S"),
        )

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
            return
        except asyncio.TimeoutError:
            pass

        async with state_lock:
            collected = total_messages_counter
            window_start_local = counter_window_start_local
            total_messages_counter = 0
            counter_window_start_local = target

        logger.info(
            "Daily collection statistics: %d message(s) collected between "
            "%s and %s (GMT %+d). Counter reset.",
            collected,
            window_start_local.strftime("%d-%m-%Y %H:%M"),
            target.strftime("%d-%m-%Y %H:%M"),
            TIMEZONE_OFFSET,
        )


# ============================================================
# Message Handler
# ============================================================

async def handle_new_message(event) -> None:
    global total_messages_counter

    try:
        message = event.message
        text = message.message or ""
        message_id = safe_str(getattr(message, "id", ""))
        message_dt_utc = ensure_aware_utc(message.date)
        has_media = getattr(message, "media", None) is not None

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

        # Resolve sender for author details; fall back to the raw sender id
        # if the lookup fails so the message is still recorded.
        username = ""
        author_id = safe_str(getattr(message, "sender_id", ""))
        phone_num = ""

        try:
            sender = await event.get_sender()
            if sender is not None:
                username = safe_str(getattr(sender, "username", ""))
                author_id = safe_str(getattr(sender, "id", "")) or author_id
                phone_num = safe_str(getattr(sender, "phone", ""))
        except FloodWaitError as e:
            logger.warning("FloodWait in get_sender: sleeping %ss.", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception:
            logger.warning(
                "Could not resolve sender; saving message with partial author info. "
                "group='%s' group_id=%s",
                group_name,
                group_id,
            )

        await append_to_message_log(
            message_dt_utc=message_dt_utc,
            message_id=message_id,
            group_name=group_name,
            group_id=group_id,
            username=username,
            author_id=author_id,
            phone_num=phone_num,
            has_media=has_media,
            text=text,
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

    async with state_lock:
        collected = total_messages_counter
        window_start_local = counter_window_start_local

    logger.info(
        "Collected %d message(s) since %s before shutdown.",
        collected,
        window_start_local.strftime("%d-%m-%Y %H:%M"),
    )

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
        await client.start(phone=phone)
        logger.info("Telegram client started successfully.")

        client.add_event_handler(handle_new_message, events.NewMessage)
        logger.info("NewMessage handler registered.")

        background_tasks = [
            asyncio.create_task(daily_stats_task(), name="daily_stats"),
        ]

        logger.info("Collector is running. Saving every message seen...")

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
