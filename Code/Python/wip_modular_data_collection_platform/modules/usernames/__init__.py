"""Usernames — a Sherlock-style username OSINT module.

Reference implementation for the platform's module system. Read the README's
"Writing a module" section alongside this file: every contract used here
(MANIFEST, create_blueprint, create_config_blueprint, the core helpers) is
documented there.
"""
import re
import uuid

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for, current_app)
from flask_login import login_required

# Helpers provided by the platform core. These three imports are the entire
# surface a module depends on.
from core.security import admin_required, assert_clean, contains_blacklisted
from core.store import get_module_config, save_module_config

from . import checker

MODULE_ID = "usernames"

MANIFEST = {
    "id": MODULE_ID,
    "name": "Usernames",
    "description": "Check whether a username exists across a configurable list "
                   "of sites, Sherlock-style, and open any hit in a new tab.",
    "version": "1.0.0",
    "author": "OSINT Console",
    "has_config": True,
}

# Username the operator types: letters, digits and a few safe separators only.
INPUT_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

DEFAULT_CONFIG = {"targets": []}


def _load_targets() -> list[dict]:
    return get_module_config(MODULE_ID, DEFAULT_CONFIG).get("targets", [])


def _save_targets(targets: list[dict]) -> None:
    save_module_config(MODULE_ID, {"targets": targets})


# --------------------------------------------------------------------------- #
# User-facing blueprint  ->  /m/usernames
# --------------------------------------------------------------------------- #
def create_blueprint() -> Blueprint:
    bp = Blueprint(MODULE_ID, __name__, template_folder="templates")

    @bp.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        results, username, error = None, "", None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            if not username or contains_blacklisted(username) or not INPUT_RE.match(username):
                error = "Enter a username (1–64 chars: letters, digits, _ . - only)."
            else:
                cfg = current_app.config
                results = checker.run_checks(
                    _load_targets(), username,
                    user_agent=cfg["DEFAULT_USER_AGENT"],
                    timeout=cfg["OUTBOUND_TIMEOUT"],
                    max_workers=cfg["OUTBOUND_MAX_WORKERS"],
                )
                if not results:
                    error = "No targets are configured yet. Ask an admin to add some."
        return render_template("usernames_index.html",
                               results=results, username=username, error=error)

    return bp


# --------------------------------------------------------------------------- #
# Admin config blueprint  ->  /admin/modules/usernames
# --------------------------------------------------------------------------- #
def create_config_blueprint() -> Blueprint:
    bp = Blueprint(MODULE_ID + "_cfg", __name__, template_folder="templates")

    @bp.route("/", methods=["GET"])
    @admin_required
    def config():
        return render_template("usernames_config.html",
                               targets=_load_targets(),
                               methods=checker.METHODS)

    @bp.route("/add", methods=["POST"])
    @admin_required
    def add():
        targets = _load_targets()
        targets.append(_target_from_form(request.form, new=True))
        _save_targets(targets)
        flash("Target added.", "success")
        return redirect(url_for(".config"))

    @bp.route("/update/<target_id>", methods=["POST"])
    @admin_required
    def update(target_id):
        targets = _load_targets()
        for t in targets:
            if t["id"] == target_id:
                updated = _target_from_form(request.form, new=False)
                updated["id"] = target_id
                t.update(updated)
                break
        else:
            abort(404)
        _save_targets(targets)
        flash("Target updated.", "success")
        return redirect(url_for(".config"))

    @bp.route("/delete/<target_id>", methods=["POST"])
    @admin_required
    def delete(target_id):
        targets = [t for t in _load_targets() if t["id"] != target_id]
        _save_targets(targets)
        flash("Target removed.", "success")
        return redirect(url_for(".config"))

    return bp


def _target_from_form(form, *, new: bool) -> dict:
    """Validate and normalise an admin-submitted target. Rejects blacklisted
    characters in the URL and match string before they are ever stored/used."""
    url = (form.get("url") or "").strip()
    name = (form.get("name") or "").strip()
    match = (form.get("match") or "").strip()
    method = form.get("method", checker.METHOD_STATUS)

    if not url:
        abort(400, "URL is required.")
    if method not in checker.METHODS:
        method = checker.METHOD_STATUS
    # Defence-in-depth: forbidden characters never reach an outbound request.
    try:
        assert_clean(url)
        assert_clean(match)
        assert_clean(name)
    except ValueError as exc:
        abort(400, str(exc))

    try:
        codes = [int(c) for c in (form.get("expected_status") or "200").replace(",", " ").split()]
    except ValueError:
        codes = [200]

    target = {
        "name": name or url,
        "url": url,
        "method": method,
        "expected_status": codes,
        "match": match,
        "enabled": form.get("enabled", "on") == "on",
    }
    if new:
        target["id"] = uuid.uuid4().hex[:12]
    return target
