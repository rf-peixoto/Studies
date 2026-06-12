import os
import re
import json
import socket
import sqlite3
import threading
import subprocess
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from urllib.parse import urlparse

from flask import Flask, g, redirect, render_template, request, url_for, flash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("INVENTORY_DB_PATH", os.path.join(BASE_DIR, "inventory.db"))

SUBFINDER_BIN = './subfinder' #os.environ.get("SUBFINDER_BIN", "subfinder")
SUBFINDER_TIMEOUT = int(os.environ.get("SUBFINDER_TIMEOUT", "300"))
DNS_TIMEOUT = float(os.environ.get("DNS_TIMEOUT", "3.0"))
MAX_HOSTNAME_LENGTH = 253

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "change-this-secret")
app.config["SUBFINDER_TIMEOUT"] = SUBFINDER_TIMEOUT
app.config["DNS_TIMEOUT"] = DNS_TIMEOUT
app.config["SUBFINDER_BIN"] = SUBFINDER_BIN

scan_locks: dict[int, threading.Lock] = {}
scan_locks_guard = threading.Lock()


# -----------------------------
# Database helpers
# -----------------------------
def apply_sqlite_pragmas(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db = apply_sqlite_pragmas(conn)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def new_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return apply_sqlite_pragmas(conn)


def init_db() -> None:
    conn = new_db_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_scan_at TEXT,
                scan_status TEXT NOT NULL DEFAULT 'idle'
            );

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                raw_count INTEGER NOT NULL DEFAULT 0,
                new_count INTEGER NOT NULL DEFAULT 0,
                suspicious_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                raw_output TEXT,
                FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS subdomains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id INTEGER NOT NULL,
                hostname TEXT NOT NULL,
                is_suspicious INTEGER NOT NULL DEFAULT 0,
                is_new_unseen INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_resolved_at TEXT,
                ipv4_json TEXT NOT NULL DEFAULT '[]',
                ipv6_json TEXT NOT NULL DEFAULT '[]',
                resolution_error TEXT,
                UNIQUE(domain_id, hostname),
                FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                subdomain_id INTEGER NOT NULL,
                seen_in_scan INTEGER NOT NULL DEFAULT 1,
                was_new_in_scan INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE CASCADE,
                FOREIGN KEY(subdomain_id) REFERENCES subdomains(id) ON DELETE CASCADE,
                UNIQUE(scan_id, subdomain_id)
            );

            CREATE INDEX IF NOT EXISTS idx_subdomains_domain_id ON subdomains(domain_id);
            CREATE INDEX IF NOT EXISTS idx_subdomains_flags ON subdomains(domain_id, is_suspicious, is_new_unseen, is_active);
            CREATE INDEX IF NOT EXISTS idx_scans_domain_id ON scans(domain_id, started_at DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()


# -----------------------------
# Utilities
# -----------------------------
def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)


def normalize_domain(value: str) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    if not value:
        return None

    if "://" in value:
        parsed = urlparse(value)
        value = (parsed.hostname or "").strip().lower()

    value = value.rstrip(".")

    if "/" in value or " " in value:
        return None
    if len(value) > MAX_HOSTNAME_LENGTH:
        return None
    if not HOSTNAME_RE.match(value):
        return None
    return value



def is_hostname_under_root(hostname: str, root_domain: str) -> bool:
    return hostname == root_domain or hostname.endswith("." + root_domain)



def parse_subfinder_output(raw_output: str) -> list[str]:
    seen = set()
    results = []
    for line in raw_output.splitlines():
        hostname = normalize_domain(line)
        if not hostname:
            continue
        if hostname in seen:
            continue
        seen.add(hostname)
        results.append(hostname)
    return results



def resolve_hostname(hostname: str, timeout_seconds: float) -> tuple[list[str], list[str], str | None]:
    def _lookup() -> tuple[list[str], list[str], str | None]:
        ipv4 = set()
        ipv6 = set()
        try:
            infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            return [], [], str(exc)
        except Exception as exc:
            return [], [], str(exc)

        for info in infos:
            family = info[0]
            sockaddr = info[4]
            if family == socket.AF_INET:
                ipv4.add(sockaddr[0])
            elif family == socket.AF_INET6:
                ipv6.add(sockaddr[0])
        return sorted(ipv4), sorted(ipv6), None

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_lookup)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            return [], [], f"DNS resolution timed out after {timeout_seconds} seconds"
        except Exception as exc:
            return [], [], str(exc)



def acquire_domain_lock(domain_id: int) -> threading.Lock:
    with scan_locks_guard:
        if domain_id not in scan_locks:
            scan_locks[domain_id] = threading.Lock()
        return scan_locks[domain_id]


# -----------------------------
# Scan logic
# -----------------------------
def start_domain_scan(domain_id: int) -> bool:
    conn = new_db_connection()
    try:
        domain = conn.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
        if not domain:
            return False
        if domain["scan_status"] == "running":
            return False

        conn.execute(
            "UPDATE domains SET scan_status = 'running' WHERE id = ?",
            (domain_id,),
        )
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=run_scan_worker, args=(domain_id,), daemon=True)
    thread.start()
    return True



