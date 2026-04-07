#!/usr/bin/env python3
"""
Minimalist terminal-like Flask web app for inspecting Telethon .session files.

Features
- Upload a .session file through the browser
- Parses the Telethon SQLite database safely in read-only mode when possible
- Displays sessions, entities, update_state, sent_files, and version
- Cyberpunk / terminal-inspired UI
- Search and per-section filtering in the browser
- Export current results as JSON, TXT, or HTML
- Does not persist uploaded files beyond the active request
- No external dependencies besides Flask

Run:
    python telegram_session_dump.py

Then open:
    http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, render_template_string, request


HOST = "127.0.0.1"
PORT = 5000
DEBUG = False
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"session", "sqlite", "db"}
SECRET_KEY = os.environ.get("SESSION_EXTRACTOR_SECRET", "change-this-in-production")
TITLE = "AFTERLIFE // SESSION EXTRACTOR"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config["SECRET_KEY"] = SECRET_KEY

LAST_RESULTS: dict[str, dict[str, Any]] = {}
LAST_RESULT_TOKEN = "latest"


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
    <style>
        :root {
            --bg: #05070a;
            --fg: #d7ffe8;
            --muted: #8aa394;
            --accent: #66ffb2;
            --accent2: #00e5ff;
            --danger: #ff6b9e;
            --border: rgba(102,255,178,0.20);
            --shadow: 0 0 0 1px rgba(102,255,178,0.06), 0 0 30px rgba(0,229,255,0.04);
        }
        * { box-sizing: border-box; }
        html, body {
            margin: 0;
            padding: 0;
            min-height: 100%;
            background:
                radial-gradient(circle at top right, rgba(0,229,255,0.08), transparent 25%),
                radial-gradient(circle at top left, rgba(102,255,178,0.08), transparent 20%),
                linear-gradient(180deg, #030507, #05070a 30%, #040608 100%);
            color: var(--fg);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
        }
        .scanlines::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background: repeating-linear-gradient(
                to bottom,
                rgba(255,255,255,0.015),
                rgba(255,255,255,0.015) 1px,
                transparent 2px,
                transparent 4px
            );
            opacity: 0.18;
            mix-blend-mode: screen;
        }
        .wrap {
            width: min(1180px, calc(100% - 24px));
            margin: 24px auto 48px;
        }
        .hero, .panel, .section {
            background: linear-gradient(180deg, rgba(10,15,20,0.95), rgba(7,11,16,0.98));
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            border-radius: 14px;
        }
        .hero {
            padding: 18px;
            margin-bottom: 16px;
        }
        .topline {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
        }
        .brand {
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: var(--accent);
        }
        .sub {
            margin-top: 8px;
            color: var(--muted);
            line-height: 1.55;
            font-size: 0.96rem;
        }
        .statusbar {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid var(--border);
            padding: 8px 10px;
            border-radius: 999px;
            color: var(--muted);
            background: rgba(0,0,0,0.22);
            font-size: 0.85rem;
        }
        .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent);
        }
        .panel {
            padding: 16px;
            margin-bottom: 16px;
        }
        .terminal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
            flex-wrap: wrap;
        }
        .terminal-title {
            color: var(--accent2);
            font-weight: 700;
            letter-spacing: 0.08em;
            font-size: 0.92rem;
        }
        .kbdline {
            color: var(--muted);
            font-size: 0.84rem;
        }
        .upload-box {
            border: 1px dashed rgba(102,255,178,0.35);
            border-radius: 12px;
            padding: 18px;
            background: linear-gradient(180deg, rgba(0,0,0,0.18), rgba(0,0,0,0.28));
        }
        form {
            display: grid;
            gap: 12px;
        }
        .input-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 10px;
        }
        input[type=file], input[type=search], select {
            width: 100%;
            background: #020406;
            color: var(--fg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            outline: none;
            font-family: inherit;
        }
        input[type=file]::file-selector-button {
            background: linear-gradient(180deg, rgba(102,255,178,0.16), rgba(102,255,178,0.08));
            color: var(--fg);
            border: 1px solid rgba(102,255,178,0.30);
            border-radius: 8px;
            padding: 8px 12px;
            margin-right: 12px;
            cursor: pointer;
            font-family: inherit;
        }
        button, .export-link, .toggle-btn {
            appearance: none;
            border: 1px solid rgba(102,255,178,0.35);
            background: linear-gradient(180deg, rgba(102,255,178,0.20), rgba(102,255,178,0.10));
            color: var(--fg);
            border-radius: 10px;
            padding: 12px 16px;
            cursor: pointer;
            font-family: inherit;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 44px;
        }
        .help {
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.55;
        }
        .message {
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 14px;
            border: 1px solid;
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .message.error {
            color: #ffd7e3;
            background: rgba(255,107,158,0.08);
            border-color: rgba(255,107,158,0.32);
        }
        .message.ok {
            color: #d8ffec;
            background: rgba(102,255,178,0.08);
            border-color: rgba(102,255,178,0.32);
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }
        .stat {
            background: linear-gradient(180deg, rgba(7,12,16,0.95), rgba(5,8,12,0.98));
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px;
        }
        .stat .label {
            color: var(--muted);
            font-size: 0.8rem;
            margin-bottom: 7px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .stat .value {
            color: var(--accent);
            font-size: 1.35rem;
            font-weight: 700;
        }
        .controls-grid {
            display: grid;
            grid-template-columns: 1.4fr 0.8fr auto auto auto auto auto;
            gap: 10px;
            margin-bottom: 16px;
            align-items: stretch;
        }
        .section {
            padding: 0;
            overflow: hidden;
            margin-bottom: 14px;
        }
        .section-head {
            padding: 12px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            background: linear-gradient(180deg, rgba(12,20,28,0.95), rgba(9,15,22,0.98));
            border-bottom: 1px solid var(--border);
            flex-wrap: wrap;
        }
        .section-left, .section-right {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .section-title {
            color: var(--accent2);
            font-weight: 700;
            letter-spacing: 0.05em;
        }
        .pill {
            color: var(--muted);
            border: 1px solid var(--border);
            padding: 4px 8px;
            border-radius: 999px;
            font-size: 0.78rem;
        }
        .section-body {
            padding: 12px;
        }
        .entry {
            border: 1px solid rgba(102,255,178,0.14);
            background: linear-gradient(180deg, rgba(4,7,10,0.75), rgba(2,4,7,0.88));
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .entry:last-child { margin-bottom: 0; }
        .kv {
            display: grid;
            grid-template-columns: 220px 1fr;
            gap: 6px 14px;
            align-items: start;
        }
        .k {
            color: var(--muted);
            word-break: break-word;
        }
        .v {
            color: var(--fg);
            word-break: break-word;
            white-space: pre-wrap;
        }
        .empty {
            color: var(--muted);
            font-style: italic;
        }
        .hidden-by-filter {
            display: none !important;
        }
        .footer {
            margin-top: 10px;
            color: var(--muted);
            font-size: 0.82rem;
            text-align: center;
        }
        .mono-accent { color: var(--accent); }
        @media (max-width: 1080px) {
            .controls-grid { grid-template-columns: 1fr 1fr 1fr; }
        }
        @media (max-width: 760px) {
            .input-row, .controls-grid { grid-template-columns: 1fr; }
            .kv { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body class="scanlines">
    <div class="wrap">
        <div class="hero">
            <div class="topline">
                <div>
                    <div class="brand">{{ title }}</div>
                    <div class="sub">
                        Minimalist Telethon <span class="mono-accent">.session</span> inspector.<br>
                        Upload a file, decode the SQLite contents, review auth/session metadata and cached entities.
                    </div>
                </div>
                <div class="statusbar">
                    <span class="dot"></span>
                    <span>LOCAL TERMINAL MODE</span>
                </div>
            </div>
        </div>

        <div class="panel">
            <div class="terminal-header">
                <div class="terminal-title">[ INPUT ] SESSION PAYLOAD</div>
                <div class="kbdline">accepted: .session / .sqlite / .db</div>
            </div>

            {% if error %}
                <div class="message error">{{ error }}</div>
            {% endif %}

            {% if ok_message %}
                <div class="message ok">{{ ok_message }}</div>
            {% endif %}

            <div class="upload-box">
                <form method="post" enctype="multipart/form-data">
                    <div class="input-row">
                        <input type="file" name="session_file" required>
                        <button type="submit">ANALYZE</button>
                    </div>
                    <div class="help">
                        The file is processed in temporary storage only for the current request. This interface remains intentionally read-only.
                    </div>
                </form>
            </div>
        </div>

        {% if result %}
            <div class="panel">
                <div class="terminal-header">
                    <div class="terminal-title">[ SUMMARY ] EXTRACTION OVERVIEW</div>
                    <div class="kbdline">target: {{ result.filename }}</div>
                </div>

                <div class="summary-grid">
                    <div class="stat"><div class="label">Sessions</div><div class="value">{{ result.summary.sessions }}</div></div>
                    <div class="stat"><div class="label">Entities</div><div class="value">{{ result.summary.entities }}</div></div>
                    <div class="stat"><div class="label">Update states</div><div class="value">{{ result.summary.update_state }}</div></div>
                    <div class="stat"><div class="label">Sent files</div><div class="value">{{ result.summary.sent_files }}</div></div>
                    <div class="stat"><div class="label">Schema version</div><div class="value">{{ result.summary.version }}</div></div>
                </div>

                <div class="controls-grid">
                    <input type="search" id="globalSearch" placeholder="Search across all visible results...">
                    <select id="sectionFilter">
                        <option value="all">All sections</option>
                        {% for section in result.sections %}
                            <option value="{{ section.slug }}">{{ section.title }}</option>
                        {% endfor %}
                    </select>
                    <button type="button" class="toggle-btn" onclick="expandAll()">EXPAND ALL</button>
                    <button type="button" class="toggle-btn" onclick="collapseAll()">COLLAPSE ALL</button>
                    <a class="export-link" href="/export/json?token={{ result.export_token }}">EXPORT JSON</a>
                    <a class="export-link" href="/export/txt?token={{ result.export_token }}">EXPORT TXT</a>
                    <a class="export-link" href="/export/html?token={{ result.export_token }}">EXPORT HTML</a>
                </div>

                {% for section in result.sections %}
                    <div class="section result-section" data-section="{{ section.slug }}">
                        <div class="section-head">
                            <div class="section-left">
                                <button type="button" class="toggle-btn" data-toggle="{{ section.slug }}" onclick="toggleSection('{{ section.slug }}')">HIDE</button>
                                <div class="section-title">{{ section.title }}</div>
                                <div class="pill">{{ section.count_label }}</div>
                            </div>
                            <div class="section-right">
                                <div class="pill">filter key: {{ section.slug }}</div>
                            </div>
                        </div>
                        <div class="section-body" id="body-{{ section.slug }}">
                            {% if section.entries %}
                                {% for entry in section.entries %}
                                    <div class="entry result-entry" data-entry-search="{{ entry.search_blob|lower }}">
                                        <div class="kv">
                                            {% for item in entry["fields"] %}
                                                <div class="k">{{ item.key }}</div>
                                                <div class="v">{{ item.value }}</div>
                                            {% endfor %}
                                        </div>
                                    </div>
                                {% endfor %}
                            {% else %}
                                <div class="empty">No data found for this table.</div>
                            {% endif %}
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% endif %}

        <div class="footer">
            Read-only inspector. Keep in mind that Telethon session files may contain highly sensitive authentication material.
        </div>
    </div>

    <script>
        function toggleSection(slug) {
            const body = document.getElementById('body-' + slug);
            const btn = document.querySelector('[data-toggle="' + slug + '"]');
            if (!body || !btn) return;
            const hidden = body.style.display === 'none';
            body.style.display = hidden ? '' : 'none';
            btn.textContent = hidden ? 'HIDE' : 'SHOW';
        }
        function expandAll() {
            document.querySelectorAll('.section-body').forEach(el => el.style.display = '');
            document.querySelectorAll('[data-toggle]').forEach(btn => btn.textContent = 'HIDE');
        }
        function collapseAll() {
            document.querySelectorAll('.section-body').forEach(el => el.style.display = 'none');
            document.querySelectorAll('[data-toggle]').forEach(btn => btn.textContent = 'SHOW');
        }
        function applyFilters() {
            const term = (document.getElementById('globalSearch').value || '').toLowerCase().trim();
            const sectionValue = document.getElementById('sectionFilter').value;
            document.querySelectorAll('.result-section').forEach(section => {
                const slug = section.dataset.section;
                const sectionMatches = sectionValue === 'all' || slug === sectionValue;
                let visibleEntries = 0;
                section.querySelectorAll('.result-entry').forEach(entry => {
                    const hay = entry.dataset.entrySearch || '';
                    const matchesSearch = !term || hay.includes(term);
                    const visible = sectionMatches && matchesSearch;
                    entry.classList.toggle('hidden-by-filter', !visible);
                    if (visible) visibleEntries += 1;
                });
                const hasEmptyOnly = section.querySelectorAll('.result-entry').length === 0;
                const showSection = sectionMatches && (visibleEntries > 0 || (hasEmptyOnly && !term));
                section.classList.toggle('hidden-by-filter', !showSection);
            });
        }
        document.addEventListener('DOMContentLoaded', function () {
            const search = document.getElementById('globalSearch');
            const filter = document.getElementById('sectionFilter');
            if (search) search.addEventListener('input', applyFilters);
            if (filter) filter.addEventListener('change', applyFilters);
        });
    </script>
</body>
</html>
"""


