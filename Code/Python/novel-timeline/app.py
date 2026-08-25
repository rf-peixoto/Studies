"""
Novel Timeline — a Flask app for planning the timeline of a novel.

Everything lives in a single SQLite file (default: novel_timeline.db in the
working directory, or set NOVEL_DB to another path). Projects can also be
exported to / imported from portable JSON files.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""

import json
import os
import sqlite3
import time
from contextlib import closing

from flask import Flask, g, jsonify, render_template, request, Response

app = Flask(__name__)
DB_PATH = os.environ.get("NOVEL_DB", "novel_timeline.db")

# A default character palette. Fully editable per character in the UI; this is
# only used to suggest a colour when a new character is created without one.
DEFAULT_PALETTE = [
    "#6cc46c", "#4fd0d6", "#e6b34d", "#d07bd0",
    "#6aa9f0", "#e0685f", "#e0904d", "#a99cf0",
    "#5ec8a0", "#c8c85e", "#f07ca0", "#7f8fa6",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    unit_label TEXT DEFAULT 'Day',
    created_at REAL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS character (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#6cc46c',
    description TEXT DEFAULT '',
    appear_day INTEGER,
    exit_day INTEGER,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS thread (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#e6b34d',
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#4fd0d6'
);
CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    thread_id INTEGER REFERENCES thread(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES location(id) ON DELETE SET NULL,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS event_character (
    event_id INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, character_id)
);
"""


# --------------------------------------------------------------------------- #
#  Database helpers
# --------------------------------------------------------------------------- #
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(SCHEMA)
        db.commit()


def now():
    return time.time()


def touch_project(db, project_id):
    db.execute("UPDATE project SET updated_at=? WHERE id=?", (now(), project_id))


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


# --------------------------------------------------------------------------- #
#  Serialisation
# --------------------------------------------------------------------------- #
def serialize_project(db, project_id):
    proj = db.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
    if proj is None:
        return None

    characters = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM character WHERE project_id=? ORDER BY sort_order, id",
        (project_id,))]
    threads = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM thread WHERE project_id=? ORDER BY id", (project_id,))]
    locations = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM location WHERE project_id=? ORDER BY id", (project_id,))]

    events = []
    for r in db.execute(
            "SELECT * FROM event WHERE project_id=? ORDER BY day, sort_order, id",
            (project_id,)):
        ev = row_to_dict(r)
        ev["character_ids"] = [row["character_id"] for row in db.execute(
            "SELECT character_id FROM event_character WHERE event_id=?", (r["id"],))]
        events.append(ev)

    return {
        "project": row_to_dict(proj),
        "characters": characters,
        "threads": threads,
        "locations": locations,
        "events": events,
    }


# --------------------------------------------------------------------------- #
#  Pages
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------- #
#  Projects
# --------------------------------------------------------------------------- #
@app.route("/api/projects", methods=["GET"])
def list_projects():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, description, unit_label, updated_at "
        "FROM project ORDER BY updated_at DESC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO project (name, description, unit_label, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (data.get("name", "Untitled novel").strip() or "Untitled novel",
         data.get("description", ""),
         data.get("unit_label", "Day") or "Day",
         now(), now()))
    db.commit()
    return jsonify(serialize_project(db, cur.lastrowid)), 201


@app.route("/api/projects/<int:pid>", methods=["GET"])
def get_project(pid):
    data = serialize_project(get_db(), pid)
    if data is None:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(data)


@app.route("/api/projects/<int:pid>", methods=["PUT"])
def update_project(pid):
    data = request.get_json(force=True)
    db = get_db()
    db.execute(
        "UPDATE project SET name=?, description=?, unit_label=?, updated_at=? WHERE id=?",
        (data.get("name", "Untitled novel"),
         data.get("description", ""),
         data.get("unit_label", "Day") or "Day",
         now(), pid))
    db.commit()
    return jsonify(serialize_project(db, pid))


