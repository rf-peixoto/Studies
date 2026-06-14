"""Bitcoin Explorer & Investigation module.

Two layers on one Blockstream/Esplora-compatible API:

  * Explorer — look up an address or transaction and click through the graph
    (inputs, outputs, spends), the same intuitive navigation as before.
  * Investigation — a persistent, monitored workspace:
      - Watch an address  -> "new activity" tag when coins move in/out.
      - Watch a transaction -> "confirmed" tag when it confirms.
      - Flag a coin (an outpoint txid:vout) -> it is traced backward
        (provenance) and forward (every spend is followed automatically), with
        "new" tags on freshly discovered movement.

Persistence: tunable settings live in the platform JSON config store; the
monitored workspace (addresses, transactions, flagged coins, trace graphs) lives
in a module-private SQLite file (see storage.py) — the core database is never
touched. A background poller refreshes everything on an interval; operators can
also trigger an immediate "Check now".
"""
import os
import threading

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for, current_app)
from flask_login import login_required, current_user

from core.extensions import limiter
from core.security import admin_required, assert_clean
from core.store import get_module_config, save_module_config

from . import explorer, monitor
from .storage import Store

MODULE_ID = "bitcoin"
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

MANIFEST = {
    "id": MODULE_ID,
    "name": "Bitcoin Explorer",
    "description": "Investigate Bitcoin: explore addresses and transactions, "
                   "watch addresses for new activity, track transaction "
                   "confirmations, and flag coins to trace where they came from "
                   "and follow where they go.",
    "version": "2.0.0",
    "author": "OSINT Console",
    "has_config": True,
}

DEFAULT_SETTINGS = {
    "api_base_url": "https://blockstream.info/api",
    "network_label": "mainnet",
    "recent_tx_count": 10,
    "timeout": 10,
    "auto_poll": True,
    "poll_interval": 300,        # seconds between automatic sweeps (min 60)
    "provenance_depth": 3,       # how far back a flagged coin is mapped
    "max_trace_depth": 6,        # how far forward spends are auto-followed
    "max_trace_nodes": 60,       # cap on hops per flagged coin
    "request_delay": 0.4,        # politeness delay between API calls
}


# --------------------------------------------------------------------------- #
# Settings / wiring
# --------------------------------------------------------------------------- #
def _settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(get_module_config(MODULE_ID, {}))
    return merged


def _db_path() -> str:
    return os.environ.get("BITCOIN_DB_PATH", os.path.join(MODULE_DIR, "bitcoin.db"))


def _store() -> Store:
    store = Store(_db_path())
    store.init()
    return store


def _client(settings: dict) -> explorer.ExplorerClient:
    return explorer.ExplorerClient(
        base_url=settings["api_base_url"],
        timeout=float(settings.get("timeout", 10)),
        user_agent=current_app.config["DEFAULT_USER_AGENT"],
    )


def _cfg(settings: dict) -> monitor.MonitorConfig:
    return monitor.MonitorConfig(
        provenance_depth=int(settings["provenance_depth"]),
        max_trace_depth=int(settings["max_trace_depth"]),
        max_trace_nodes=int(settings["max_trace_nodes"]),
        request_delay=float(settings["request_delay"]),
    )


# --------------------------------------------------------------------------- #
# Background execution
# --------------------------------------------------------------------------- #
def _run_bg(app, fn):
    """Run fn(store, client, cfg) in a daemon thread with an app context (needed
    to read settings and the platform User-Agent)."""
    def worker():
        with app.app_context():
            settings = _settings()
            store = _store()
            client = _client(settings)
            cfg = _cfg(settings)
        # network work happens outside the context; only config reads need it
        try:
            fn(store, client, cfg)
        except explorer.ExplorerError:
            pass
    threading.Thread(target=worker, daemon=True).start()


_poller_lock = threading.Lock()
_poller_started = False


def _ensure_poller(app):
    global _poller_started
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True

    def loop():
        import time
        while True:
            try:
                with app.app_context():
                    settings = _settings()
                interval = max(60, int(settings.get("poll_interval", 300)))
                if settings.get("auto_poll", True):
                    store = _store()
                    client = _client_no_ctx(settings, app)
                    monitor.run_once(store, client, _cfg(settings))
            except Exception:  # noqa: BLE001 — a poller must never die
                interval = 300
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()


def _client_no_ctx(settings, app):
    with app.app_context():
        ua = app.config["DEFAULT_USER_AGENT"]
    return explorer.ExplorerClient(settings["api_base_url"],
                                   float(settings.get("timeout", 10)), ua)


