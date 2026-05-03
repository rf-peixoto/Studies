#!/usr/bin/env python3
"""
VAULTTERM v2.0 -- CYBERDECK EDITION
AES-256 ENCRYPTED // PBKDF2-600K // FIELD-LEVEL CRYPTO
"""

import os, sys, sqlite3, secrets, string, base64, json
import time, getpass, shutil, threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# ── dependency bootstrap ──────────────────────────────────────────────────────

def _install(pkg: str):
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"],
        check=True
    )

for _m, _p in [("rich", "rich"), ("cryptography", "cryptography"), ("pyperclip", "pyperclip")]:
    try:
        __import__(_m)
    except ImportError:
        print(f"[SYS] installing {_p}...")
        _install(_p)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.rule import Rule
from rich import box

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    import pyperclip
    _CLIP = True
except Exception:
    _CLIP = False

# ── constants ─────────────────────────────────────────────────────────────────

VERSION      = "2.0"
VAULT_DIR    = Path.home() / ".vaultterm"
DB_PATH      = VAULT_DIR / "vault.db"
META_PATH    = VAULT_DIR / "meta.json"
EXPIRY_DAYS  = 45
PW_MIN_LEN   = 16
PW_MAX_LEN   = 64
MAX_ATTEMPTS = 5
KDF_ITERS    = 600_000
SENTINEL     = "VAULTTERM::ONLINE::v2"

console = Console()

# ── colour palette ────────────────────────────────────────────────────────────
#   primary   = bright_cyan    (headers, keys, highlights)
#   accent    = green          (success, active)
#   warn      = yellow         (expiry, caution)
#   danger    = bright_red     (errors, expired, delete)
#   dim       = grey50 / dim   (secondary text)
#   data      = white          (user data, values)
#   pw        = bright_yellow  (revealed passwords)

C_HEAD  = "bright_cyan"
C_KEY   = "bright_cyan"
C_OK    = "green"
C_WARN  = "yellow"
C_ERR   = "bright_red"
C_DIM   = "grey50"
C_DATA  = "white"
C_PW    = "bright_yellow"
C_LABEL = "cyan"

# ── crypto ────────────────────────────────────────────────────────────────────

class Crypto:
    def __init__(self):
        self._f: Optional[Fernet] = None

    def _key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=KDF_ITERS)
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def init(self, password: str, salt: bytes):
        self._f = Fernet(self._key(password, salt))

    def enc(self, s: str) -> str:
        if not self._f: raise RuntimeError("crypto not ready")
        return self._f.encrypt(s.encode()).decode()

    def dec(self, token: str) -> str:
        if not self._f: raise RuntimeError("crypto not ready")
        return self._f.decrypt(token.encode()).decode()

    def verify(self, password: str, salt: bytes, token: str) -> bool:
        try:
            Fernet(self._key(password, salt)).decrypt(token.encode())
            return True
        except Exception:
            return False

# ── database ──────────────────────────────────────────────────────────────────

