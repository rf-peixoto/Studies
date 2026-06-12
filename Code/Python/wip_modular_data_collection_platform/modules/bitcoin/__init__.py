"""Bitcoin Explorer — a clickable blockchain explorer module.

Refactored from the "bitcrawler" CLI. The command-driven graph walking (iN/oN,
manual chain dump/load) is replaced by ordinary hyperlinks: every txid, address,
input source and spent output is a link, so navigating the chain is just
clicking — and the browser's history is the "chain" you walked.

The explorer is stateless: it queries a Blockstream/Esplora-compatible API and
renders the result. Nothing is stored per user, so the only persistence is a
handful of admin settings kept in the platform's JSON config store.
"""
from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for, current_app)
from flask_login import login_required

from core.extensions import limiter
from core.security import admin_required, assert_clean
from core.store import get_module_config, save_module_config

from . import explorer

MODULE_ID = "bitcoin"

MANIFEST = {
    "id": MODULE_ID,
    "name": "Bitcoin Explorer",
    "description": "Look up Bitcoin addresses and transactions and walk the "
                   "transaction graph by clicking — balances, inputs/outputs, "
                   "and spent/unspent tracing via a Blockstream/Esplora API.",
    "version": "1.0.0",
    "author": "OSINT Console",
    "has_config": True,
}

DEFAULT_SETTINGS = {
    "api_base_url": "https://blockstream.info/api",
    "network_label": "mainnet",
    "recent_tx_count": 10,
    "timeout": 10,
}


# --------------------------------------------------------------------------- #
# Settings helpers
# --------------------------------------------------------------------------- #
def _settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(get_module_config(MODULE_ID, {}))
    return merged


def _client(settings: dict) -> explorer.ExplorerClient:
    return explorer.ExplorerClient(
        base_url=settings["api_base_url"],
        timeout=float(settings.get("timeout", 10)),
        user_agent=current_app.config["DEFAULT_USER_AGENT"],
    )


# --------------------------------------------------------------------------- #
# User-facing blueprint  ->  /m/bitcoin
# --------------------------------------------------------------------------- #
def create_blueprint() -> Blueprint:
    bp = Blueprint(MODULE_ID, __name__, template_folder="templates")

    @bp.route("/", methods=["GET"])
    @login_required
    def index():
        settings = _settings()
        q = (request.args.get("q") or "").strip()
        if not q:
            return render_template("bitcoin_index.html", settings=settings)

        # Validate against the platform blacklist, then classify.
        try:
            assert_clean(q)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("bitcoin_index.html", settings=settings, query=q)

        kind = explorer.classify_query(q)
        if kind == "tx":
            return redirect(url_for(".tx", txid=q))
        if kind == "address":
            return redirect(url_for(".address", address=q))
        flash("That doesn't look like a Bitcoin address or a 64-character transaction ID.", "error")
        return render_template("bitcoin_index.html", settings=settings, query=q)

    @bp.route("/address/<address>", methods=["GET"])
    @login_required
    @limiter.limit("90 per hour")
    def address(address):
        settings = _settings()
        if not _valid(address, explorer.looks_like_address):
            flash("Invalid Bitcoin address.", "error")
            return redirect(url_for(".index"))
        client = _client(settings)
        try:
            data = client.address(address)
            txs = client.address_txs(address)
        except explorer.ExplorerError as exc:
            flash(str(exc), "error")
            return redirect(url_for(".index"))
        view = explorer.summarize_address(address, data, txs, int(settings["recent_tx_count"]))
        return render_template("bitcoin_address.html", a=view, settings=settings)

    @bp.route("/tx/<txid>", methods=["GET"])
    @login_required
    @limiter.limit("90 per hour")
    def tx(txid):
        settings = _settings()
        if not _valid(txid, explorer.is_txid):
            flash("Invalid transaction ID.", "error")
            return redirect(url_for(".index"))
        client = _client(settings)
        try:
            data = client.transaction(txid)
            try:
                spends = client.outspends(txid)
            except explorer.ExplorerError:
                spends = None  # spent-tracing is best-effort; tx still renders
        except explorer.ExplorerError as exc:
            flash(str(exc), "error")
            return redirect(url_for(".index"))
        view = explorer.summarize_tx(data, spends)
        return render_template("bitcoin_tx.html", t=view, settings=settings)

    return bp


def _valid(value: str, predicate) -> bool:
    """Blacklist-clean AND structurally valid."""
    try:
        assert_clean(value)
    except ValueError:
        return False
    return predicate(value)


# --------------------------------------------------------------------------- #
# Admin config blueprint  ->  /admin/modules/bitcoin
# --------------------------------------------------------------------------- #
def create_config_blueprint() -> Blueprint:
    bp = Blueprint(MODULE_ID + "_cfg", __name__, template_folder="templates")

    @bp.route("/", methods=["GET"])
    @admin_required
    def config():
        return render_template("bitcoin_config.html", settings=_settings())

    @bp.route("/settings", methods=["POST"])
    @admin_required
    def save_settings():
        current = _settings()
        form = request.form

        base = (form.get("api_base_url") or "").strip().rstrip("/")
        try:
            assert_clean(base)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for(".config"))
        if not (base.startswith("http://") or base.startswith("https://")):
            flash("API base URL must start with http:// or https://.", "error")
            return redirect(url_for(".config"))

        label = (form.get("network_label") or "").strip()[:32]
        try:
            assert_clean(label)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for(".config"))

        def _as_int(key, lo, hi, fallback):
            try:
                return max(lo, min(hi, int(form.get(key, fallback))))
            except (TypeError, ValueError):
                return fallback

        save_module_config(MODULE_ID, {
            "api_base_url": base,
            "network_label": label or "mainnet",
            "recent_tx_count": _as_int("recent_tx_count", 1, 50, current["recent_tx_count"]),
            "timeout": _as_int("timeout", 2, 60, current["timeout"]),
        })
        flash("Settings saved.", "success")
        return redirect(url_for(".config"))

    return bp
