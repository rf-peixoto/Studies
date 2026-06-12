"""Admin panel: manage users, modules, and platform settings."""
from datetime import timedelta

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from .models import ModuleState, User, db, utcnow
from .module_loader import (delete_module_files, loaded_manifests,
                            module_exists)
from .security import admin_required, get_flag, set_flag
from .store import delete_module_config

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _module_state(module_id: str) -> ModuleState:
    state = db.session.get(ModuleState, module_id)
    if state is None:
        state = ModuleState(module_id=module_id, enabled=True)
        db.session.add(state)
        db.session.commit()
    return state


@bp.route("/")
@admin_required
def index():
    users = db.session.query(User).count()
    modules = loaded_manifests()
    enabled_states = {s.module_id: s.enabled for s in db.session.query(ModuleState).all()}
    return render_template(
        "admin/index.html",
        user_count=users,
        modules=modules,
        enabled_states=enabled_states,
        registration_open=get_flag("registration_open", default=True),
        maintenance=get_flag("maintenance_mode", default=False),
    )


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@bp.route("/users")
@admin_required
def users():
    rows = db.session.query(User).order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=rows)


@bp.route("/users/<int:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    if user.id == current_user.id:
        flash("You cannot ban yourself.", "error")
        return redirect(url_for("admin.users"))
    if user.is_admin:
        flash("Admins cannot be banned.", "error")
        return redirect(url_for("admin.users"))

    mode = request.form.get("mode", "permanent")
    if mode == "permanent":
        user.ban_permanent = True
        user.ban_until = None
        flash(f"{user.username} is banned permanently.", "success")
    else:
        try:
            hours = max(1, int(request.form.get("hours", "24")))
        except ValueError:
            hours = 24
        user.ban_permanent = False
        user.ban_until = utcnow() + timedelta(hours=hours)
        flash(f"{user.username} is banned for {hours}h.", "success")
    db.session.commit()
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    user.ban_permanent = False
    user.ban_until = None
    db.session.commit()
    flash(f"{user.username} is unbanned.", "success")
    return redirect(url_for("admin.users"))


# --------------------------------------------------------------------------- #
# Modules
# --------------------------------------------------------------------------- #
@bp.route("/modules")
@admin_required
def modules():
    mods = loaded_manifests()
    enabled_states = {s.module_id: s.enabled for s in db.session.query(ModuleState).all()}
    return render_template(
        "admin/modules.html",
        modules=mods,
        enabled_states=enabled_states,
    )


@bp.route("/modules/<module_id>/toggle", methods=["POST"])
@admin_required
def toggle_module(module_id):
    if not module_exists(module_id):
        flash("Unknown module.", "error")
        return redirect(url_for("admin.modules"))
    state = _module_state(module_id)
    state.enabled = not state.enabled
    db.session.commit()
    flash(f"Module '{module_id}' {'enabled' if state.enabled else 'disabled'}.", "success")
    return redirect(url_for("admin.modules"))


@bp.route("/modules/<module_id>/delete", methods=["POST"])
@admin_required
def delete_module(module_id):
    # Disable first so it is inaccessible immediately, then remove from disk.
    state = _module_state(module_id)
    state.enabled = False
    db.session.commit()
    try:
        delete_module_files(current_app.config["MODULES_DIR"], module_id)
        delete_module_config(module_id)
        db.session.delete(state)
        db.session.commit()
        flash(f"Module '{module_id}' deleted. Restart to fully unload its routes.",
              "success")
    except Exception as exc:  # noqa: BLE001
        flash(f"Could not delete module: {exc}", "error")
    return redirect(url_for("admin.modules"))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@bp.route("/settings", methods=["POST"])
@admin_required
def settings():
    set_flag("registration_open", request.form.get("registration_open") == "on")
    set_flag("maintenance_mode", request.form.get("maintenance_mode") == "on")
    flash("Settings saved.", "success")
    return redirect(url_for("admin.index"))
