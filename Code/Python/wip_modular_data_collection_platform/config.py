"""Central configuration for the OSINT platform.

Values are read from environment variables where it makes sense so the same
code can run unchanged across machines. For a self-hosted deployment the
defaults are safe, but you MUST set a real SECRET_KEY in production.
"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # --- Core ---------------------------------------------------------------
    SECRET_KEY = os.environ.get("OSINT_SECRET_KEY", "dev-only-change-me")

    # SQLite lives in the instance folder. Swap this string for a Postgres/MySQL
    # URL later (e.g. postgresql+psycopg://user:pass@host/db) with no other code
    # changes required.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "OSINT_DATABASE_URI",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "osint.sqlite3"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Session / cookie hardening ----------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True once you terminate HTTPS in front of the app (recommended).
    SESSION_COOKIE_SECURE = os.environ.get("OSINT_HTTPS", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    REMEMBER_COOKIE_HTTPONLY = True

    # --- Security policy ----------------------------------------------------
    # Characters rejected everywhere user input is accepted, and before any
    # outbound request is built. Defence-in-depth on top of parameterised
    # queries and URL-encoding (which are the real protections).
    BLACKLISTED_CHARS = ['"', "'", "\\", "%"]

    PASSWORD_MIN_LENGTH = 12
    # Symbols accepted in passwords (the blacklisted four are intentionally absent).
    PASSWORD_SYMBOLS = "!@#$^&*()-_=+[]{}<>?,.:;|/~`"

    # Failed-login lockout.
    LOGIN_MAX_FAILURES = 3
    LOGIN_LOCKOUT = timedelta(hours=1)

    # Generic per-route rate limits applied by Flask-Limiter.
    RATELIMIT_DEFAULT = "200 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("OSINT_RATELIMIT_URI", "memory://")

    # --- First-run bootstrap admin -----------------------------------------
    # Created automatically the first time the app starts if no admin exists.
    BOOTSTRAP_ADMIN_USER = os.environ.get("OSINT_ADMIN_USER", "admin")
    BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("OSINT_ADMIN_PASSWORD", "ChangeMe!2025xyz")

    # --- Outbound requests (used by modules) -------------------------------
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    OUTBOUND_TIMEOUT = 10          # seconds per request
    OUTBOUND_MAX_WORKERS = 20      # thread-pool size for concurrent checks

    MODULES_DIR = os.path.join(BASE_DIR, "modules")
