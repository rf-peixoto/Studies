"""Module discovery and registration.

A "module" is a Python package placed in the modules/ directory. The loader
imports each package, reads its MANIFEST, and registers its blueprint(s).

Contract a module package must satisfy (documented fully in the README):

    MANIFEST = {
        "id": "usernames",            # unique, [a-z0-9_], matches folder name
        "name": "Usernames",          # shown in the UI
        "description": "…",
        "version": "1.0.0",
        "author": "you",
        "has_config": True,           # exposes an admin config screen?
    }

    def create_blueprint() -> flask.Blueprint: ...        # required, user-facing
    def create_config_blueprint() -> flask.Blueprint: ... # required iff has_config

Lifecycle:
  * Drop a module folder in modules/ and (re)start the app — its routes appear.
  * Enable/disable from the admin UI — takes effect immediately (request-time
    gate), no restart needed.
  * Delete from the admin UI — removes the folder and its stored config.
"""
import importlib
import os
import re
import shutil
import sys

from flask import abort

ID_RE = re.compile(r"^[a-z0-9_]+$")

# Populated at registration time: module_id -> dict(manifest, import_error)
REGISTRY: dict[str, dict] = {}


def _candidate_dirs(modules_dir: str) -> list[str]:
    if not os.path.isdir(modules_dir):
        return []
    out = []
    for name in sorted(os.listdir(modules_dir)):
        path = os.path.join(modules_dir, name)
        if name.startswith((".", "_")):
            continue
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "__init__.py")):
            out.append(name)
    return out


def discover_and_register(app) -> None:
    """Import every module package and register its blueprints on the app."""
    project_root = os.path.dirname(app.config["MODULES_DIR"])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    REGISTRY.clear()

    for name in _candidate_dirs(app.config["MODULES_DIR"]):
        entry = {"manifest": None, "import_error": None}
        REGISTRY[name] = entry
        try:
            pkg = importlib.import_module(f"modules.{name}")
            manifest = getattr(pkg, "MANIFEST", None)
            if not isinstance(manifest, dict):
                raise ValueError("MANIFEST dict is missing.")
            mid = manifest.get("id")
            if not mid or not ID_RE.match(mid):
                raise ValueError("MANIFEST id must match [a-z0-9_].")
            if mid != name:
                raise ValueError(f"MANIFEST id '{mid}' must match folder '{name}'.")
            entry["manifest"] = manifest

            # User-facing blueprint -> /m/<id>
            user_bp = pkg.create_blueprint()
            user_bp.name = f"mod_{mid}"
            app.register_blueprint(user_bp, url_prefix=f"/m/{mid}")

            # Optional admin config blueprint -> /admin/modules/<id>
            if manifest.get("has_config"):
                cfg_bp = pkg.create_config_blueprint()
                cfg_bp.name = f"modcfg_{mid}"
                app.register_blueprint(cfg_bp, url_prefix=f"/admin/modules/{mid}")
        except Exception as exc:  # noqa: BLE001 — surface any import problem in UI
            entry["import_error"] = f"{type(exc).__name__}: {exc}"
            app.logger.warning("Module '%s' failed to load: %s", name, entry["import_error"])


def loaded_manifests() -> list[dict]:
    """Return manifest info for every discovered module (for the admin panel)."""
    items = []
    for mid, entry in REGISTRY.items():
        m = entry["manifest"] or {}
        items.append({
            "id": mid,
            "name": m.get("name", mid),
            "description": m.get("description", ""),
            "version": m.get("version", "?"),
            "author": m.get("author", "?"),
            "has_config": bool(m.get("has_config")),
            "import_error": entry["import_error"],
        })
    return sorted(items, key=lambda x: x["name"].lower())


def module_exists(module_id: str) -> bool:
    return module_id in REGISTRY and REGISTRY[module_id]["manifest"] is not None


def require_module_enabled(module_id: str, enabled: bool) -> None:
    """Called by the request-time gate; 404s if the module is gone or disabled."""
    if not module_exists(module_id) or not enabled:
        abort(404)


def delete_module_files(modules_dir: str, module_id: str) -> None:
    """Remove a module's folder from disk. Routes vanish on next restart; the
    admin panel also disables it so it is inaccessible immediately."""
    if not ID_RE.match(module_id):
        raise ValueError("Invalid module id.")
    target = os.path.join(modules_dir, module_id)
    # Guard against path traversal: target must be a direct child of modules_dir.
    if os.path.dirname(os.path.abspath(target)) != os.path.abspath(modules_dir):
        raise ValueError("Refusing to delete outside the modules directory.")
    if os.path.isdir(target):
        shutil.rmtree(target)
