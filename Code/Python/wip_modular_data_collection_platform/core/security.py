"""Security helpers shared across the core and exposed to modules.

Modules are expected to import the validators here (see README) so the whole
platform enforces one consistent input policy.
"""
from datetime import timedelta
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user

from .models import Setting, db

_hasher = PasswordHasher()


# --------------------------------------------------------------------------- #
# Password hashing (argon2)
# --------------------------------------------------------------------------- #
def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(stored_hash: str, raw: str) -> bool:
    try:
        return _hasher.verify(stored_hash, raw)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #
def contains_blacklisted(value: str) -> bool:
    """True if the string contains any globally forbidden character."""
    if value is None:
        return False
    blacklist = current_app.config["BLACKLISTED_CHARS"]
    return any(ch in value for ch in blacklist)


def assert_clean(value: str) -> str:
    """Return the value if clean, else raise ValueError. Use before any
    outbound request or whenever you accept free text from a user."""
    if contains_blacklisted(value):
        bad = " ".join(current_app.config["BLACKLISTED_CHARS"])
        raise ValueError(f"Input contains a forbidden character ({bad}).")
    return value


def password_problems(pw: str) -> list[str]:
    """Return a list of human-readable reasons the password is too weak.
    Empty list means the password passes policy."""
    cfg = current_app.config
    problems = []
    if len(pw) < cfg["PASSWORD_MIN_LENGTH"]:
        problems.append(f"At least {cfg['PASSWORD_MIN_LENGTH']} characters.")
    if not any(c.isupper() for c in pw):
        problems.append("At least one uppercase letter.")
    if not any(c.islower() for c in pw):
        problems.append("At least one lowercase letter.")
    if not any(c.isdigit() for c in pw):
        problems.append("At least one digit.")
    symbols = set(cfg["PASSWORD_SYMBOLS"])
    if not any(c in symbols for c in pw):
        problems.append("At least one symbol (" + cfg["PASSWORD_SYMBOLS"][:8] + " …).")
    if contains_blacklisted(pw):
        problems.append("Cannot contain " + " ".join(cfg["BLACKLISTED_CHARS"]) + ".")
    return problems


# --------------------------------------------------------------------------- #
# Platform settings (key/value flags)
# --------------------------------------------------------------------------- #
def get_setting(key: str, default: str = "") -> str:
    row = db.session.get(Setting, key)
    return row.value if row else default


def set_setting(key: str, value: str) -> None:
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)
    db.session.commit()


def get_flag(key: str, default: bool = False) -> bool:
    return get_setting(key, "1" if default else "0") == "1"


def set_flag(key: str, value: bool) -> None:
    set_setting(key, "1" if value else "0")


# --------------------------------------------------------------------------- #
# Access-control decorators
# --------------------------------------------------------------------------- #
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped
