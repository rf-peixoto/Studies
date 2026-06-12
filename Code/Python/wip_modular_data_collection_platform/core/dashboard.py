"""User dashboard: lists the modules currently available to use."""
from flask import Blueprint, render_template
from flask_login import login_required

from .models import ModuleState, db
from .module_loader import loaded_manifests

bp = Blueprint("dashboard", __name__)


def available_modules() -> list[dict]:
    """Enabled, successfully-loaded modules, for the user-facing dashboard."""
    states = {s.module_id: s.enabled for s in db.session.query(ModuleState).all()}
    out = []
    for m in loaded_manifests():
        if m["import_error"]:
            continue
        if states.get(m["id"], True):  # missing state == enabled by default
            out.append(m)
    return out


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", modules=available_modules())
