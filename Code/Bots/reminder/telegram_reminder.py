#!/usr/bin/env python3
"""
Simple Telegram reminder bot.

Features:
- Save reminders from plain text messages
- Supported formats:
    In 6 hours: reminder to buy stuff
    In 30 minutes: do the thing
    In 2 days: remind this stuff
    Tomorrow at 07:30: message goes here
    Tomorrow at 7h30: message goes here
    At 16/04/2026 13:00: this other thing here
    At 16/04 13:00: this other thing here
    At April 16 13:00: this other thing here
    At April 16th 13h00: this other thing here

Commands:
- /start
- /help
- /now
- /list
- /delete <id>

Timezone:
- America/Sao_Paulo
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# Configuration
# =========================

DB_PATH = "reminders.db"
TIMEZONE_NAME = "America/Sao_Paulo"
CHECK_INTERVAL_SECONDS = 30

TZ = ZoneInfo(TIMEZONE_NAME)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================
# Data model
# =========================

@dataclass
class ParsedReminder:
    remind_at: datetime
    text: str
    original_input: str


# =========================
# Database
# =========================

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                reminder_text TEXT NOT NULL,
                remind_at_iso TEXT NOT NULL,
                original_input TEXT NOT NULL,
                created_at_iso TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0,
                sent_at_iso TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_reminder(chat_id: int, parsed: ParsedReminder) -> int:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO reminders (
                chat_id,
                reminder_text,
                remind_at_iso,
                original_input,
                created_at_iso,
                sent
            )
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                chat_id,
                parsed.text,
                parsed.remind_at.isoformat(),
                parsed.original_input,
                datetime.now(TZ).isoformat(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_pending_reminders(chat_id: int) -> list[sqlite3.Row]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, reminder_text, remind_at_iso
            FROM reminders
            WHERE chat_id = ? AND sent = 0
            ORDER BY remind_at_iso ASC
            """,
            (chat_id,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def delete_reminder(chat_id: int, reminder_id: int) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            DELETE FROM reminders
            WHERE id = ? AND chat_id = ? AND sent = 0
            """,
            (reminder_id, chat_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_due_reminders(now_local: datetime) -> list[sqlite3.Row]:
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, chat_id, reminder_text, remind_at_iso
            FROM reminders
            WHERE sent = 0 AND remind_at_iso <= ?
            ORDER BY remind_at_iso ASC
            """,
            (now_local.isoformat(),),
        ).fetchall()
        return rows
    finally:
        conn.close()


def mark_reminder_sent(reminder_id: int, when_local: datetime) -> None:
    conn = get_db_connection()
    try:
        conn.execute(
            """
            UPDATE reminders
            SET sent = 1, sent_at_iso = ?
            WHERE id = ?
            """,
            (when_local.isoformat(), reminder_id),
        )
        conn.commit()
    finally:
        conn.close()


# =========================
# Parsing helpers
# =========================

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