# --------------------------------------------------------------------------- #
# User-facing blueprint  ->  /m/bitcoin
# --------------------------------------------------------------------------- #
def create_blueprint() -> Blueprint:
    bp = Blueprint(MODULE_ID, __name__, template_folder="templates")

    @bp.before_request
    def _kick_poller():
        _ensure_poller(current_app._get_current_object())

    # ---- Dashboard + search ------------------------------------------- #
    @bp.route("/", methods=["GET"])
    @login_required
    def index():
        settings = _settings()
        q = (request.args.get("q") or "").strip()
        if q:
            try:
                assert_clean(q)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for(".index"))
            kind = explorer.classify_query(q)
            if kind == "tx":
                return redirect(url_for(".tx", txid=q))
            if kind == "address":
                return redirect(url_for(".address", address=q))
            flash("That doesn't look like a Bitcoin address or transaction ID.", "error")
            return redirect(url_for(".index"))

        store = _store()
        return render_template("bitcoin_index.html", settings=settings,
                               summary=store.summary(),
                               addresses=store.list_addresses(),
                               txs=store.list_txs(),
                               coins=store.list_coins())

    # ---- Explorer: address ------------------------------------------- #
    @bp.route("/address/<address>", methods=["GET"])
    @login_required
    @limiter.limit("120 per hour")
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
        store = _store()
        watched = store.get_address_by_addr(address)
        activity = store.get_activity(watched["id"]) if watched else []
        if watched and watched["has_new"]:
            store.ack_address(watched["id"])
        return render_template("bitcoin_address.html", a=view, settings=settings,
                               watched=watched, activity=activity)

    # ---- Explorer: transaction --------------------------------------- #
    @bp.route("/tx/<txid>", methods=["GET"])
    @login_required
    @limiter.limit("120 per hour")
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
                spends = None
        except explorer.ExplorerError as exc:
            flash(str(exc), "error")
            return redirect(url_for(".index"))
        view = explorer.summarize_tx(data, spends)
        store = _store()
        watched = store.get_tx_by_txid(txid)
        flagged = {(c["txid"], c["vout"]) for c in store.list_coins()}
        if watched and watched["is_newly_confirmed"]:
            store.ack_tx(watched["id"])
        return render_template("bitcoin_tx.html", t=view, settings=settings,
                               watched=watched, flagged=flagged)

    # ---- Flagged coin detail ----------------------------------------- #
    @bp.route("/coin/<int:coin_id>", methods=["GET"])
    @login_required
    def coin(coin_id):
        store = _store()
        c = store.get_coin(coin_id)
        if not c:
            flash("Flagged coin not found.", "error")
            return redirect(url_for(".index"))
        hops = store.get_hops(coin_id)
        ancestors = [h for h in hops if h["kind"] == "ancestor"]
        descendants = [h for h in hops if h["kind"] == "descendant"]
        flagged_hop = next((h for h in hops if h["kind"] == "flagged"), None)
        # Current resting places = unspent frontier outpoints.
        resting = [h for h in hops if h["kind"] in ("flagged", "descendant") and not h["spent"]]
        store.ack_coin(coin_id)
        return render_template("bitcoin_coin.html", c=c, settings=_settings(),
                               ancestors=sorted(ancestors, key=lambda h: -h["depth"]),
                               descendants=sorted(descendants, key=lambda h: h["depth"]),
                               flagged_hop=flagged_hop, resting=resting)

    # ---- Actions: watch / flag / check / remove ---------------------- #
    @bp.route("/watch/address", methods=["POST"])
    @login_required
    def watch_address():
        addr = (request.form.get("address") or "").strip()
        label = (request.form.get("label") or "").strip()[:120]
        if not _valid(addr, explorer.looks_like_address):
            flash("Invalid Bitcoin address.", "error")
            return redirect(request.referrer or url_for(".index"))
        try:
            assert_clean(label)
        except ValueError as exc:
            flash(str(exc), "error"); return redirect(url_for(".index"))
        store = _store()
        try:
            store.add_address(addr, label, current_user.username)
        except Exception:
            flash("That address is already being watched.", "error")
            return redirect(url_for(".address", address=addr))
        _run_bg(current_app._get_current_object(),
                lambda s, cl, cf: [monitor.check_address(s, cl, r, cf)
                                   for r in s.list_addresses() if r["address"] == addr])
        flash("Address added to the watchlist. Baseline scan started.", "success")
        return redirect(url_for(".index"))

    @bp.route("/watch/tx", methods=["POST"])
    @login_required
    def watch_tx():
        txid = (request.form.get("txid") or "").strip()
        label = (request.form.get("label") or "").strip()[:120]
        if not _valid(txid, explorer.is_txid):
            flash("Invalid transaction ID.", "error")
            return redirect(request.referrer or url_for(".index"))
        try:
            assert_clean(label)
        except ValueError as exc:
            flash(str(exc), "error"); return redirect(url_for(".index"))
        store = _store()
        try:
            store.add_tx(txid, label, current_user.username)
        except Exception:
            flash("That transaction is already being watched.", "error")
            return redirect(url_for(".tx", txid=txid))
        app = current_app._get_current_object()
        def chk(s, cl, cf):
            tip = cl.tip_height()
            for r in s.list_txs():
                if r["txid"] == txid:
                    monitor.check_tx(s, cl, r, tip)
        _run_bg(app, chk)
        flash("Transaction added to the watchlist.", "success")
        return redirect(url_for(".index"))

    @bp.route("/flag", methods=["POST"])
    @login_required
    @limiter.limit("60 per hour")
    def flag():
        # Accept either an outpoint string (txid:vout) or separate fields.
        outpoint = (request.form.get("outpoint") or "").strip()
        if outpoint:
            parsed = explorer.parse_outpoint(outpoint)
            if not parsed:
                flash("Enter an outpoint as txid:vout (e.g. abcd…:0).", "error")
                return redirect(request.referrer or url_for(".index"))
            txid, vout = parsed
        else:
            txid = (request.form.get("txid") or "").strip()
            vout_raw = (request.form.get("vout") or "").strip()
            if not _valid(txid, explorer.is_txid) or not vout_raw.isdigit():
                flash("Invalid coin reference.", "error")
                return redirect(request.referrer or url_for(".index"))
            vout = int(vout_raw)
        label = (request.form.get("label") or "").strip()[:120]
        try:
            assert_clean(label)
        except ValueError as exc:
            flash(str(exc), "error"); return redirect(request.referrer or url_for(".index"))

        settings = _settings()
        store = _store()
        existing = store.get_coin_by_outpoint(txid, vout)
        if existing:
            flash("That coin is already flagged.", "error")
            return redirect(url_for(".coin", coin_id=existing["id"]))
        # Do the first trace synchronously enough to create the record, but the
        # heavy walk runs in the background so the request returns promptly.
        client = _client(settings)
        try:
            coin_id, _ = monitor.flag_coin(store, client, txid, vout, label,
                                           current_user.username, _cfg(settings))
        except explorer.ExplorerError as exc:
            flash(str(exc), "error")
            return redirect(request.referrer or url_for(".index"))
        flash("Coin flagged. Provenance mapped and forward tracing started.", "success")
        return redirect(url_for(".coin", coin_id=coin_id))

    @bp.route("/check/all", methods=["POST"])
    @login_required
    @limiter.limit("30 per hour")
    def check_all():
        _run_bg(current_app._get_current_object(), monitor.run_once)
        flash("Checking all watched items in the background…", "success")
        return redirect(url_for(".index"))

    @bp.route("/check/coin/<int:coin_id>", methods=["POST"])
    @login_required
    def check_coin_now(coin_id):
        app = current_app._get_current_object()
        def chk(s, cl, cf):
            c = s.get_coin(coin_id)
            if c:
                monitor.check_coin(s, cl, c, cf)
        _run_bg(app, chk)
        flash("Re-tracing this coin in the background…", "success")
        return redirect(url_for(".coin", coin_id=coin_id))

    @bp.route("/unflag/<int:coin_id>", methods=["POST"])
    @login_required
    def unflag(coin_id):
        _store().delete_coin(coin_id)
        flash("Coin removed from the investigation.", "success")
        return redirect(url_for(".index"))

    @bp.route("/unwatch/address/<int:address_id>", methods=["POST"])
    @login_required
    def unwatch_address(address_id):
        _store().delete_address(address_id)
        flash("Address removed from the watchlist.", "success")
        return redirect(url_for(".index"))

    @bp.route("/unwatch/tx/<int:tx_id>", methods=["POST"])
    @login_required
    def unwatch_tx(tx_id):
        _store().delete_tx(tx_id)
        flash("Transaction removed from the watchlist.", "success")
        return redirect(url_for(".index"))

    return bp