def run_scan_worker(domain_id: int) -> None:
    lock = acquire_domain_lock(domain_id)
    with lock:
        conn = new_db_connection()
        try:
            domain_row = conn.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
            if not domain_row:
                return

            root_domain = domain_row["domain"]
            started_at = utcnow_iso()
            scan_id = conn.execute(
                "INSERT INTO scans (domain_id, started_at, status) VALUES (?, ?, 'running')",
                (domain_id, started_at),
            ).lastrowid
            conn.commit()

            raw_output = ""
            new_count = 0
            suspicious_count = 0
            parsed = []

            try:
                command = [
                    app.config["SUBFINDER_BIN"],
                    "-d",
                    root_domain,
                    "-all",
                    "-silent",
                ]
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=app.config["SUBFINDER_TIMEOUT"],
                    check=False,
                )
                raw_output = (completed.stdout or "")
                stderr = (completed.stderr or "").strip()

                if completed.returncode != 0:
                    error = f"subfinder exited with code {completed.returncode}"
                    if stderr:
                        error += f": {stderr}"
                    raise RuntimeError(error)

                parsed = parse_subfinder_output(raw_output)
                suspicious_count = sum(1 for host in parsed if not is_hostname_under_root(host, root_domain))
                new_count = persist_scan_results(conn, domain_id, scan_id, root_domain, parsed)

                finished_at = utcnow_iso()
                conn.execute(
                    """
                    UPDATE scans
                    SET finished_at = ?, status = 'completed', raw_count = ?, new_count = ?, suspicious_count = ?, raw_output = ?
                    WHERE id = ?
                    """,
                    (finished_at, len(parsed), new_count, suspicious_count, raw_output, scan_id),
                )
                conn.execute(
                    "UPDATE domains SET last_scan_at = ?, scan_status = 'idle' WHERE id = ?",
                    (finished_at, domain_id),
                )
                conn.commit()
            except subprocess.TimeoutExpired:
                finished_at = utcnow_iso()
                msg = f"subfinder timed out after {app.config['SUBFINDER_TIMEOUT']} seconds"
                conn.execute(
                    "UPDATE scans SET finished_at = ?, status = 'failed', error_message = ?, raw_output = ? WHERE id = ?",
                    (finished_at, msg, raw_output, scan_id),
                )
                conn.execute(
                    "UPDATE domains SET scan_status = 'error' WHERE id = ?",
                    (domain_id,),
                )
                conn.commit()
            except Exception as exc:
                finished_at = utcnow_iso()
                conn.execute(
                    "UPDATE scans SET finished_at = ?, status = 'failed', error_message = ?, raw_output = ? WHERE id = ?",
                    (finished_at, str(exc), raw_output, scan_id),
                )
                conn.execute(
                    "UPDATE domains SET scan_status = 'error' WHERE id = ?",
                    (domain_id,),
                )
                conn.commit()
        finally:
            conn.close()