@app.route("/api/projects/<int:pid>", methods=["DELETE"])
def delete_project(pid):
    db = get_db()
    db.execute("DELETE FROM project WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
#  Characters
# --------------------------------------------------------------------------- #
def _int_or_none(v):
    if v in (None, "", "null"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@app.route("/api/projects/<int:pid>/characters", methods=["POST"])
def add_character(pid):
    data = request.get_json(force=True)
    db = get_db()
    count = db.execute("SELECT COUNT(*) c FROM character WHERE project_id=?",
                       (pid,)).fetchone()["c"]
    color = data.get("color") or DEFAULT_PALETTE[count % len(DEFAULT_PALETTE)]
    cur = db.execute(
        "INSERT INTO character (project_id, name, color, description, appear_day, "
        "exit_day, sort_order) VALUES (?,?,?,?,?,?,?)",
        (pid, data.get("name", "New character"), color, data.get("description", ""),
         _int_or_none(data.get("appear_day")), _int_or_none(data.get("exit_day")),
         count))
    touch_project(db, pid)
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM character WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@app.route("/api/characters/<int:cid>", methods=["PUT"])
def update_character(cid):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT project_id FROM character WHERE id=?", (cid,)).fetchone()
    if row is None:
        return jsonify({"error": "Character not found"}), 404
    db.execute(
        "UPDATE character SET name=?, color=?, description=?, appear_day=?, "
        "exit_day=?, sort_order=? WHERE id=?",
        (data.get("name", "Character"), data.get("color", "#6cc46c"),
         data.get("description", ""), _int_or_none(data.get("appear_day")),
         _int_or_none(data.get("exit_day")),
         _int_or_none(data.get("sort_order")) or 0, cid))
    touch_project(db, row["project_id"])
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM character WHERE id=?", (cid,)).fetchone()))


@app.route("/api/characters/<int:cid>", methods=["DELETE"])
def delete_character(cid):
    db = get_db()
    row = db.execute("SELECT project_id FROM character WHERE id=?", (cid,)).fetchone()
    db.execute("DELETE FROM character WHERE id=?", (cid,))
    if row:
        touch_project(db, row["project_id"])
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
#  Threads
# --------------------------------------------------------------------------- #
@app.route("/api/projects/<int:pid>/threads", methods=["POST"])
def add_thread(pid):
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO thread (project_id, name, color, description) VALUES (?,?,?,?)",
        (pid, data.get("name", "New thread"), data.get("color", "#e6b34d"),
         data.get("description", "")))
    touch_project(db, pid)
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM thread WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@app.route("/api/threads/<int:tid>", methods=["PUT"])
def update_thread(tid):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT project_id FROM thread WHERE id=?", (tid,)).fetchone()
    if row is None:
        return jsonify({"error": "Thread not found"}), 404
    db.execute("UPDATE thread SET name=?, color=?, description=? WHERE id=?",
               (data.get("name", "Thread"), data.get("color", "#e6b34d"),
                data.get("description", ""), tid))
    touch_project(db, row["project_id"])
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM thread WHERE id=?", (tid,)).fetchone()))


@app.route("/api/threads/<int:tid>", methods=["DELETE"])
def delete_thread(tid):
    db = get_db()
    row = db.execute("SELECT project_id FROM thread WHERE id=?", (tid,)).fetchone()
    db.execute("DELETE FROM thread WHERE id=?", (tid,))
    if row:
        touch_project(db, row["project_id"])
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
#  Locations
# --------------------------------------------------------------------------- #
@app.route("/api/projects/<int:pid>/locations", methods=["POST"])
def add_location(pid):
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO location (project_id, name, color) VALUES (?,?,?)",
        (pid, data.get("name", "New place"), data.get("color", "#4fd0d6")))
    touch_project(db, pid)
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM location WHERE id=?", (cur.lastrowid,)).fetchone())), 201


@app.route("/api/locations/<int:lid>", methods=["PUT"])
def update_location(lid):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT project_id FROM location WHERE id=?", (lid,)).fetchone()
    if row is None:
        return jsonify({"error": "Location not found"}), 404
    db.execute("UPDATE location SET name=?, color=? WHERE id=?",
               (data.get("name", "Place"), data.get("color", "#4fd0d6"), lid))
    touch_project(db, row["project_id"])
    db.commit()
    return jsonify(row_to_dict(db.execute(
        "SELECT * FROM location WHERE id=?", (lid,)).fetchone()))


@app.route("/api/locations/<int:lid>", methods=["DELETE"])
def delete_location(lid):
    db = get_db()
    row = db.execute("SELECT project_id FROM location WHERE id=?", (lid,)).fetchone()
    db.execute("DELETE FROM location WHERE id=?", (lid,))
    if row:
        touch_project(db, row["project_id"])
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
#  Events
# --------------------------------------------------------------------------- #
def _set_event_characters(db, event_id, character_ids):
    db.execute("DELETE FROM event_character WHERE event_id=?", (event_id,))
    for cid in character_ids or []:
        db.execute(
            "INSERT OR IGNORE INTO event_character (event_id, character_id) VALUES (?,?)",
            (event_id, cid))


@app.route("/api/projects/<int:pid>/events", methods=["POST"])
def add_event(pid):
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO event (project_id, day, title, description, thread_id, "
        "location_id, sort_order) VALUES (?,?,?,?,?,?,?)",
        (pid, _int_or_none(data.get("day")) or 0, data.get("title", "New event"),
         data.get("description", ""), _int_or_none(data.get("thread_id")),
         _int_or_none(data.get("location_id")),
         _int_or_none(data.get("sort_order")) or 0))
    _set_event_characters(db, cur.lastrowid, data.get("character_ids"))
    touch_project(db, pid)
    db.commit()
    return _event_response(db, cur.lastrowid), 201


