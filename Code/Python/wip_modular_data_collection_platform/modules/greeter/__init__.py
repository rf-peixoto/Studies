import re
from flask import Blueprint, render_template, request
from flask_login import login_required
from core.security import contains_blacklisted

MANIFEST = {
    "id": "greeter",
    "name": "Greeter",
    "description": "Minimal example module — echoes a safe greeting.",
    "version": "1.0.0",
    "author": "you",
    "has_config": False,
}

SAFE = re.compile(r"^[A-Za-z0-9_.\- ]{1,40}$")

def create_blueprint():
    bp = Blueprint("greeter", __name__, template_folder="templates")

    @bp.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        greeting = None
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            if name and not contains_blacklisted(name) and SAFE.match(name):
                greeting = f"Hello, {name}."
        return render_template("greeter_index.html", greeting=greeting)

    return bp