class DB:
    def __init__(self, path: Path, crypto: Crypto):
        self.path   = path
        self.crypto = crypto
        self._db: Optional[sqlite3.Connection] = None

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._schema()

    def _schema(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                url        TEXT NOT NULL DEFAULT '',
                login      TEXT NOT NULL,
                password   TEXT NOT NULL,
                notes      TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL,
                action    TEXT NOT NULL,
                entry_id  INTEGER,
                detail    TEXT NOT NULL DEFAULT ''
            );
        """)
        self._db.commit()

    def close(self):
        if self._db: self._db.close()

    # ── crud ──────────────────────────────────────────────────────────────────

    def add(self, name: str, url: str, login: str,
            password: str, notes: str = "") -> int:
        now = _ts()
        cur = self._db.execute(
            "INSERT INTO entries (name,url,login,password,notes,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, url,
             self.crypto.enc(login),
             self.crypto.enc(password),
             self.crypto.enc(notes) if notes else "",
             now, now)
        )
        self._db.commit()
        self._log("ADD", cur.lastrowid, name)
        return cur.lastrowid

    def update(self, eid: int, **kw):
        fields = {"updated_at": _ts()}
        for k, v in kw.items():
            if k in ("login", "password"):
                fields[k] = self.crypto.enc(v)
            elif k == "notes":
                fields[k] = self.crypto.enc(v) if v else ""
            else:
                fields[k] = v
        clause = ", ".join(f"{k}=?" for k in fields)
        self._db.execute(f"UPDATE entries SET {clause} WHERE id=?",
                         [*fields.values(), eid])
        self._db.commit()
        self._log("EDIT", eid, ", ".join(kw))

    def delete(self, eid: int, name: str = ""):
        self._db.execute("DELETE FROM entries WHERE id=?", (eid,))
        self._db.commit()
        self._log("PURGE", eid, name)

    def get_all(self) -> List[Dict]:
        rows = self._db.execute(
            "SELECT * FROM entries ORDER BY name"
        ).fetchall()
        return [self._dec(r) for r in rows]

    def get(self, eid: int) -> Optional[Dict]:
        r = self._db.execute(
            "SELECT * FROM entries WHERE id=?", (eid,)
        ).fetchone()
        return self._dec(r) if r else None

    def search(self, q: str) -> List[Dict]:
        like = f"%{q}%"
        rows = self._db.execute(
            "SELECT * FROM entries WHERE name LIKE ? OR url LIKE ? ORDER BY name",
            (like, like)
        ).fetchall()
        return [self._dec(r) for r in rows]

    def reencrypt(self, new_crypto: Crypto):
        rows = self._db.execute("SELECT * FROM entries").fetchall()
        for r in rows:
            d = dict(r)
            self._db.execute(
                "UPDATE entries SET login=?,password=?,notes=? WHERE id=?",
                (new_crypto.enc(self.crypto.dec(d["login"])),
                 new_crypto.enc(self.crypto.dec(d["password"])),
                 new_crypto.enc(self.crypto.dec(d["notes"])) if d["notes"] else "",
                 d["id"])
            )
        self._db.commit()
        self._log("REKEY", None, "master password changed -- all fields re-encrypted")

    # ── log ───────────────────────────────────────────────────────────────────

    def _log(self, action: str, eid, detail: str):
        self._db.execute(
            "INSERT INTO log (ts,action,entry_id,detail) VALUES (?,?,?,?)",
            (_ts(), action, eid, detail)
        )
        self._db.commit()

    def get_log(self, n: int = 60) -> List[Dict]:
        rows = self._db.execute(
            "SELECT * FROM log ORDER BY ts DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── helpers ───────────────────────────────────────────────────────────────

    def _dec(self, row: sqlite3.Row) -> Dict:
        d = dict(row)
        for f in ("login", "password"):
            try:    d[f] = self.crypto.dec(d[f])
            except: d[f] = "[ERR:DECRYPT]"
        if d.get("notes"):
            try:    d["notes"] = self.crypto.dec(d["notes"])
            except: d["notes"] = ""
        updated      = datetime.fromisoformat(d["updated_at"])
        d["age"]     = (datetime.now() - updated).days
        d["expired"] = d["age"] >= EXPIRY_DAYS
        return d

# ── meta (salt + verify token) ────────────────────────────────────────────────

class Meta:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def create(self, password: str, crypto: Crypto) -> bytes:
        salt = os.urandom(32)
        crypto.init(password, salt)
        data = {
            "version":      VERSION,
            "salt":         base64.b64encode(salt).decode(),
            "verify":       crypto.enc(SENTINEL),
            "created_at":   _ts(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
        return salt

    def load(self) -> Dict:
        return json.loads(self.path.read_text())

    def salt(self) -> bytes:
        return base64.b64decode(self.load()["salt"])

    def token(self) -> str:
        return self.load()["verify"]

    def update(self, salt: bytes, token: str):
        d = self.load()
        d["salt"]   = base64.b64encode(salt).decode()
        d["verify"] = token
        self.path.write_text(json.dumps(d, indent=2))

# ── password tools ────────────────────────────────────────────────────────────

def gen_pw(length: int = 20) -> str:
    length  = max(PW_MIN_LEN, min(PW_MAX_LEN, length))
    pool    = string.ascii_lowercase + string.ascii_uppercase + string.digits + "!@#$%^&*-_=+[]{}|;:,.<>?"
    seed    = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*-_=+[]{}|;:,.<>?"),
    ]
    rest    = [secrets.choice(pool) for _ in range(length - len(seed))]
    chars   = seed + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

def strength(pw: str) -> Tuple[int, str, str]:
    s = 0
    if len(pw) >= 8:  s += 10
    if len(pw) >= 12: s += 10
    if len(pw) >= 16: s += 10
    if len(pw) >= 20: s += 10
    if any(c.islower() for c in pw): s += 10
    if any(c.isupper() for c in pw): s += 15
    if any(c.isdigit() for c in pw): s += 15
    if any(c in "!@#$%^&*-_=+[]{}|;:,.<>?" for c in pw): s += 20
    s = min(s, 100)
    if s < 30: return s, "CRITICAL",  C_ERR
    if s < 50: return s, "WEAK",      C_WARN
    if s < 70: return s, "MODERATE",  "yellow"
    if s < 85: return s, "STRONG",    C_OK
    return s,             "MAXSEC",   "bright_green"

def strength_bar(score: int, width: int = 24) -> Text:
    filled = int(score / 100 * width)
    _, _, color = strength("x" * 20)
    if score < 30:  color = C_ERR
    elif score < 50: color = C_WARN
    elif score < 70: color = "yellow"
    elif score < 85: color = C_OK
    else:            color = "bright_green"
    bar = "#" * filled + "." * (width - filled)
    t = Text()
    t.append(f"[{bar}]", style=color)
    return t

# ── ui primitives ─────────────────────────────────────────────────────────────

def clr():
    os.system("cls" if os.name == "nt" else "clear")

def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")

def ln(style: str = C_DIM):
    console.print(Rule(style=style))

def ok(msg: str):
    console.print(f"\n  [{C_OK}][OK][/{C_OK}]  {msg}\n")

def err(msg: str):
    console.print(f"\n  [{C_ERR}][ERR][/{C_ERR}] {msg}\n")

def warn(msg: str):
    console.print(f"\n  [{C_WARN}][WARN][/{C_WARN}] {msg}\n")

def inf(msg: str):
    console.print(f"\n  [{C_HEAD}][SYS][/{C_HEAD}] {msg}\n")

def pause():
    console.print(f"  [{C_DIM}]press ENTER to continue...[/{C_DIM}]", end="")
    input()

def ask_pw(prompt: str = "password") -> str:
    return getpass.getpass(f"  {prompt} >> ")

def header(title: str):
    console.print()
    console.print(f"  [{C_HEAD}]>> {title}[/{C_HEAD}]")
    console.print(f"  [{C_DIM}]{'─' * (len(title) + 4)}[/{C_DIM}]")
    console.print()

def banner():
    console.print()
    w = console.width or 72
    line = "=" * w
    tag  = f"  VAULTTERM v{VERSION}  //  AES-256  //  PBKDF2-{KDF_ITERS//1000}K  //  CYBERDECK EDITION"
    console.print(f"[{C_HEAD}]{line}[/{C_HEAD}]")
    console.print(f"[{C_HEAD}]{tag}[/{C_HEAD}]")
    console.print(f"[{C_HEAD}]{line}[/{C_HEAD}]")
    console.print()

def _clip_clear(value: str, delay: int = 30):
    def _run():
        time.sleep(delay)
        try:
            if pyperclip.paste() == value:
                pyperclip.copy("")
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

# ── app ───────────────────────────────────────────────────────────────────────

class VaultTerm:

    def __init__(self):
        self.crypto = Crypto()
        self.meta   = Meta(META_PATH)
        self.db: Optional[DB] = None

    # ── boot ──────────────────────────────────────────────────────────────────

    def start(self):
        clr(); banner()
        if not self.meta.exists():
            self._init_vault()
        else:
            self._unlock()
        self._expiry_check()

    def _init_vault(self):
        console.print(f"  [{C_WARN}]NO VAULT DETECTED.[/{C_WARN}]")
        console.print(f"  [{C_DIM}]Initialising new encrypted vault at {VAULT_DIR}[/{C_DIM}]\n")
        console.print(f"  [{C_DIM}]Choose a master password (minimum 8 characters).[/{C_DIM}]")
        console.print(f"  [{C_DIM}]This password cannot be recovered if lost.[/{C_DIM}]\n")

        while True:
            pw  = ask_pw("master password")
            if len(pw) < 8:
                err("too short. minimum 8 characters."); continue
            pw2 = ask_pw("confirm master password")
            if pw != pw2:
                err("mismatch. try again."); continue

            sc, label, color = strength(pw)
            bar = strength_bar(sc)
            console.print(f"\n  strength  ", end="")
            console.print(bar, end="")
            console.print(f"  [{color}]{label}[/{color}] ({sc}/100)\n")

            if sc < 40:
                warn("low-entropy master password. consider something stronger.")
                if not Confirm.ask("  continue?", default=False):
                    continue
            break

        self.meta.create(pw, self.crypto)
        self.db = DB(DB_PATH, self.crypto)
        self.db.open()
        ok("vault initialised and encrypted.")
        time.sleep(0.6)

    def _unlock(self):
        console.print(f"  [{C_DIM}]vault found at {DB_PATH}[/{C_DIM}]\n")

        for attempt in range(MAX_ATTEMPTS):
            pw = ask_pw("master password")
            if self.crypto.verify(pw, self.meta.salt(), self.meta.token()):
                self.crypto.init(pw, self.meta.salt())
                self.db = DB(DB_PATH, self.crypto)
                self.db.open()
                ok("access granted.")
                time.sleep(0.3)
                return
            left = MAX_ATTEMPTS - attempt - 1
            if left:
                console.print(f"  [{C_ERR}]wrong password. {left} attempt(s) remaining.[/{C_ERR}]")

        err("too many failed attempts. terminating.")
        sys.exit(1)

    def _expiry_check(self):
        expired = [e for e in self.db.get_all() if e["expired"]]
        if not expired:
            return
        clr(); banner()
        console.print(f"  [{C_WARN}]!! EXPIRY ALERT !! {len(expired)} password(s) not rotated in {EXPIRY_DAYS}+ days.[/{C_WARN}]\n")
        t = Table(box=box.MINIMAL, show_header=True, header_style=f"bold {C_WARN}",
                  border_style=C_DIM, padding=(0, 2))
        t.add_column("ID",   width=5,  justify="right")
        t.add_column("NAME",           min_width=20)
        t.add_column("LOGIN",          min_width=18)
        t.add_column("DAYS OLD",       width=10, justify="right")
        for e in expired:
            t.add_row(str(e["id"]), e["name"], e["login"], f"[{C_WARN}]{e['age']}d[/{C_WARN}]")
        console.print(t)
        console.print(f"\n  [{C_DIM}]You are not required to update these now.[/{C_DIM}]")
        console.print(f"  [{C_DIM}]Expired entries are tagged [EXPIRED] in the vault listing.[/{C_DIM}]\n")
        pause()

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self):
        self.start()
        while True:
            clr(); banner()
            self._stats()
            self._menu()

    def _stats(self):
        entries = self.db.get_all()
        total   = len(entries)
        expired = sum(1 for e in entries if e["expired"])
        ec      = C_ERR if expired else C_OK

        console.print(
            f"  [{C_DIM}]entries[/{C_DIM}] [{C_HEAD}]{total:<4}[/{C_HEAD}]  "
            f"[{C_DIM}]expired[/{C_DIM}] [{ec}]{expired:<4}[/{ec}]  "
            f"[{C_DIM}]vault[/{C_DIM}] [{C_OK}]LOCKED[/{C_OK}]"
        )
        console.print()

    def _menu(self):
        items = [
            ("1", "LIST",     "display all vault entries"),
            ("2", "SEARCH",   "query by name or url"),
            ("3", "INJECT",   "add a new entry"),
            ("4", "MODIFY",   "edit an existing entry"),
            ("5", "PURGE",    "delete an entry"),
            ("6", "GENERATE", "standalone password generator"),
            ("7", "LOG",      "view audit trail"),
            ("8", "REKEY",    "change master password"),
            ("9", "CLONE",    "backup vault files"),
            ("0", "EJECT",    "lock vault and exit"),
        ]
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        t.add_column("K", width=3)
        t.add_column("CMD", width=10)
        t.add_column("DESC")
        for key, cmd, desc in items:
            t.add_row(
                f"[{C_KEY}][{key}][/{C_KEY}]",
                f"[{C_HEAD}]{cmd}[/{C_HEAD}]",
                f"[{C_DIM}]{desc}[/{C_DIM}]",
            )
        console.print(t)
        console.print()

        choice = Prompt.ask(f"  [{C_HEAD}]cmd[/{C_HEAD}]",
                            choices=[str(i) for i in range(10)],
                            show_choices=False)
        clr()
        {
            "1": self.cmd_list,
            "2": self.cmd_search,
            "3": self.cmd_inject,
            "4": self.cmd_modify,
            "5": self.cmd_purge,
            "6": self.cmd_generate,
            "7": self.cmd_log,
            "8": self.cmd_rekey,
            "9": self.cmd_clone,
            "0": self.cmd_eject,
        }[choice]()

    # ── [1] LIST ──────────────────────────────────────────────────────────────

    def cmd_list(self, entries: Optional[List[Dict]] = None, title: str = "VAULT LISTING"):
        if entries is None:
            entries = self.db.get_all()
        banner(); header(title)

        if not entries:
            inf("vault is empty. use INJECT [3] to add entries.")
            pause(); return

        t = self._entry_table(entries)
        console.print(t)
        console.print()
        self._entry_actions(entries)

    def _entry_table(self, entries: List[Dict]) -> Table:
        t = Table(
            box=box.MINIMAL,
            show_header=True,
            header_style=f"bold {C_HEAD}",
            border_style=C_DIM,
            padding=(0, 2),
        )
        t.add_column("ID",     width=5,  justify="right")
        t.add_column("NAME",             min_width=18)
        t.add_column("URL",              min_width=22)
        t.add_column("LOGIN",            min_width=18)
        t.add_column("AGE",    width=8,  justify="right")
        t.add_column("STATUS", width=14, justify="center")

        for e in entries:
            if e["expired"]:
                status = Text("[EXPIRED]", style=f"bold {C_ERR}")
                age_s  = Text(f"{e['age']}d", style=C_ERR)
                name_s = Text(e["name"], style=C_ERR)
            elif e["age"] > 20:
                status = Text("[EXPIRING]", style=C_WARN)
                age_s  = Text(f"{e['age']}d", style=C_WARN)
                name_s = Text(e["name"], style=C_DATA)
            else:
                status = Text("[ACTIVE]", style=C_OK)
                age_s  = Text(f"{e['age']}d", style=C_DIM)
                name_s = Text(e["name"], style=C_DATA)

            t.add_row(
                Text(str(e["id"]), style=C_DIM),
                name_s,
                Text(e.get("url", "") or "—", style=C_DIM),
                Text(e["login"], style=C_LABEL),
                age_s,
                status,
            )
        return t

    def _entry_actions(self, entries: List[Dict]):
        t = Table.grid(padding=(0, 4))
        t.add_column(); t.add_column(); t.add_column(); t.add_column()
        t.add_row(
            f"[{C_KEY}][C][/{C_KEY}] copy password",
            f"[{C_KEY}][V][/{C_KEY}] view entry",
            f"[{C_KEY}][U][/{C_KEY}] update password",
            f"[{C_KEY}][B][/{C_KEY}] back",
        )
        console.print(t)
        console.print()

        act = Prompt.ask(f"  [{C_HEAD}]action[/{C_HEAD}]",
                         choices=["c","C","v","V","u","U","b","B"],
                         show_choices=False, default="B").upper()
        if act == "C": self._copy(entries)
        elif act == "V": self._view(entries)
        elif act == "U": self._quick_update(entries)

    def _pick(self, entries: List[Dict], prompt: str = "id") -> Optional[Dict]:
        raw = Prompt.ask(f"  [{C_HEAD}]{prompt}[/{C_HEAD}]")
        try:
            eid = int(raw)
            hit = next((e for e in entries if e["id"] == eid), None)
            if not hit: err(f"no entry with id {eid}.")
            return hit
        except ValueError:
            err("expected a numeric id.")
            return None

    def _copy(self, entries: List[Dict]):
        if not _CLIP:
            err("clipboard unavailable. install xclip/xsel on linux.")
            pause(); return
        e = self._pick(entries, "entry id to copy")
        if not e: pause(); return
        pyperclip.copy(e["password"])
        ok(f"password for '{e['name']}' copied to clipboard.")
        console.print(f"  [{C_DIM}]clipboard will be cleared in 30 seconds.[/{C_DIM}]\n")
        _clip_clear(e["password"], 30)
        pause()

    def _view(self, entries: List[Dict]):
        e = self._pick(entries, "entry id to view")
        if not e: pause(); return

        sc, label, color = strength(e["password"])
        bar = strength_bar(sc)

        console.print()
        w = 52
        sep = f"  [{C_DIM}]{'─' * w}[/{C_DIM}]"

        def row(k: str, v: str, vc: str = C_DATA):
            pad = 10
            console.print(f"  [{C_DIM}]{k:<{pad}}[/{C_DIM}]  [{vc}]{v}[/{vc}]")

        console.print(sep)
        row("ID",       str(e["id"]),            C_DIM)
        row("NAME",     e["name"])
        row("URL",      e.get("url") or "—",     C_DIM)
        row("LOGIN",    e["login"],               C_LABEL)
        row("PASSWORD", e["password"],            C_PW)
        row("CREATED",  e["created_at"][:10],     C_DIM)
        row("UPDATED",  e["updated_at"][:10],     C_DIM)
        row("AGE",      f"{e['age']} day(s)",
            C_ERR if e["expired"] else C_DIM)
        if e.get("notes"):
            row("NOTES",    e["notes"],           C_DIM)
        console.print(f"  [{C_DIM}]STRENGTH  [/{C_DIM}]", end="")
        console.print(bar, end="")
        console.print(f"  [{color}]{label}[/{color}] ({sc}/100)")
        console.print(sep)
        console.print()
        pause()

    def _quick_update(self, entries: List[Dict]):
        e = self._pick(entries, "entry id to update password")
        if not e: pause(); return

        console.print(f"\n  updating password for [{C_HEAD}]{e['name']}[/{C_HEAD}]\n")
        console.print(f"  [{C_KEY}][G][/{C_KEY}] generate   [{C_KEY}][M][/{C_KEY}] manual entry\n")
        choice = Prompt.ask(f"  [{C_HEAD}]mode[/{C_HEAD}]",
                            choices=["g","G","m","M"], show_choices=False).upper()
        if choice == "G":
            pw = self._gen_pw()
        else:
            pw = self._manual_pw()
            if pw is None: pause(); return

        self.db.update(e["id"], password=pw)
        ok(f"password updated for '{e['name']}'.")
        pause()

    # ── [2] SEARCH ────────────────────────────────────────────────────────────

    def cmd_search(self):
        banner(); header("SEARCH")
        q = Prompt.ask(f"  [{C_HEAD}]query[/{C_HEAD}]")
        results = self.db.search(q)
        if not results:
            warn(f"no results for: {q}"); pause(); return
        self.cmd_list(results, title=f"SEARCH >> {q}  ({len(results)} match(es))")

    # ── [3] INJECT ────────────────────────────────────────────────────────────

    def cmd_inject(self):
        banner(); header("INJECT -- NEW ENTRY")

        name  = Prompt.ask(f"  [{C_HEAD}]name[/{C_HEAD}]   [{C_DIM}](service or site name)[/{C_DIM}]")
        url   = Prompt.ask(f"  [{C_HEAD}]url[/{C_HEAD}]    [{C_DIM}](optional, enter to skip)[/{C_DIM}]", default="")
        login = Prompt.ask(f"  [{C_HEAD}]login[/{C_HEAD}]  [{C_DIM}](username or email)[/{C_DIM}]")
        notes = Prompt.ask(f"  [{C_HEAD}]notes[/{C_HEAD}]  [{C_DIM}](optional)[/{C_DIM}]", default="")

        console.print()
        console.print(f"  [{C_KEY}][G][/{C_KEY}] generate password   [{C_KEY}][M][/{C_KEY}] enter manually\n")
        choice = Prompt.ask(f"  [{C_HEAD}]password mode[/{C_HEAD}]",
                            choices=["g","G","m","M"], show_choices=False).upper()

        if choice == "G":
            pw = self._gen_pw()
        else:
            pw = self._manual_pw()
            if pw is None: pause(); return

        # confirm
        console.print()
        sep = f"  [{C_DIM}]{'─' * 48}[/{C_DIM}]"
        console.print(sep)
        console.print(f"  [{C_DIM}]NAME   [/{C_DIM}]  [{C_DATA}]{name}[/{C_DATA}]")
        console.print(f"  [{C_DIM}]URL    [/{C_DIM}]  [{C_DIM}]{url or '—'}[/{C_DIM}]")
        console.print(f"  [{C_DIM}]LOGIN  [/{C_DIM}]  [{C_LABEL}]{login}[/{C_LABEL}]")
        console.print(f"  [{C_DIM}]PASS   [/{C_DIM}]  [{C_DIM}]{'*' * len(pw)}[/{C_DIM}]  [{C_DIM}]({len(pw)} chars)[/{C_DIM}]")
        console.print(sep)
        console.print()

        if Confirm.ask("  commit to vault?", default=True):
            eid = self.db.add(name, url, login, pw, notes)
            ok(f"entry injected. id={eid}")
        else:
            inf("aborted.")
        pause()

    # ── [4] MODIFY ────────────────────────────────────────────────────────────

    def cmd_modify(self):
        banner(); header("MODIFY -- EDIT ENTRY")
        entries = self.db.get_all()
        if not entries: inf("vault is empty."); pause(); return

        t = self._entry_table(entries)
        console.print(t)
        console.print()

        e = self._pick(entries, "entry id to modify")
        if not e: pause(); return

        console.print(f"\n  modifying [{C_HEAD}]{e['name']}[/{C_HEAD}]")
        console.print(f"  [{C_DIM}](press ENTER to keep current value)[/{C_DIM}]\n")

        name  = Prompt.ask(f"  [{C_HEAD}]name[/{C_HEAD}]",  default=e["name"])
        url   = Prompt.ask(f"  [{C_HEAD}]url[/{C_HEAD}]",   default=e.get("url",""))
        login = Prompt.ask(f"  [{C_HEAD}]login[/{C_HEAD}]", default=e["login"])
        notes = Prompt.ask(f"  [{C_HEAD}]notes[/{C_HEAD}]", default=e.get("notes",""))

        console.print()
        console.print(f"  [{C_KEY}][K][/{C_KEY}] keep password   [{C_KEY}][G][/{C_KEY}] generate   [{C_KEY}][M][/{C_KEY}] manual\n")
        pw_mode = Prompt.ask(f"  [{C_HEAD}]password[/{C_HEAD}]",
                             choices=["k","K","g","G","m","M"], show_choices=False).upper()

        updates: Dict = dict(name=name, url=url, login=login, notes=notes)
        if pw_mode == "G":
            updates["password"] = self._gen_pw()
        elif pw_mode == "M":
            pw = self._manual_pw()
            if pw: updates["password"] = pw

        self.db.update(e["id"], **updates)
        ok(f"entry {e['id']} modified.")
        pause()

    # ── [5] PURGE ─────────────────────────────────────────────────────────────

    def cmd_purge(self):
        banner(); header("PURGE -- DELETE ENTRY")
        entries = self.db.get_all()
        if not entries: inf("vault is empty."); pause(); return

        t = self._entry_table(entries)
        console.print(t)
        console.print()

        e = self._pick(entries, "entry id to purge")
        if not e: pause(); return

        console.print(f"\n  [{C_ERR}]target: {e['name']}  ({e['login']})[/{C_ERR}]")
        console.print(f"  [{C_WARN}]this action is irreversible.[/{C_WARN}]\n")

        if Confirm.ask("  confirm purge?", default=False):
            self.db.delete(e["id"], e["name"])
            ok(f"entry {e['id']} purged.")
        else:
            inf("aborted.")
        pause()

    # ── [6] GENERATE ──────────────────────────────────────────────────────────

    def cmd_generate(self):
        banner(); header("GENERATE -- STANDALONE")
        while True:
            pw = self._gen_pw()
            if _CLIP and Confirm.ask("  copy to clipboard?", default=True):
                pyperclip.copy(pw)
                ok("copied. clears in 30 seconds.")
                _clip_clear(pw, 30)
            if not Confirm.ask("  generate another?", default=False):
                break
        pause()

    # ── [7] LOG ───────────────────────────────────────────────────────────────

    def cmd_log(self):
        banner(); header("AUDIT LOG")
        logs = self.db.get_log(60)
        if not logs: inf("no log entries."); pause(); return

        t = Table(box=box.MINIMAL, show_header=True,
                  header_style=f"bold {C_HEAD}",
                  border_style=C_DIM, padding=(0, 2))
        t.add_column("TIMESTAMP",  width=20)
        t.add_column("ACTION",     width=8)
        t.add_column("ID",         width=5, justify="right")
        t.add_column("DETAIL")

        colors = {"ADD": C_OK, "EDIT": C_WARN, "PURGE": C_ERR,
                  "REKEY": "magenta"}
        for lg in logs:
            c = colors.get(lg["action"], C_DIM)
            t.add_row(
                Text(lg["ts"][:19], style=C_DIM),
                Text(lg["action"],  style=c),
                Text(str(lg["entry_id"] or "—"), style=C_DIM),
                Text(lg.get("detail",""), style=C_DIM),
            )
        console.print(t)
        pause()

    # ── [8] REKEY ─────────────────────────────────────────────────────────────

    def cmd_rekey(self):
        banner(); header("REKEY -- CHANGE MASTER PASSWORD")
        console.print(f"  [{C_DIM}]verify current master password first.[/{C_DIM}]\n")

        cur = ask_pw("current master password")
        if not self.crypto.verify(cur, self.meta.salt(), self.meta.token()):
            err("authentication failed."); pause(); return

        while True:
            new  = ask_pw("new master password (min 8 chars)")
            if len(new) < 8: err("too short."); continue
            new2 = ask_pw("confirm new master password")
            if new != new2: err("mismatch."); continue

            sc, label, color = strength(new)
            bar = strength_bar(sc)
            console.print(f"\n  strength  ", end="")
            console.print(bar, end="")
            console.print(f"  [{color}]{label}[/{color}] ({sc}/100)\n")

            if sc < 40 and not Confirm.ask("  weak password -- continue?", default=False):
                continue
            break

        if not Confirm.ask("  re-encrypt all vault data with new key?", default=True):
            inf("aborted."); pause(); return

        console.print(f"\n  [{C_DIM}]re-encrypting vault...[/{C_DIM}]")

        new_salt   = os.urandom(32)
        new_crypto = Crypto()
        new_crypto.init(new, new_salt)
        new_token  = new_crypto.enc(SENTINEL)

        self.db.reencrypt(new_crypto)
        self.meta.update(new_salt, new_token)
        self.crypto.init(new, new_salt)
        self.db.crypto = self.crypto

        ok("vault re-keyed. all fields re-encrypted with new master password.")
        pause()

    # ── [9] CLONE ─────────────────────────────────────────────────────────────

    def cmd_clone(self):
        banner(); header("CLONE -- BACKUP")
        dest = Path.home() / "Desktop"
        if not dest.exists():
            dest = Path.home()
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag  = f"vaultterm_{ts}"
        db_b  = dest / f"{tag}.db"
        meta_b = dest / f"{tag}.meta.json"
        shutil.copy2(DB_PATH,   db_b)
        shutil.copy2(META_PATH, meta_b)
        ok(f"backup written:\n  {db_b}\n  {meta_b}")
        warn("keep both files together. both required for restore.")
        pause()

    # ── [0] EJECT ─────────────────────────────────────────────────────────────

    def cmd_eject(self):
        if self.db: self.db.close()
        clr()
        w = console.width or 72
        line = "=" * w
        console.print()
        console.print(f"[{C_HEAD}]{line}[/{C_HEAD}]")
        console.print(f"[{C_HEAD}]  VAULT LOCKED  //  SESSION TERMINATED[/{C_HEAD}]")
        console.print(f"[{C_HEAD}]{line}[/{C_HEAD}]")
        console.print()
        sys.exit(0)

    # ── password helpers ──────────────────────────────────────────────────────

    def _gen_pw(self) -> str:
        raw = Prompt.ask(f"  [{C_HEAD}]length[/{C_HEAD}]  [{C_DIM}]({PW_MIN_LEN}–{PW_MAX_LEN})[/{C_DIM}]",
                         default="20")
        try:
            length = int(raw)
        except ValueError:
            length = 20

        pw    = gen_pw(length)
        sc, label, color = strength(pw)
        bar   = strength_bar(sc)

        console.print()
        console.print(f"  [{C_DIM}]generated  [/{C_DIM}][{C_PW}]{pw}[/{C_PW}]")
        console.print(f"  [{C_DIM}]strength   [/{C_DIM}]", end="")
        console.print(bar, end="")
        console.print(f"  [{color}]{label}[/{color}] ({sc}/100)")
        console.print()

        if not Confirm.ask("  use this password?", default=True):
            return self._gen_pw()
        return pw

    def _manual_pw(self) -> Optional[str]:
        while True:
            p1 = ask_pw("new password")
            p2 = ask_pw("confirm password")
            if p1 != p2:
                err("mismatch."); continue
            sc, label, color = strength(p1)
            bar = strength_bar(sc)
            console.print(f"\n  [{C_DIM}]strength   [/{C_DIM}]", end="")
            console.print(bar, end="")
            console.print(f"  [{color}]{label}[/{color}] ({sc}/100)\n")
            if sc < 30 and not Confirm.ask("  very weak -- continue?", default=False):
                continue
            return p1

# ── entry point ───────────────────────────────────────────────────────────────

def main():
    try:
        VaultTerm().run()
    except KeyboardInterrupt:
        console.print(f"\n\n  [{C_DIM}]interrupted -- vault locked.[/{C_DIM}]\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
