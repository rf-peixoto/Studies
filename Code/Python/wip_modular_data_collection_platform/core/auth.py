"""Authentication: registration, login (with IP lockout), logout."""
import re
from datetime import timezone

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Length

from .extensions import limiter
from .models import LoginAttempt, User, db, utcnow
from .security import (assert_clean, contains_blacklisted, get_flag,
                       hash_password, password_problems, verify_password)

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired()])


class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField("Password", validators=[DataRequired()])
    confirm = PasswordField("Confirm password", validators=[DataRequired()])


# --------------------------------------------------------------------------- #
# Lockout helpers
# --------------------------------------------------------------------------- #
def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def ip_block_remaining(ip: str):
    """Return remaining timedelta if this IP is locked out, else None."""
    row = db.session.get(LoginAttempt, ip)
    if row and row.blocked_until:
        remaining = _aware(row.blocked_until) - utcnow()
        if remaining.total_seconds() > 0:
            return remaining
    return None


def record_failure(ip: str) -> None:
    cfg = current_app.config
    row = db.session.get(LoginAttempt, ip)
    now = utcnow()
    if row is None:
        row = LoginAttempt(ip=ip, fail_count=0, first_failed_at=now)
        db.session.add(row)
    # Reset the window if the previous one has fully elapsed.
    if _aware(row.first_failed_at) + cfg["LOGIN_LOCKOUT"] < now:
        row.fail_count = 0
        row.first_failed_at = now
        row.blocked_until = None
    row.fail_count += 1
    if row.fail_count >= cfg["LOGIN_MAX_FAILURES"]:
        row.blocked_until = now + cfg["LOGIN_LOCKOUT"]
    db.session.commit()


def clear_failures(ip: str) -> None:
    row = db.session.get(LoginAttempt, ip)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


def _fmt(remaining) -> str:
    mins = int(remaining.total_seconds() // 60) + 1
    return f"{mins} minute{'s' if mins != 1 else ''}"


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if not get_flag("registration_open", default=True):
        return render_template("register_closed.html"), 403

    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        confirm = form.confirm.data
        errors = []

        if not USERNAME_RE.match(username) or contains_blacklisted(username):
            errors.append("Username must be 3–64 chars: letters, digits, _ . - only.")
        if password != confirm:
            errors.append("Passwords do not match.")
        errors.extend(password_problems(password))
        if db.session.query(User).filter_by(username=username).first():
            errors.append("That username is taken.")

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            user = User(username=username, password_hash=hash_password(password))
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can sign in now.", "success")
            return redirect(url_for("auth.login"))

    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    ip = request.remote_addr or "unknown"

    if form.validate_on_submit():
        remaining = ip_block_remaining(ip)
        if remaining is not None:
            flash(f"Too many failed attempts. Try again in {_fmt(remaining)}.", "error")
            return render_template("login.html", form=form), 429

        username = form.username.data.strip()
        password = form.password.data

        # Reject forbidden characters before touching anything else.
        if contains_blacklisted(username) or contains_blacklisted(password):
            record_failure(ip)
            flash("Invalid credentials.", "error")
            return render_template("login.html", form=form)

        user = db.session.query(User).filter_by(username=username).first()
        if user is None or not verify_password(user.password_hash, password):
            record_failure(ip)
            flash("Invalid credentials.", "error")
            return render_template("login.html", form=form)

        if user.is_banned:
            flash(f"This account is banned. ({user.ban_label})", "error")
            return render_template("login.html", form=form)

        clear_failures(ip)
        login_user(user)
        flash(f"Welcome back, {user.username}.", "success")
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("dashboard.index"))

    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login"))
