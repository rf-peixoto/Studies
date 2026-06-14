"""Monitoring & tracing engine for the Bitcoin investigation module.

Framework-free (no Flask import) so it can be unit-tested and run from a
background thread without an application context. Callers build a Store, an
ExplorerClient and a MonitorConfig and hand them in.

Three jobs:
  * check_address — detect new send/receive activity on a watched address.
  * check_tx      — detect when a watched transaction confirms.
  * trace_coin / check_coin — the core: follow a flagged outpoint (txid:vout)
    backward (provenance) and forward (every spend), tagging new movement.

A note on forward tracing honesty: Bitcoin transactions merge many inputs and
split into many outputs, so once flagged coins pass through a transaction the
downstream outputs are not provably "the same" coins. This engine follows all
outputs of each spending transaction (the standard taint approach) and annotates
each hop with a proportional ``taint_share`` (our input value / the spending
transaction's total input value) so an investigator can judge dilution. Depth
and node caps keep the trace bounded.
"""
import time
from dataclasses import dataclass

from . import explorer
from .storage import Store, utcnow_iso


@dataclass(frozen=True)
class MonitorConfig:
    provenance_depth: int = 3     # how far back to map a coin's origin
    max_trace_depth: int = 6      # how far forward to auto-follow spends
    max_trace_nodes: int = 60     # cap on hops per flagged coin
    request_delay: float = 0.4    # politeness delay between API calls


# --------------------------------------------------------------------------- #
# Address monitoring
# --------------------------------------------------------------------------- #
def check_address(store: Store, client: explorer.ExplorerClient, row, cfg: MonitorConfig) -> int:
    """Refresh a watched address; record any new transactions as activity.
    Returns the number of newly detected transactions."""
    import json

    data = client.address(row["address"])
    txs = client.address_txs(row["address"])
    chain = data.get("chain_stats", {}) or {}
    balance = chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
    tx_count = chain.get("tx_count", 0)

    known = set(json.loads(row["known_txids"] or "[]"))
    first_observation = not known
    current = [t.get("txid") for t in (txs or []) if t.get("txid")]
    new_txids = [t for t in current if t not in known]

    last_activity = None
    detected = 0
    # Iterate newest-first as returned by the API. For each new tx, fetch the
    # full transaction so input/output detail is always present (address-txs
    # summaries can't be relied on to carry prevouts), and classify direction.
    for txid in new_txids:
        try:
            full = client.transaction(txid)
        except explorer.ExplorerError:
            continue
        delta = explorer.address_delta(full, row["address"])
        status = full.get("status", {}) or {}
        bt = status.get("block_time")
        # On the very first observation we set a baseline silently (no "new"
        # tag); after that, every fresh tx is real new activity.
        added = store.add_activity(
            row["id"], txid, delta["direction"], abs(delta["net"]),
            bt, "confirmed" if status.get("confirmed") else "unconfirmed",
        )
        if added and not first_observation:
            detected += 1
            if bt:
                last_activity = max(last_activity or 0, bt)
        time.sleep(cfg.request_delay)

    known.update(current)
    known_capped = list(known)[-300:]
    store.update_address_state(
        row["id"], balance, tx_count, known_capped,
        has_new=(detected > 0),
        last_activity_at=(explorer.format_timestamp(last_activity) if last_activity else None),
    )
    return detected


# --------------------------------------------------------------------------- #
# Transaction monitoring
# --------------------------------------------------------------------------- #
def check_tx(store: Store, client: explorer.ExplorerClient, row, tip_height: int) -> bool:
    """Refresh a watched transaction. Returns True if it just confirmed."""
    data = client.transaction(row["txid"])
    status = data.get("status", {}) or {}
    confirmed = bool(status.get("confirmed"))
    height = status.get("block_height")
    confirmations = (tip_height - height + 1) if (confirmed and height and tip_height) else 0
    newly_confirmed = confirmed and row["status"] != "confirmed"
    store.update_tx_state(
        row["id"], "confirmed" if confirmed else "unconfirmed",
        height, max(0, confirmations), newly_confirmed,
    )
    return newly_confirmed


# --------------------------------------------------------------------------- #
# Coin flagging & tracing
# --------------------------------------------------------------------------- #
def flag_coin(store: Store, client: explorer.ExplorerClient, txid: str, vout: int,
              label: str, created_by: str, cfg: MonitorConfig):
    """Flag an outpoint, map its provenance, and run the first forward trace.
    Returns (coin_id, created: bool)."""
    existing = store.get_coin_by_outpoint(txid, vout)
    if existing:
        return existing["id"], False

    tx = client.transaction(txid)
    vouts = tx.get("vout") or []
    if vout < 0 or vout >= len(vouts):
        raise explorer.ExplorerError(f"Transaction has no output #{vout}.")
    out = vouts[vout]
    value = out.get("value", 0)
    address = out.get("scriptpubkey_address")
    block_time = (tx.get("status") or {}).get("block_time")

    coin_id = store.add_coin(txid, vout, label, created_by, value, address)
    store.add_hop(coin_id, 0, "flagged", txid, vout, value, address,
                  block_time=block_time, taint_share=1.0)

    _build_provenance(store, client, coin_id, txid, cfg)
    expand_forward(store, client, store.get_coin(coin_id), cfg)
    return coin_id, True