def persist_scan_results(conn: sqlite3.Connection, domain_id: int, scan_id: int, root_domain: str, parsed_hosts: list[str]) -> int:
    now = utcnow_iso()
    current_seen = set(parsed_hosts)
    new_count = 0

    existing_rows = conn.execute(
        "SELECT * FROM subdomains WHERE domain_id = ?",
        (domain_id,),
    ).fetchall()
    existing_map = {row["hostname"]: row for row in existing_rows}

    missing_hostnames = [row["hostname"] for row in existing_rows if row["hostname"] not in current_seen and row["is_active"] == 1]

    resolved_hosts = []
    for hostname in parsed_hosts:
        is_suspicious = 0 if is_hostname_under_root(hostname, root_domain) else 1
        ipv4, ipv6, resolution_error = resolve_hostname(hostname, app.config["DNS_TIMEOUT"])
        resolved_hosts.append({
            "hostname": hostname,
            "is_suspicious": is_suspicious,
            "ipv4_json": json.dumps(ipv4),
            "ipv6_json": json.dumps(ipv6),
            "resolution_error": resolution_error,
            "last_resolved_at": utcnow_iso(),
        })

    conn.execute("BEGIN IMMEDIATE")
    try:
        if missing_hostnames:
            conn.executemany(
                "UPDATE subdomains SET is_active = 0 WHERE domain_id = ? AND hostname = ?",
                [(domain_id, hostname) for hostname in missing_hostnames],
            )

        for item in resolved_hosts:
            hostname = item["hostname"]
            if hostname in existing_map:
                row = existing_map[hostname]
                conn.execute(
                    """
                    UPDATE subdomains
                    SET is_suspicious = ?,
                        is_active = 1,
                        last_seen_at = ?,
                        last_resolved_at = ?,
                        ipv4_json = ?,
                        ipv6_json = ?,
                        resolution_error = ?
                    WHERE id = ?
                    """,
                    (
                        item["is_suspicious"],
                        now,
                        item["last_resolved_at"],
                        item["ipv4_json"],
                        item["ipv6_json"],
                        item["resolution_error"],
                        row["id"],
                    ),
                )
                subdomain_id = row["id"]
                was_new = 0
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO subdomains (
                        domain_id, hostname, is_suspicious, is_new_unseen, is_active,
                        first_seen_at, last_seen_at, last_resolved_at, ipv4_json, ipv6_json, resolution_error
                    ) VALUES (?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        domain_id,
                        hostname,
                        item["is_suspicious"],
                        now,
                        now,
                        item["last_resolved_at"],
                        item["ipv4_json"],
                        item["ipv6_json"],
                        item["resolution_error"],
                    ),
                )
                subdomain_id = cursor.lastrowid
                was_new = 1
                new_count += 1

            conn.execute(
                "INSERT OR REPLACE INTO scan_results (scan_id, subdomain_id, seen_in_scan, was_new_in_scan) VALUES (?, ?, 1, ?)",
                (scan_id, subdomain_id, was_new),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return new_count


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    db = get_db()
    domains = db.execute(
        """
        SELECT
            d.*,
            COALESCE((SELECT COUNT(*) FROM subdomains s WHERE s.domain_id = d.id), 0) AS total_subdomains,
            COALESCE((SELECT COUNT(*) FROM subdomains s WHERE s.domain_id = d.id AND s.is_new_unseen = 1), 0) AS unseen_new_count,
            COALESCE((SELECT COUNT(*) FROM subdomains s WHERE s.domain_id = d.id AND s.is_suspicious = 1), 0) AS suspicious_count,
            COALESCE((SELECT COUNT(*) FROM subdomains s WHERE s.domain_id = d.id AND s.is_active = 1), 0) AS active_count
        FROM domains d
        ORDER BY d.domain ASC
        """
    ).fetchall()
    return render_template("index.html", domains=domains)


@app.route("/domains", methods=["POST"])
def add_domain():
    raw_domain = request.form.get("domain", "")
    normalized = normalize_domain(raw_domain)
    if not normalized:
        flash("Invalid domain.", "error")
        return redirect(url_for("index"))

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO domains (domain, created_at, scan_status) VALUES (?, ?, 'idle')",
            (normalized, utcnow_iso()),
        )
        db.commit()
        domain_id = cursor.lastrowid
        start_domain_scan(domain_id)
        flash(f"Domain {normalized} added. Initial scan started.", "success")
    except sqlite3.IntegrityError:
        flash("Domain already exists.", "error")
    return redirect(url_for("index"))


@app.route("/domains/<int:domain_id>/scan", methods=["POST"])
def scan_domain(domain_id: int):
    started = start_domain_scan(domain_id)
    if started:
        flash("Scan started.", "success")
    else:
        flash("Scan already running or domain not found.", "error")
    return redirect(url_for("domain_detail", domain_id=domain_id))


@app.route("/domains/<int:domain_id>")
def domain_detail(domain_id: int):
    db = get_db()
    domain = db.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
    if not domain:
        flash("Domain not found.", "error")
        return redirect(url_for("index"))

    subdomains = db.execute(
        "SELECT * FROM subdomains WHERE domain_id = ? ORDER BY is_suspicious DESC, hostname ASC",
        (domain_id,),
    ).fetchall()
    scans = db.execute(
        "SELECT * FROM scans WHERE domain_id = ? ORDER BY started_at DESC LIMIT 10",
        (domain_id,),
    ).fetchall()

    suspicious = []
    normal = []
    for row in subdomains:
        parsed = dict(row)
        parsed["ipv4"] = json.loads(parsed["ipv4_json"] or "[]")
        parsed["ipv6"] = json.loads(parsed["ipv6_json"] or "[]")
        if parsed["is_suspicious"]:
            suspicious.append(parsed)
        else:
            normal.append(parsed)

    # Best-effort acknowledgement of "new" tags.
    # During an active scan, writes may briefly contend with the worker.
    # The page must still render even if this acknowledgement cannot run now.
    try:
        db.execute(
            "UPDATE subdomains SET is_new_unseen = 0 WHERE domain_id = ? AND is_new_unseen = 1",
            (domain_id,),
        )
        db.commit()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            db.rollback()
        else:
            raise

    return render_template(
        "domain_detail.html",
        domain=domain,
        suspicious=suspicious,
        normal=normal,
        scans=scans,
    )


@app.route("/domains/<int:domain_id>/delete", methods=["POST"])
def delete_domain(domain_id: int):
    db = get_db()
    db.execute("DELETE FROM domains WHERE id = ?", (domain_id,))
    db.commit()
    flash("Domain deleted.", "success")
    return redirect(url_for("index"))


@app.template_filter("fmt_ts")
def fmt_ts(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return value


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
