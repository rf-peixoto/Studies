#!/usr/bin/env python3
"""
DungeonFinder - a web front-end for code-cave detection and identification.

Anyone can upload an executable (PE/ELF/Mach-O) and get a read-only structural
report: format, architecture, entry point, sections, per-section entropy,
hashes, and a map of the "code caves" (runs of padding bytes) inside it.

This service performs analysis only. It does not modify, patch, inject into,
or produce any executable. Uploaded files are stored transiently and deleted
after an admin-configured retention window.

Admin configuration (password set via environment or the CLI):
    python app.py set-password          # interactively set the admin password
    DUNGEONFINDER_ADMIN_PASSWORD=...     # or provide it via the environment

Run:
    python app.py                        # dev server
    gunicorn -w 4 app:app                # production
"""
from __future__ import annotations

import csv
import getpass
import hashlib
import hmac
import io
import json
import os
import secrets
import sys
import threading
import time
import uuid
from collections import deque
from functools import wraps

from flask import (
    Flask, request, render_template, redirect, url_for, session,
    jsonify, abort, send_file, flash, Response,
)
from werkzeug.utils import secure_filename

import dungeon_core as dc

# --------------------------------------------------------------------------- #
#  Paths & persistent state
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DUNGEONFINDER_DATA", os.path.join(BASE_DIR, "dungeon"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
RESULT_DIR = os.path.join(DATA_DIR, "results")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

for d in (DATA_DIR, UPLOAD_DIR, RESULT_DIR):
    os.makedirs(d, exist_ok=True)

DEFAULT_CONFIG = {
    "max_file_size_mb": 32,
    "retention_minutes": 30,
    "force_extension": True,
    # adaptive hashcash
    "hashcash_base_bits": 18,     # baseline difficulty (leading zero bits)
    "hashcash_max_bits": 26,      # hard cap
    "hashcash_adaptive": True,
    "admin_password_hash": None,  # pbkdf2 "algo$iter$salt$hash"
    # recent-analysis feed
    "feed_enabled": True,
    "feed_hash": "sha256",        # which digest to show (md5/sha256/sha512/blake2b)
    "feed_max": 10,               # how many recent entries to show
}

FEED_HASHES = ("md5", "sha256", "sha512", "blake2b")

_config_lock = threading.Lock()


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict):
    with _config_lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)