RELATIVE_RE = re.compile(
    r"^\s*in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

TOMORROW_RE = re.compile(
    r"^\s*tomorrow\s+at\s+(.+?)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

AT_ABSOLUTE_RE = re.compile(
    r"^\s*at\s+(.+?)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


def normalize_time_string(time_str: str) -> str:
    s = time_str.strip().lower()

    # 7h30 -> 07:30 ; 13h00 -> 13:00 ; 7h -> 07:00
    m = re.fullmatch(r"(\d{1,2})h(?:(\d{2}))?", s)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or "0")
        return f"{hour:02d}:{minute:02d}"

    # 7:30 -> 07:30
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        return f"{hour:02d}:{minute:02d}"

    raise ValueError("Invalid time format.")


def parse_hhmm(time_str: str) -> tuple[int, int]:
    normalized = normalize_time_string(time_str)
    hour_str, minute_str = normalized.split(":")
    hour = int(hour_str)
    minute = int(minute_str)

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Time out of range.")

    return hour, minute


def parse_relative(now_local: datetime, text: str) -> Optional[ParsedReminder]:
    m = RELATIVE_RE.match(text)
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2).lower()
    reminder_text = m.group(3).strip()

    if amount <= 0:
        raise ValueError("Relative amount must be positive.")

    if unit.startswith("minute"):
        delta = timedelta(minutes=amount)
    elif unit.startswith("hour"):
        delta = timedelta(hours=amount)
    elif unit.startswith("day"):
        delta = timedelta(days=amount)
    else:
        raise ValueError("Unsupported relative time unit.")

    remind_at = now_local + delta
    return ParsedReminder(remind_at=remind_at, text=reminder_text, original_input=text)


def parse_tomorrow(now_local: datetime, text: str) -> Optional[ParsedReminder]:
    m = TOMORROW_RE.match(text)
    if not m:
        return None

    time_part = m.group(1).strip()
    reminder_text = m.group(2).strip()
    hour, minute = parse_hhmm(time_part)

    tomorrow_date = (now_local + timedelta(days=1)).date()
    remind_at = datetime(
        year=tomorrow_date.year,
        month=tomorrow_date.month,
        day=tomorrow_date.day,
        hour=hour,
        minute=minute,
        tzinfo=TZ,
    )

    return ParsedReminder(remind_at=remind_at, text=reminder_text, original_input=text)


def parse_absolute_numeric(now_local: datetime, date_part: str, reminder_text: str, original_input: str) -> Optional[ParsedReminder]:
    # DD/MM/YYYY HH:MM or DD/MM HH:MM
    m = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s+(.+)",
        date_part.strip(),
        re.IGNORECASE,
    )
    if not m:
        return None

    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3)) if m.group(3) else now_local.year
    time_part = m.group(4).strip()

    hour, minute = parse_hhmm(time_part)

    remind_at = datetime(year, month, day, hour, minute, tzinfo=TZ)

    # If year omitted and date/time already passed, push to next year.
    if m.group(3) is None and remind_at <= now_local:
        remind_at = datetime(year + 1, month, day, hour, minute, tzinfo=TZ)

    return ParsedReminder(remind_at=remind_at, text=reminder_text, original_input=original_input)


def parse_absolute_month_name(now_local: datetime, date_part: str, reminder_text: str, original_input: str) -> Optional[ParsedReminder]:
    # April 16 13:00
    # April 16th 13h00
    m = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(.+)",
        date_part.strip(),
        re.IGNORECASE,
    )
    if not m:
        return None

    month_name = m.group(1).lower()
    day = int(m.group(2))
    time_part = m.group(3).strip()

    if month_name not in MONTHS:
        raise ValueError("Unknown month name.")

    month = MONTHS[month_name]
    hour, minute = parse_hhmm(time_part)

    remind_at = datetime(now_local.year, month, day, hour, minute, tzinfo=TZ)

    # If already passed this year, move to next year.
    if remind_at <= now_local:
        remind_at = datetime(now_local.year + 1, month, day, hour, minute, tzinfo=TZ)

    return ParsedReminder(remind_at=remind_at, text=reminder_text, original_input=original_input)


def parse_absolute(now_local: datetime, text: str) -> Optional[ParsedReminder]:
    m = AT_ABSOLUTE_RE.match(text)
    if not m:
        return None

    date_part = m.group(1).strip()
    reminder_text = m.group(2).strip()

    parsed = parse_absolute_numeric(now_local, date_part, reminder_text, text)
    if parsed is not None:
        return parsed

    parsed = parse_absolute_month_name(now_local, date_part, reminder_text, text)
    if parsed is not None:
        return parsed

    raise ValueError("Unsupported absolute date format.")


def parse_user_reminder(text: str, now_local: datetime) -> ParsedReminder:
    parsers = (
        parse_relative,
        parse_tomorrow,
        parse_absolute,
    )

    for parser in parsers:
        parsed = parser(now_local, text)
        if parsed is not None:
            if not parsed.text.strip():
                raise ValueError("Reminder text cannot be empty.")
            if parsed.remind_at <= now_local:
                raise ValueError("Reminder time must be in the future.")
            return parsed

    raise ValueError(
        "Could not parse reminder.\n"
        "Use one of these formats:\n"
        "- In 6 hours: buy stuff\n"
        "- In 30 minutes: do the thing\n"
        "- In 2 days: remind this stuff\n"
        "- Tomorrow at 07:30: message goes here\n"
        "- At 16/04/2026 13:00: this other thing here\n"
        "- At 16/04 13:00: this other thing here\n"
        "- At April 16 13:00: this other thing here"
    )


