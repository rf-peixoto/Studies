"""Database models.

Kept deliberately small. Module-specific data is NOT modelled here — modules
store their own configuration as a JSON blob via the ModuleConfig table, so the
core schema never needs to know what any module stores. That is what keeps
modules drop-in and removable.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    # Ban state. ban_permanent wins; otherwise banned while now < ban_until.
    ban_permanent = db.Column(db.Boolean, default=False, nullable=False)
    ban_until = db.Column(db.DateTime, nullable=True)

    @property
    def is_banned(self) -> bool:
        if self.ban_permanent:
            return True
        if self.ban_until is None:
            return False
        until = self.ban_until
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return utcnow() < until

    @property
    def ban_label(self) -> str:
        if self.ban_permanent:
            return "Permanent"
        if self.is_banned:
            return f"Until {self.ban_until:%Y-%m-%d %H:%M} UTC"
        return "Active"


class LoginAttempt(db.Model):
    """Tracks failed logins per client IP to enforce the lockout policy."""
    __tablename__ = "login_attempts"

    ip = db.Column(db.String(64), primary_key=True)
    fail_count = db.Column(db.Integer, default=0, nullable=False)
    first_failed_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    blocked_until = db.Column(db.DateTime, nullable=True)


class Setting(db.Model):
    """Simple key/value store for platform-wide flags."""
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)


class ModuleState(db.Model):
    """Enable/disable state for a discovered module (keyed by module id)."""
    __tablename__ = "module_states"

    module_id = db.Column(db.String(64), primary_key=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)


class ModuleConfig(db.Model):
    """Opaque JSON configuration owned by a module. The core never inspects it."""
    __tablename__ = "module_configs"

    module_id = db.Column(db.String(64), primary_key=True)
    data = db.Column(db.Text, nullable=False, default="{}")