# --------------------------------------------------------------------------- #
#  Password hashing (stdlib pbkdf2)
# --------------------------------------------------------------------------- #
def hash_password(password: str, iterations: int = 240_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def resolve_admin_hash(cfg: dict):
    """Env password wins over the stored hash; returns a verifier hash or None."""
    env_pw = os.environ.get("DUNGEONFINDER_ADMIN_PASSWORD")
    if env_pw:
        return ("env", env_pw)
    if cfg.get("admin_password_hash"):
        return ("hash", cfg["admin_password_hash"])
    return None


# --------------------------------------------------------------------------- #
#  Adaptive hashcash (proof-of-work)
# --------------------------------------------------------------------------- #
class HashcashManager:
    """
    Issues HMAC-signed PoW challenges and verifies solutions.

    A client must find a nonce such that
        sha256(f"{token}:{bits}:{ts}:{nonce}")
    has at least `bits` leading zero bits.

    Difficulty is adaptive: it rises with recent global upload volume and with
    repeated requests from the same client, then decays back to the baseline.
    """

    def __init__(self, cfg_getter):
        self._cfg = cfg_getter
        self._secret = secrets.token_bytes(32)
        self._lock = threading.Lock()
        self._global_hits = deque(maxlen=400)       # recent issue timestamps
        self._per_ip = {}                           # ip -> deque[timestamps]
        self._used = {}                             # token -> expiry ts

    # -- difficulty ------------------------------------------------------- #
    def current_bits(self, ip: str) -> int:
        cfg = self._cfg()
        base = int(cfg.get("hashcash_base_bits", 18))
        cap = int(cfg.get("hashcash_max_bits", 26))
        if not cfg.get("hashcash_adaptive", True):
            return max(1, min(base, cap))
        now = time.time()
        with self._lock:
            # global load over the last 60s
            recent = sum(1 for t in self._global_hits if now - t < 60)
            ipq = self._per_ip.get(ip)
            ip_recent = sum(1 for t in ipq if now - t < 60) if ipq else 0
        bump = 0
        bump += min(recent // 10, 4)       # +1 per 10 global requests/min, max +4
        bump += min(ip_recent // 3, 4)     # +1 per 3 requests/min from this IP, max +4
        return max(1, min(base + bump, cap))

    # -- issue ------------------------------------------------------------ #
    def issue(self, ip: str) -> dict:
        now = int(time.time())
        token = secrets.token_hex(12)
        bits = self.current_bits(ip)
        payload = f"{token}:{bits}:{now}"
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        with self._lock:
            self._global_hits.append(now)
            self._per_ip.setdefault(ip, deque(maxlen=60)).append(now)
            self._gc(now)
        return {"token": token, "bits": bits, "ts": now, "sig": sig,
                "challenge": payload}

    def _gc(self, now):
        # drop used tokens older than 10 min
        dead = [t for t, exp in self._used.items() if exp < now]
        for t in dead:
            self._used.pop(t, None)

    # -- verify ----------------------------------------------------------- #
    @staticmethod
    def _leading_zero_bits(digest: bytes) -> int:
        bits = 0
        for byte in digest:
            if byte == 0:
                bits += 8
                continue
            bits += 8 - byte.bit_length()
            break
        return bits

    def verify(self, token, bits, ts, sig, nonce) -> tuple[bool, str]:
        try:
            bits = int(bits)
            ts = int(ts)
        except (TypeError, ValueError):
            return False, "Malformed challenge."
        now = int(time.time())
        if now - ts > 300:
            return False, "Challenge expired. Reload and try again."
        payload = f"{token}:{bits}:{ts}"
        expected = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, str(sig)):
            return False, "Invalid challenge signature."
        with self._lock:
            if token in self._used:
                return False, "Challenge already used."
        digest = hashlib.sha256(f"{payload}:{nonce}".encode()).digest()
        if self._leading_zero_bits(digest) < bits:
            return False, "Proof-of-work does not satisfy the required difficulty."
        with self._lock:
            self._used[token] = now + 600
        return True, "ok"


# --------------------------------------------------------------------------- #
#  Retention sweeper
# --------------------------------------------------------------------------- #
class Sweeper(threading.Thread):
    daemon = True

    def __init__(self, cfg_getter, interval=30):
        super().__init__()
        self._cfg = cfg_getter
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        while not self._stop.wait(self.interval):
            try:
                self.sweep()
            except Exception:
                pass

    def sweep(self):
        cfg = self._cfg()
        ttl = max(1, int(cfg.get("retention_minutes", 30))) * 60
        now = time.time()
        for folder in (UPLOAD_DIR, RESULT_DIR):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                try:
                    if now - os.path.getmtime(path) > ttl:
                        os.remove(path)
                except FileNotFoundError:
                    pass
                except Exception:
                    pass


# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.secret_key = os.environ.get("DUNGEONFINDER_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = None  # enforced dynamically from config

hashcash = HashcashManager(load_config)
sweeper = Sweeper(load_config)
sweeper.start()


def client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def is_admin() -> bool:
    return bool(session.get("is_admin"))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        if not is_admin():
            return redirect(url_for("admin_login", next=request.path))
        return fn(*a, **k)
    return wrapper


def result_path(rid: str) -> str:
    return os.path.join(RESULT_DIR, f"{rid}.json")


def load_result(rid: str):
    p = result_path(rid)
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def retention_left(rid: str, cfg: dict):
    p = result_path(rid)
    if not os.path.isfile(p):
        return 0
    ttl = max(1, int(cfg.get("retention_minutes", 30))) * 60
    left = ttl - (time.time() - os.path.getmtime(p))
    return max(0, int(left))


def recent_feed(cfg: dict):
    """
    Build the public recent-analysis feed: for each live report, expose only the
    admin-chosen hash, human-readable size, cave count and time-to-deletion.
    No filenames or offsets are leaked.
    """
    if not cfg.get("feed_enabled", True):
        return []
    which = cfg.get("feed_hash", "sha256")
    if which not in FEED_HASHES:
        which = "sha256"
    ttl = max(1, int(cfg.get("retention_minutes", 30))) * 60
    now = time.time()
    rows = []
    try:
        names = os.listdir(RESULT_DIR)
    except FileNotFoundError:
        return []
    for name in names:
        if not name.endswith(".json"):
            continue
        p = os.path.join(RESULT_DIR, name)
        try:
            mtime = os.path.getmtime(p)
            with open(p) as f:
                d = json.load(f)
        except Exception:
            continue
        left = int(max(0, ttl - (now - mtime)))
        if left <= 0:
            continue
        digest = (d.get("hashes") or {}).get(which, "")
        rows.append({
            "hash": digest,
            "hash_algo": which,
            "size_human": d.get("size_human") or dc.human_size(d.get("size", 0)),
            "caves": len(d.get("caves") or []),
            "format": d.get("format", "?"),
            "ttl": left,
            "_created": d.get("created", mtime),
        })
    rows.sort(key=lambda r: r["_created"], reverse=True)
    rows = rows[: max(1, int(cfg.get("feed_max", 10)))]
    for r in rows:
        r.pop("_created", None)
    return rows


# --------------------------------------------------------------------------- #
#  Public routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    cfg = load_config()
    return render_template(
        "index.html",
        cfg=cfg,
        allowed=", ".join(dc.ALLOWED_EXTENSIONS),
        admin=is_admin(),
        feed=recent_feed(cfg),
    )


@app.route("/api/challenge")
def api_challenge():
    """Issue an adaptive hashcash challenge for the uploader."""
    return jsonify(hashcash.issue(client_ip()))


@app.route("/api/feed")
def api_feed():
    """Live recent-analysis feed (polled by the scan page)."""
    return jsonify(recent_feed(load_config()))


@app.route("/scan", methods=["POST"])
def scan():
    cfg = load_config()

    # 1) Hashcash gate
    ok, msg = hashcash.verify(
        request.form.get("hc_token"), request.form.get("hc_bits"),
        request.form.get("hc_ts"), request.form.get("hc_sig"),
        request.form.get("hc_nonce"),
    )
    if not ok:
        return _scan_error(msg, 429)

    # 2) File presence
    f = request.files.get("file")
    if not f or not f.filename:
        return _scan_error("No file was uploaded.", 400)

    filename = secure_filename(f.filename) or "upload.bin"

    # 3) Size limit (stream to disk with a hard cap)
    max_bytes = int(cfg.get("max_file_size_mb", 32)) * 1024 * 1024
    uid = uuid.uuid4().hex
    stored = os.path.join(UPLOAD_DIR, f"{uid}_{filename}")
    size = 0
    head = b""
    try:
        with open(stored, "wb") as out:
            while True:
                chunk = f.stream.read(65536)
                if not chunk:
                    break
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("size")
                out.write(chunk)
    except ValueError:
        _safe_remove(stored)
        return _scan_error(
            f"File exceeds the {cfg['max_file_size_mb']} MB limit.", 413)
    except Exception:
        _safe_remove(stored)
        return _scan_error("Could not read the uploaded file.", 400)

    if size == 0:
        _safe_remove(stored)
        return _scan_error("Uploaded file is empty.", 400)

    # 4) Forced extension + magic validation
    try:
        dc.validate_upload(filename, head, force_ext=bool(cfg.get("force_extension", True)))
    except dc.ValidationError as e:
        _safe_remove(stored)
        return _scan_error(str(e), 415)

    # 5) Analyze (read-only)
    opts = _scan_options_from_form(request.form)
    try:
        result = dc.analyze(stored, opts)
    except dc.ValidationError as e:
        _safe_remove(stored)
        return _scan_error(str(e), 415)
    except Exception as e:
        _safe_remove(stored)
        return _scan_error(f"Analysis failed: {e}", 500)
    finally:
        # We only needed the bytes for analysis; drop the upload immediately.
        _safe_remove(stored)

    payload = result.to_dict()
    payload["id"] = uid
    payload["created"] = int(time.time())
    with open(result_path(uid), "w") as rf:
        json.dump(payload, rf)

    return redirect(url_for("result", rid=uid))


def _scan_options_from_form(form) -> dc.ScanOptions:
    def _int(name, default=None):
        v = (form.get(name) or "").strip()
        if not v:
            return default
        try:
            return int(v, 0)
        except ValueError:
            return default

    patterns_raw = (form.get("patterns") or "").strip()
    patterns = [p.strip() for p in patterns_raw.replace(",", "\n").splitlines() if p.strip()] or ["\\x00"]
    sections_raw = (form.get("scan_sections") or "").strip()
    skip_raw = (form.get("skip_sections") or "").strip()
    return dc.ScanOptions(
        patterns=patterns,
        min_size=max(1, _int("min_size", 32) or 32),
        scan_sections=[s.strip() for s in sections_raw.split(",") if s.strip()] or None,
        skip_sections=[s.strip() for s in skip_raw.split(",") if s.strip()] or None,
        min_offset=_int("min_offset"),
        max_offset=_int("max_offset"),
        align=_int("align"),
        disasm_filter=bool(form.get("disasm_filter")),
        exclude_code=bool(form.get("exclude_code")),
        top=_int("top"),
    )


def _scan_error(message, code=400):
    if request.headers.get("X-Requested-With") == "DungeonFinder":
        return jsonify({"error": message}), code
    return render_template("error.html", message=message, code=code), code


@app.route("/result/<rid>")
def result(rid):
    cfg = load_config()
    data = load_result(rid)
    if not data:
        return render_template(
            "error.html",
            message="This report has expired or does not exist. Reports are "
                    "deleted automatically after the retention window.",
            code=404), 404
    return render_template("result.html", r=data, cfg=cfg,
                           ttl_left=retention_left(rid, cfg), admin=is_admin())


@app.route("/result/<rid>/download.<fmt>")
def download(rid, fmt):
    data = load_result(rid)
    if not data:
        abort(404)
    if fmt == "json":
        buf = io.BytesIO(json.dumps(data, indent=2).encode())
        return send_file(buf, mimetype="application/json", as_attachment=True,
                         download_name=f"dungeonfinder_{rid}.json")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["pattern", "offset", "offset_hex", "size", "section", "is_code"])
        for c in data.get("caves", []):
            w.writerow([c["pattern"], c["offset"], c["offset_hex"], c["size"],
                        c["section"], c.get("is_code")])
        out = io.BytesIO(buf.getvalue().encode())
        return send_file(out, mimetype="text/csv", as_attachment=True,
                         download_name=f"dungeonfinder_{rid}.csv")
    abort(404)


# --------------------------------------------------------------------------- #
#  Admin routes
# --------------------------------------------------------------------------- #
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    cfg = load_config()
    resolver = resolve_admin_hash(cfg)
    if request.method == "POST":
        pw = request.form.get("password", "")
        ok = False
        if resolver:
            kind, val = resolver
            ok = (pw == val) if kind == "env" else verify_password(pw, val)
        if ok:
            session["is_admin"] = True
            session.permanent = False
            return redirect(request.args.get("next") or url_for("admin"))
        flash("Incorrect password.")
    return render_template("admin_login.html",
                           configured=resolver is not None)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    cfg = load_config()
    if request.method == "POST":
        def _posint(name, lo, hi, cur):
            try:
                return max(lo, min(hi, int(request.form.get(name, cur))))
            except (TypeError, ValueError):
                return cur
        cfg["max_file_size_mb"] = _posint("max_file_size_mb", 1, 1024, cfg["max_file_size_mb"])
        cfg["retention_minutes"] = _posint("retention_minutes", 1, 10080, cfg["retention_minutes"])
        cfg["hashcash_base_bits"] = _posint("hashcash_base_bits", 1, 30, cfg["hashcash_base_bits"])
        cfg["hashcash_max_bits"] = _posint("hashcash_max_bits", cfg["hashcash_base_bits"], 30, cfg["hashcash_max_bits"])
        cfg["force_extension"] = bool(request.form.get("force_extension"))
        cfg["hashcash_adaptive"] = bool(request.form.get("hashcash_adaptive"))
        cfg["feed_enabled"] = bool(request.form.get("feed_enabled"))
        fh = request.form.get("feed_hash", cfg["feed_hash"])
        cfg["feed_hash"] = fh if fh in FEED_HASHES else cfg["feed_hash"]
        cfg["feed_max"] = _posint("feed_max", 1, 100, cfg["feed_max"])
        save_config(cfg)
        flash("Settings saved.")
        return redirect(url_for("admin"))

    stats = {
        "uploads_pending": len(os.listdir(UPLOAD_DIR)),
        "reports_live": len([x for x in os.listdir(RESULT_DIR) if x.endswith(".json")]),
        "current_bits": hashcash.current_bits(client_ip()),
    }
    return render_template("admin.html", cfg=cfg, stats=stats,
                           feed_hashes=FEED_HASHES,
                           env_pw=bool(os.environ.get("DUNGEONFINDER_ADMIN_PASSWORD")))


@app.route("/admin/purge", methods=["POST"])
@admin_required
def admin_purge():
    n = 0
    for folder in (UPLOAD_DIR, RESULT_DIR):
        for name in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, name))
                n += 1
            except Exception:
                pass
    flash(f"Purged {n} file(s).")
    return redirect(url_for("admin"))