@app.route("/api/events/<int:eid>", methods=["PUT"])
def update_event(eid):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT project_id FROM event WHERE id=?", (eid,)).fetchone()
    if row is None:
        return jsonify({"error": "Event not found"}), 404
    db.execute(
        "UPDATE event SET day=?, title=?, description=?, thread_id=?, location_id=?, "
        "sort_order=? WHERE id=?",
        (_int_or_none(data.get("day")) or 0, data.get("title", "Event"),
         data.get("description", ""), _int_or_none(data.get("thread_id")),
         _int_or_none(data.get("location_id")),
         _int_or_none(data.get("sort_order")) or 0, eid))
    if "character_ids" in data:
        _set_event_characters(db, eid, data.get("character_ids"))
    touch_project(db, row["project_id"])
    db.commit()
    return _event_response(db, eid)


@app.route("/api/events/<int:eid>", methods=["DELETE"])
def delete_event(eid):
    db = get_db()
    row = db.execute("SELECT project_id FROM event WHERE id=?", (eid,)).fetchone()
    db.execute("DELETE FROM event WHERE id=?", (eid,))
    if row:
        touch_project(db, row["project_id"])
    db.commit()
    return jsonify({"ok": True})


def _event_response(db, eid):
    ev = row_to_dict(db.execute("SELECT * FROM event WHERE id=?", (eid,)).fetchone())
    ev["character_ids"] = [r["character_id"] for r in db.execute(
        "SELECT character_id FROM event_character WHERE event_id=?", (eid,))]
    return jsonify(ev)


# --------------------------------------------------------------------------- #
#  Export / Import (portable JSON)
# --------------------------------------------------------------------------- #
@app.route("/api/projects/<int:pid>/export", methods=["GET"])
def export_project(pid):
    data = serialize_project(get_db(), pid)
    if data is None:
        return jsonify({"error": "Project not found"}), 404
    payload = {
        "format": "novel-timeline",
        "version": 1,
        "project": {
            "name": data["project"]["name"],
            "description": data["project"]["description"],
            "unit_label": data["project"]["unit_label"],
        },
        "characters": data["characters"],
        "threads": data["threads"],
        "locations": data["locations"],
        "events": data["events"],
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    fname = (data["project"]["name"] or "project").replace(" ", "_")[:60]
    return Response(
        body, mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}.json"'})


@app.route("/api/projects/import", methods=["POST"])
def import_project():
    payload = request.get_json(force=True)
    if not isinstance(payload, dict) or payload.get("format") != "novel-timeline":
        return jsonify({"error": "Not a Novel Timeline export file."}), 400

    db = get_db()
    p = payload.get("project", {})
    cur = db.execute(
        "INSERT INTO project (name, description, unit_label, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (p.get("name", "Imported novel"), p.get("description", ""),
         p.get("unit_label", "Day") or "Day", now(), now()))
    pid = cur.lastrowid

    # Remap old ids -> new ids so cross references survive.
    char_map, thread_map, loc_map = {}, {}, {}

    for c in payload.get("characters", []):
        new = db.execute(
            "INSERT INTO character (project_id, name, color, description, appear_day, "
            "exit_day, sort_order) VALUES (?,?,?,?,?,?,?)",
            (pid, c.get("name", "Character"), c.get("color", "#6cc46c"),
             c.get("description", ""), _int_or_none(c.get("appear_day")),
             _int_or_none(c.get("exit_day")), _int_or_none(c.get("sort_order")) or 0))
        char_map[c.get("id")] = new.lastrowid

    for t in payload.get("threads", []):
        new = db.execute(
            "INSERT INTO thread (project_id, name, color, description) VALUES (?,?,?,?)",
            (pid, t.get("name", "Thread"), t.get("color", "#e6b34d"),
             t.get("description", "")))
        thread_map[t.get("id")] = new.lastrowid

    for l in payload.get("locations", []):
        new = db.execute(
            "INSERT INTO location (project_id, name, color) VALUES (?,?,?)",
            (pid, l.get("name", "Place"), l.get("color", "#4fd0d6")))
        loc_map[l.get("id")] = new.lastrowid

    for e in payload.get("events", []):
        new = db.execute(
            "INSERT INTO event (project_id, day, title, description, thread_id, "
            "location_id, sort_order) VALUES (?,?,?,?,?,?,?)",
            (pid, _int_or_none(e.get("day")) or 0, e.get("title", "Event"),
             e.get("description", ""), thread_map.get(e.get("thread_id")),
             loc_map.get(e.get("location_id")), _int_or_none(e.get("sort_order")) or 0))
        remapped = [char_map[c] for c in e.get("character_ids", []) if c in char_map]
        _set_event_characters(db, new.lastrowid, remapped)

    db.commit()
    return jsonify(serialize_project(db, pid)), 201


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