# =========================
# Formatting
# =========================

def format_dt(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M")


def help_text() -> str:
    return (
        "Send reminders as plain messages.\n\n"
        "<b>Supported formats</b>\n"
        "- <code>In 6 hours: reminder to buy stuff</code>\n"
        "- <code>In 30 minutes: do the thing</code>\n"
        "- <code>In 2 days: remind this stuff</code>\n"
        "- <code>Tomorrow at 07:30: message goes here</code>\n"
        "- <code>Tomorrow at 7h30: message goes here</code>\n"
        "- <code>At 16/04/2026 13:00: this other thing here</code>\n"
        "- <code>At 16/04 13:00: this other thing here</code>\n"
        "- <code>At April 16 13:00: this other thing here</code>\n"
        "- <code>At April 16th 13h00: this other thing here</code>\n\n"
        "<b>Commands</b>\n"
        "- <code>/now</code> — show current bot time\n"
        "- <code>/list</code> — show pending reminders\n"
        "- <code>/delete ID</code> — delete a pending reminder\n"
    )


# =========================
# Telegram handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Reminder bot is running.\n\n" + help_text(),
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(help_text(), parse_mode=ParseMode.HTML)


async def now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now_local = datetime.now(TZ)
    await update.message.reply_text(
        f"Current bot time: <b>{format_dt(now_local)}</b>\n"
        f"Timezone: <b>{TIMEZONE_NAME}</b>",
        parse_mode=ParseMode.HTML,
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    rows = list_pending_reminders(chat_id)

    if not rows:
        await update.message.reply_text("No pending reminders.")
        return

    lines = ["<b>Pending reminders</b>"]
    for row in rows:
        remind_at = datetime.fromisoformat(row["remind_at_iso"]).astimezone(TZ)
        lines.append(
            f"- <code>{row['id']}</code> | <b>{format_dt(remind_at)}</b> | {row['reminder_text']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("Usage: /delete <id>")
        return

    raw_id = context.args[0].strip()
    if not raw_id.isdigit():
        await update.message.reply_text("Reminder id must be a number.")
        return

    reminder_id = int(raw_id)
    deleted = delete_reminder(chat_id, reminder_id)

    if deleted:
        await update.message.reply_text(f"Deleted reminder {reminder_id}.")
    else:
        await update.message.reply_text("Reminder not found, already sent, or not yours.")


async def handle_reminder_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    now_local = datetime.now(TZ)

    try:
        parsed = parse_user_reminder(text, now_local)
        reminder_id = insert_reminder(chat_id, parsed)

        await update.message.reply_text(
            f"Saved reminder <b>{reminder_id}</b>\n"
            f"When: <b>{format_dt(parsed.remind_at)}</b>\n"
            f"Timezone: <b>{TIMEZONE_NAME}</b>\n"
            f"Text: {parsed.text}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        await update.message.reply_text(str(exc))


# =========================
# Scheduler job
# =========================

async def reminder_dispatcher(context: ContextTypes.DEFAULT_TYPE) -> None:
    now_local = datetime.now(TZ)
    rows = get_due_reminders(now_local)

    for row in rows:
        reminder_id = row["id"]
        chat_id = row["chat_id"]
        reminder_text = row["reminder_text"]
        remind_at = datetime.fromisoformat(row["remind_at_iso"]).astimezone(TZ)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ <b>Reminder</b>\n"
                    f"When: <b>{format_dt(remind_at)}</b>\n"
                    f"Text: {reminder_text}"
                ),
                parse_mode=ParseMode.HTML,
            )
            mark_reminder_sent(reminder_id, now_local)
        except Exception:
            logger.exception("Failed to send reminder id=%s", reminder_id)


# =========================
# Main
# =========================

def require_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN environment variable.\n"
            "Example:\n"
            "  export TELEGRAM_BOT_TOKEN='123456:ABCDEF...'\n"
            "  python reminder_bot.py"
        )
    return token


def main() -> None:
    init_db()
    token = require_token()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("now", now_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reminder_message))

    app.job_queue.run_repeating(
        reminder_dispatcher,
        interval=CHECK_INTERVAL_SECONDS,
        first=5,
    )

    logger.info("Bot started with timezone %s", TIMEZONE_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