def _valid(value: str, predicate) -> bool:
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
        label = (form.get("network_label") or "").strip()[:32]
        try:
            assert_clean(base); assert_clean(label)
        except ValueError as exc:
            flash(str(exc), "error"); return redirect(url_for(".config"))
        if not (base.startswith("http://") or base.startswith("https://")):
            flash("API base URL must start with http:// or https://.", "error")
            return redirect(url_for(".config"))

        def i(key, lo, hi, fb):
            try: return max(lo, min(hi, int(form.get(key, fb))))
            except (TypeError, ValueError): return fb
        def f(key, lo, hi, fb):
            try: return max(lo, min(hi, float(form.get(key, fb))))
            except (TypeError, ValueError): return fb

        save_module_config(MODULE_ID, {
            "api_base_url": base,
            "network_label": label or "mainnet",
            "recent_tx_count": i("recent_tx_count", 1, 50, current["recent_tx_count"]),
            "timeout": i("timeout", 2, 60, current["timeout"]),
            "auto_poll": form.get("auto_poll", "") == "on",
            "poll_interval": i("poll_interval", 60, 86400, current["poll_interval"]),
            "provenance_depth": i("provenance_depth", 0, 10, current["provenance_depth"]),
            "max_trace_depth": i("max_trace_depth", 1, 20, current["max_trace_depth"]),
            "max_trace_nodes": i("max_trace_nodes", 5, 500, current["max_trace_nodes"]),
            "request_delay": f("request_delay", 0.0, 5.0, current["request_delay"]),
        })
        flash("Settings saved.", "success")
        return redirect(url_for(".config"))

    return bp
