"""Application factory.

Creates the Flask app, initialises extensions, registers core blueprints,
discovers and registers module blueprints, and installs the request-time gates
(maintenance mode, banned-user check, per-module enable/disable).
"""
import os

from flask import (Flask, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFProtect

from .extensions import limiter, login_manager
from .models import ModuleState, User, db
from .module_loader import discover_and_register, require_module_enabled
from .security import get_flag, hash_password

csrf = CSRFProtect()


def create_app(config_object="config.Config") -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        instance_relative_config=False,
    )
    app.config.from_object(config_object)
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "instance"), exist_ok=True)

    # --- Extensions --------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Blueprints --------------------------------------------------------
    from .auth import bp as auth_bp
    from .dashboard import bp as dashboard_bp
    from .admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    # --- Modules -----------------------------------------------------------
    discover_and_register(app)

    # --- First-run setup ---------------------------------------------------
    with app.app_context():
        db.create_all()
        _ensure_bootstrap_admin(app)

    # --- Request-time gates ------------------------------------------------
    @app.before_request
    def _gate():
        endpoint = request.endpoint or ""

        # Always allow static assets and the auth flow.
        if endpoint.startswith("static") or endpoint.startswith("auth."):
            return None

        # Banned users are signed out immediately.
        if current_user.is_authenticated and current_user.is_banned:
            label = current_user.ban_label
            logout_user()
            flash(f"Your account is banned. ({label})", "error")
            return redirect(url_for("auth.login"))

        # Maintenance mode blocks everyone except admins.
        if get_flag("maintenance_mode", default=False):
            if not (current_user.is_authenticated and current_user.is_admin):
                return render_template("maintenance.html"), 503

        # Per-module enable/disable gate.
        if endpoint.startswith("mod_") or endpoint.startswith("modcfg_"):
            module_id = endpoint.split(".", 1)[0].split("_", 1)[1]
            state = db.session.get(ModuleState, module_id)
            enabled = state.enabled if state else True
            require_module_enabled(module_id, enabled)
        return None

    # --- Error pages -------------------------------------------------------
    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403,
                               message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404,
                               message="That page could not be found."), 404

    @app.errorhandler(429)
    def too_many(_):
        return render_template("error.html", code=429,
                               message="Too many requests. Slow down and retry shortly."), 429

    # Expose a couple of helpers to every template.
    @app.context_processor
    def _inject():
        return {"maintenance_on": get_flag("maintenance_mode", default=False)}

    return app


def _ensure_bootstrap_admin(app) -> None:
    """Create the initial admin account on first run if none exists."""
    if db.session.query(User).filter_by(is_admin=True).first():
        return
    username = app.config["BOOTSTRAP_ADMIN_USER"]
    password = app.config["BOOTSTRAP_ADMIN_PASSWORD"]
    admin = User(username=username, password_hash=hash_password(password), is_admin=True)
    db.session.add(admin)
    db.session.commit()
    app.logger.warning(
        "Created bootstrap admin '%s'. Change its password immediately.", username)