EXPORT_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }} - Export</title>
    <style>
        body {
            margin: 0;
            padding: 24px;
            background: #05070a;
            color: #d7ffe8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        }
        .wrap { max-width: 1100px; margin: 0 auto; }
        .head, .section, .entry {
            border: 1px solid rgba(102,255,178,0.22);
            border-radius: 12px;
            background: #0a0f14;
        }
        .head, .section { margin-bottom: 16px; }
        .head { padding: 18px; }
        .title { color: #66ffb2; font-size: 1.25rem; font-weight: 700; }
        .meta { color: #8aa394; margin-top: 8px; }
        .section-head { padding: 12px 14px; border-bottom: 1px solid rgba(102,255,178,0.18); color: #00e5ff; font-weight: 700; }
        .section-body { padding: 12px; }
        .entry { padding: 12px; margin-bottom: 10px; }
        .entry:last-child { margin-bottom: 0; }
        .kv { display: grid; grid-template-columns: 220px 1fr; gap: 6px 12px; }
        .k { color: #8aa394; }
        .v { white-space: pre-wrap; word-break: break-word; }
        @media (max-width: 760px) { .kv { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="head">
            <div class="title">{{ title }} // EXPORTED REPORT</div>
            <div class="meta">Target: {{ result.filename }}<br>Generated: {{ exported_at }}</div>
        </div>
        {% for section in result.sections %}
            <div class="section">
                <div class="section-head">{{ section.title }} — {{ section.count_label }}</div>
                <div class="section-body">
                    {% if section.entries %}
                        {% for entry in section.entries %}
                            <div class="entry">
                                <div class="kv">
                                    {% for item in entry["fields"] %}
                                        <div class="k">{{ item.key }}</div>
                                        <div class="v">{{ item.value }}</div>
                                    {% endfor %}
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div>No data found for this table.</div>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def allowed_file(filename: str) -> bool:
    return bool(filename and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS)


def slugify(title: str) -> str:
    return title.lower().replace("(", "").replace(")", "").replace("'", "").replace(" ", "_").replace("-", "_")


def safe_value(key: str, value: Any) -> str:
    if value is None:
        return "(none)"
    if key == "auth_key" and isinstance(value, (bytes, bytearray)):
        return value.hex()[:32] + "..."
    if key == "md5_digest" and isinstance(value, (bytes, bytearray)):
        return value.hex()
    if key == "date":
        try:
            if value:
                return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    if key == "type":
        type_map = {0: "User", 1: "Chat", 2: "Channel", 3: "Chat (legacy?)"}
        return str(type_map.get(value, value))
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def build_search_blob(fields: list[dict[str, str]]) -> str:
    return " | ".join([f["key"] for f in fields] + [f["value"] for f in fields])


def row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    fields: list[dict[str, str]] = []
    for key in row.keys():
        fields.append({"key": key, "value": safe_value(key, row[key])})
    return {"fields": fields, "search_blob": build_search_blob(fields)}


def fetch_table(cursor: sqlite3.Cursor, table_name: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        return [row_to_entry(row) for row in rows], None
    except sqlite3.OperationalError as exc:
        return [], str(exc)


def open_sqlite_readonly(path: str) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def looks_like_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16).startswith(b"SQLite format 3\x00")
    except OSError:
        return False


def make_section(title: str, entries: list[dict[str, Any]], error: str | None) -> dict[str, Any]:
    if error:
        return {
            "title": title,
            "slug": slugify(title),
            "entries": [{
                "fields": [
                    {"key": "status", "value": "table unavailable"},
                    {"key": "details", "value": error},
                ],
                "search_blob": f"status table unavailable details {error}",
            }],
            "count_label": "unavailable",
        }
    return {
        "title": title,
        "slug": slugify(title),
        "entries": entries,
        "count_label": f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
    }


def extract_session_info(session_path: str, filename: str) -> dict[str, Any]:
    if not Path(session_path).is_file():
        raise FileNotFoundError("Uploaded file was not found in temporary storage.")
    if not looks_like_sqlite(session_path):
        raise ValueError("The uploaded file does not look like a valid SQLite database.")

    conn = open_sqlite_readonly(session_path)
    try:
        cursor = conn.cursor()
        sessions_entries, sessions_error = fetch_table(cursor, "sessions")
        entities_entries, entities_error = fetch_table(cursor, "entities")
        update_state_entries, update_state_error = fetch_table(cursor, "update_state")
        sent_files_entries, sent_files_error = fetch_table(cursor, "sent_files")

        version_value = "(none)"
        version_entries: list[dict[str, Any]] = []
        version_error: str | None = None
        try:
            cursor.execute("SELECT * FROM version")
            row = cursor.fetchone()
            if row is not None:
                version_entries = [row_to_entry(row)]
                try:
                    version_value = str(row[0])
                except Exception:
                    version_value = "present"
        except sqlite3.OperationalError as exc:
            version_error = str(exc)

        result = {
            "filename": filename,
            "summary": {
                "sessions": len(sessions_entries),
                "entities": len(entities_entries),
                "update_state": len(update_state_entries),
                "sent_files": len(sent_files_entries),
                "version": version_value,
            },
            "sections": [
                make_section("SESSIONS TABLE", sessions_entries, sessions_error),
                make_section("ENTITIES TABLE", entities_entries, entities_error),
                make_section("UPDATE STATE TABLE", update_state_entries, update_state_error),
                make_section("SENT FILES TABLE", sent_files_entries, sent_files_error),
                make_section("VERSION TABLE", version_entries, version_error),
            ],
            "export_token": LAST_RESULT_TOKEN,
        }
        LAST_RESULTS[LAST_RESULT_TOKEN] = result
        return result
    finally:
        conn.close()


def export_json_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": result["filename"],
        "summary": result["summary"],
        "sections": [
            {
                "title": section["title"],
                "slug": section["slug"],
                "count_label": section["count_label"],
                "entries": [
                    {field["key"]: field["value"] for field in entry["fields"]}
                    for entry in section["entries"]
                ],
            }
            for section in result["sections"]
        ],
    }


def export_txt_payload(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f" {TITLE} // EXPORTED REPORT")
    lines.append("=" * 72)
    lines.append(f"Target: {result['filename']}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("SUMMARY")
    lines.append("-" * 72)
    for key, value in result["summary"].items():
        lines.append(f"{key}: {value}")
    for section in result["sections"]:
        lines.append("")
        lines.append("=" * 72)
        lines.append(f" {section['title']} [{section['count_label']}]")
        lines.append("=" * 72)
        if not section["entries"]:
            lines.append("No data found for this table.")
            continue
        for idx, entry in enumerate(section["entries"], start=1):
            lines.append(f"\n--- ENTRY {idx} ---")
            for field in entry["fields"]:
                lines.append(f"{field['key']}: {field['value']}")
    return "\n".join(lines) + "\n"


def get_export_result(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return LAST_RESULTS.get(token)


def result_filename_stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


@app.errorhandler(413)
def too_large(_: Exception):
    return render_template_string(
        PAGE_TEMPLATE,
        title=TITLE,
        result=None,
        ok_message=None,
        error=f"Upload rejected: file exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit.",
    ), 413


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    ok_message = None

    if request.method == "POST":
        upload = request.files.get("session_file")
        if upload is None or not upload.filename:
            error = "No file was provided."
            return render_template_string(PAGE_TEMPLATE, title=TITLE, result=result, error=error, ok_message=ok_message)

        filename = os.path.basename(upload.filename)
        if not allowed_file(filename):
            error = "Unsupported file type. Accepted extensions: .session, .sqlite, .db"
            return render_template_string(PAGE_TEMPLATE, title=TITLE, result=result, error=error, ok_message=ok_message)

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="session_inspector_", suffix=".sqlite", delete=False) as tmp:
                temp_path = tmp.name
                upload.save(tmp.name)
            result = extract_session_info(temp_path, filename)
            ok_message = f"Analysis complete for {filename}."
        except (sqlite3.DatabaseError, ValueError, FileNotFoundError) as exc:
            error = f"Could not analyze file: {exc}"
        except Exception as exc:
            error = f"Unexpected error: {exc}"
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    return render_template_string(PAGE_TEMPLATE, title=TITLE, result=result, error=error, ok_message=ok_message)


@app.route("/export/json", methods=["GET"])
def export_json_route():
    result = get_export_result(request.args.get("token"))
    if not result:
        return Response("No exportable result is currently loaded. Analyze a file first.\n", status=404, mimetype="text/plain")
    payload = json.dumps(export_json_payload(result), indent=2, ensure_ascii=False)
    stem = result_filename_stem(result["filename"])
    return Response(payload, mimetype="application/json", headers={"Content-Disposition": f'attachment; filename="{stem}_report.json"'})


@app.route("/export/txt", methods=["GET"])
def export_txt_route():
    result = get_export_result(request.args.get("token"))
    if not result:
        return Response("No exportable result is currently loaded. Analyze a file first.\n", status=404, mimetype="text/plain")
    payload = export_txt_payload(result)
    stem = result_filename_stem(result["filename"])
    return Response(payload, mimetype="text/plain", headers={"Content-Disposition": f'attachment; filename="{stem}_report.txt"'})


@app.route("/export/html", methods=["GET"])
def export_html_route():
    result = get_export_result(request.args.get("token"))
    if not result:
        return Response("No exportable result is currently loaded. Analyze a file first.\n", status=404, mimetype="text/plain")
    payload = render_template_string(EXPORT_HTML_TEMPLATE, title=TITLE, result=result, exported_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    stem = result_filename_stem(result["filename"])
    return Response(payload, mimetype="text/html", headers={"Content-Disposition": f'attachment; filename="{stem}_report.html"'})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