@app.route("/about")
def about():
    return render_template("about.html", allowed=", ".join(dc.ALLOWED_EXTENSIONS))


def _safe_remove(path):
    try:
        os.remove(path)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _cli():
    if len(sys.argv) >= 2 and sys.argv[1] == "set-password":
        cfg = load_config()
        pw = getpass.getpass("New admin password: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2 or not pw:
            print("Passwords did not match / empty.", file=sys.stderr)
            sys.exit(1)
        cfg["admin_password_hash"] = hash_password(pw)
        save_config(cfg)
        print("Admin password updated.")
        sys.exit(0)


def ensure_admin_password():
    """
    When launched from a terminal, make sure an admin password exists.
    Priority: DUNGEONFINDER_ADMIN_PASSWORD env var > stored hash > prompt now.
    """
    cfg = load_config()
    if os.environ.get("DUNGEONFINDER_ADMIN_PASSWORD"):
        print("[DungeonFinder] Admin password taken from DUNGEONFINDER_ADMIN_PASSWORD.")
        return
    if cfg.get("admin_password_hash"):
        print("[DungeonFinder] Using stored admin password "
              "(run 'python app.py set-password' to change it).")
        return
    if not sys.stdin.isatty():
        print("[DungeonFinder] WARNING: no admin password set and no TTY to prompt. "
              "Set DUNGEONFINDER_ADMIN_PASSWORD or run 'python app.py set-password'.",
              file=sys.stderr)
        return
    print("[DungeonFinder] No admin password is set. Create one now.")
    while True:
        pw = getpass.getpass("  Set admin password: ")
        if not pw:
            print("  Password cannot be empty.")
            continue
        if pw != getpass.getpass("  Confirm admin password: "):
            print("  Passwords did not match, try again.")
            continue
        break
    cfg["admin_password_hash"] = hash_password(pw)
    save_config(cfg)
    print("[DungeonFinder] Admin password set.\n")


if __name__ == "__main__":
    _cli()
    ensure_admin_password()
    port = int(os.environ.get("PORT", 5000))
    print(f"[DungeonFinder] Serving on http://0.0.0.0:{port}  (admin at /admin)")
    app.run(host="0.0.0.0", port=port, debug=False)