def _build_provenance(store, client, coin_id, origin_txid, cfg: MonitorConfig):
    """Walk the input ancestry of the flagged coin's creating transaction.
    Provenance is immutable history, so it is mapped once at flag time."""
    frontier = [(origin_txid, -1)]
    seen = {origin_txid}
    while frontier:
        cur_txid, depth = frontier.pop(0)
        if depth < -cfg.provenance_depth:
            continue
        try:
            tx = client.transaction(cur_txid)
        except explorer.ExplorerError:
            continue
        for vin in (tx.get("vin") or []):
            if vin.get("is_coinbase"):
                store.add_hop(coin_id, depth, "ancestor", "coinbase", None, 0,
                              "Coinbase (newly mined)", expanded=1)
                continue
            prev_txid = vin.get("txid")
            prev_vout = vin.get("vout")
            prevout = vin.get("prevout") or {}
            store.add_hop(coin_id, depth, "ancestor", prev_txid, prev_vout,
                          prevout.get("value", 0), prevout.get("scriptpubkey_address"),
                          expanded=1)
            if prev_txid and prev_txid not in seen and depth - 1 >= -cfg.provenance_depth:
                seen.add(prev_txid)
                frontier.append((prev_txid, depth - 1))
        time.sleep(cfg.request_delay)


def expand_forward(store: Store, client: explorer.ExplorerClient, coin, cfg: MonitorConfig) -> int:
    """Re-check every unspent outpoint on the forward frontier. When one has
    been spent, follow the spending transaction's outputs as new hops. Returns
    the number of newly discovered movements (spends)."""
    movements = 0
    for hop in store.frontier_hops(coin["id"]):
        try:
            spends = client.outspends(hop["txid"])
        except explorer.ExplorerError:
            continue
        idx = hop["vout"]
        spend = spends[idx] if (idx is not None and idx < len(spends)) else None
        if not (spend and spend.get("spent")):
            continue  # still unspent — a current resting place; recheck later

        spend_txid = spend.get("txid")
        store.mark_hop(hop["id"], spent=1, spent_txid=spend_txid, expanded=1)
        movements += 1

        if store.count_hops(coin["id"]) >= cfg.max_trace_nodes or hop["depth"] + 1 > cfg.max_trace_depth:
            store.update_coin(coin["id"], truncated=1)
            continue
        try:
            stx = client.transaction(spend_txid)
        except explorer.ExplorerError:
            continue
        total_in = sum((vin.get("prevout") or {}).get("value", 0) for vin in (stx.get("vin") or []))
        share = (hop["value_sat"] / total_in) if total_in else None
        bt = (stx.get("status") or {}).get("block_time")
        for i, o in enumerate(stx.get("vout") or []):
            if store.count_hops(coin["id"]) >= cfg.max_trace_nodes:
                store.update_coin(coin["id"], truncated=1)
                break
            store.add_hop(
                coin["id"], hop["depth"] + 1, "descendant", spend_txid, i,
                o.get("value", 0), o.get("scriptpubkey_address"),
                block_time=bt, taint_share=share, parent_hop_id=hop["id"], is_new=1,
            )
        time.sleep(cfg.request_delay)

    # Reflect movement on the coin record (drives the "new spend" tag).
    if movements:
        flagged = store.get_coin(coin["id"])
        store.update_coin(coin["id"], is_new_spend=1, status="traced",
                          spent=1 if flagged else 0)
    store.touch_coin(coin["id"])
    return movements


def check_coin(store, client, coin, cfg: MonitorConfig) -> int:
    # Keep the flagged outpoint's own spent flag in sync for display.
    movements = expand_forward(store, client, coin, cfg)
    flagged_hop = next((h for h in store.get_hops(coin["id"]) if h["kind"] == "flagged"), None)
    if flagged_hop:
        store.update_coin(coin["id"], spent=flagged_hop["spent"],
                          spent_txid=flagged_hop["spent_txid"])
    return movements


# --------------------------------------------------------------------------- #
# Sweep — used by "Check now" and the background poller
# --------------------------------------------------------------------------- #
def run_once(store: Store, client: explorer.ExplorerClient, cfg: MonitorConfig) -> dict:
    counts = {"addresses": 0, "txs": 0, "coins": 0, "errors": 0}
    tip = 0
    try:
        tip = client.tip_height()
    except explorer.ExplorerError:
        pass

    for row in store.list_addresses():
        try:
            counts["addresses"] += check_address(store, client, row, cfg)
        except explorer.ExplorerError:
            counts["errors"] += 1
        time.sleep(cfg.request_delay)

    for row in store.list_txs():
        try:
            if check_tx(store, client, row, tip):
                counts["txs"] += 1
        except explorer.ExplorerError:
            counts["errors"] += 1
        time.sleep(cfg.request_delay)

    for row in store.list_coins():
        try:
            counts["coins"] += check_coin(store, client, row, cfg)
        except explorer.ExplorerError:
            counts["errors"] += 1

    return counts
