"""Persistence for the Bitcoin investigation workspace.

Mirrors the approach taken by the subdomains module: monitoring produces
relational, append-heavy data that a background thread writes while the UI
reads it, so the module keeps its **own** SQLite file (never touching the core
database). Tunable settings live in the platform's JSON config store; the
operational data — watched addresses, watched transactions, flagged coins and
their trace graphs — lives here.

The workspace is shared across authenticated operators (like a shared case
file). Each row records who created it. Override the DB location with the
BITCOIN_DB_PATH environment variable.
"""
import json
import sqlite3
from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def init(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS watched_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL UNIQUE,
                    label TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    balance_sat INTEGER NOT NULL DEFAULT 0,
                    tx_count INTEGER NOT NULL DEFAULT 0,
                    known_txids TEXT NOT NULL DEFAULT '[]',
                    has_new INTEGER NOT NULL DEFAULT 0,
                    last_activity_at TEXT
                );

                CREATE TABLE IF NOT EXISTS address_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address_id INTEGER NOT NULL,
                    txid TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    value_sat INTEGER NOT NULL DEFAULT 0,
                    block_time INTEGER,
                    status TEXT,
                    discovered_at TEXT NOT NULL,
                    is_new INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(address_id, txid),
                    FOREIGN KEY(address_id) REFERENCES watched_addresses(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS watched_txs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txid TEXT NOT NULL UNIQUE,
                    label TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    status TEXT NOT NULL DEFAULT 'unconfirmed',
                    block_height INTEGER,
                    confirmations INTEGER NOT NULL DEFAULT 0,
                    confirmed_at TEXT,
                    is_newly_confirmed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS flagged_coins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txid TEXT NOT NULL,
                    vout INTEGER NOT NULL,
                    label TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    value_sat INTEGER NOT NULL DEFAULT 0,
                    address TEXT,
                    spent INTEGER NOT NULL DEFAULT 0,
                    spent_txid TEXT,
                    spent_at TEXT,
                    is_new_spend INTEGER NOT NULL DEFAULT 0,
                    last_checked_at TEXT,
                    status TEXT NOT NULL DEFAULT 'at_rest',
                    truncated INTEGER NOT NULL DEFAULT 0,
                    note TEXT,
                    UNIQUE(txid, vout)
                );

                CREATE TABLE IF NOT EXISTS trace_hops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin_id INTEGER NOT NULL,
                    depth INTEGER NOT NULL,
                    kind TEXT NOT NULL,            -- 'ancestor' | 'flagged' | 'descendant'
                    txid TEXT NOT NULL,
                    vout INTEGER,
                    value_sat INTEGER NOT NULL DEFAULT 0,
                    address TEXT,
                    block_time INTEGER,
                    spent INTEGER NOT NULL DEFAULT 0,
                    spent_txid TEXT,
                    expanded INTEGER NOT NULL DEFAULT 0,
                    taint_share REAL,
                    parent_hop_id INTEGER,
                    discovered_at TEXT NOT NULL,
                    is_new INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(coin_id, txid, vout, depth),
                    FOREIGN KEY(coin_id) REFERENCES flagged_coins(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_hops_coin ON trace_hops(coin_id, depth);
                CREATE INDEX IF NOT EXISTS idx_hops_frontier ON trace_hops(coin_id, spent, expanded);
                CREATE INDEX IF NOT EXISTS idx_activity_addr ON address_activity(address_id, discovered_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Generic helpers
    # ------------------------------------------------------------------ #
    def _one(self, sql, args=()):
        conn = self._connect()
        try:
            return conn.execute(sql, args).fetchone()
        finally:
            conn.close()

    def _all(self, sql, args=()):
        conn = self._connect()
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def _exec(self, sql, args=()):
        conn = self._connect()
        try:
            cur = conn.execute(sql, args)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Watched addresses
    # ------------------------------------------------------------------ #
    def list_addresses(self):
        return self._all("SELECT * FROM watched_addresses ORDER BY created_at DESC")

    def get_address(self, address_id):
        return self._one("SELECT * FROM watched_addresses WHERE id = ?", (address_id,))

    def get_address_by_addr(self, address):
        return self._one("SELECT * FROM watched_addresses WHERE address = ?", (address,))

    def add_address(self, address, label, created_by):
        return self._exec(
            "INSERT INTO watched_addresses (address, label, created_by, created_at) VALUES (?,?,?,?)",
            (address, label, created_by, utcnow_iso()),
        )

    def delete_address(self, address_id):
        self._exec("DELETE FROM watched_addresses WHERE id = ?", (address_id,))

    def update_address_state(self, address_id, balance_sat, tx_count, known_txids, has_new, last_activity_at):
        self._exec(
            "UPDATE watched_addresses SET balance_sat=?, tx_count=?, known_txids=?, "
            "has_new = CASE WHEN ?=1 THEN 1 ELSE has_new END, last_activity_at=COALESCE(?, last_activity_at), "
            "last_checked_at=? WHERE id=?",
            (balance_sat, tx_count, json.dumps(known_txids), 1 if has_new else 0,
             last_activity_at, utcnow_iso(), address_id),
        )

    def add_activity(self, address_id, txid, direction, value_sat, block_time, status):
        try:
            self._exec(
                "INSERT INTO address_activity (address_id, txid, direction, value_sat, block_time, status, discovered_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (address_id, txid, direction, value_sat, block_time, status, utcnow_iso()),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # already recorded

    def get_activity(self, address_id, limit=50):
        return self._all(
            "SELECT * FROM address_activity WHERE address_id=? ORDER BY discovered_at DESC, id DESC LIMIT ?",
            (address_id, limit),
        )

    def ack_address(self, address_id):
        conn = self._connect()
        try:
            conn.execute("UPDATE watched_addresses SET has_new=0 WHERE id=?", (address_id,))
            conn.execute("UPDATE address_activity SET is_new=0 WHERE address_id=?", (address_id,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Watched transactions
    # ------------------------------------------------------------------ #
    def list_txs(self):
        return self._all("SELECT * FROM watched_txs ORDER BY created_at DESC")

    def get_tx(self, tx_id):
        return self._one("SELECT * FROM watched_txs WHERE id = ?", (tx_id,))

    def get_tx_by_txid(self, txid):
        return self._one("SELECT * FROM watched_txs WHERE txid = ?", (txid,))

    def add_tx(self, txid, label, created_by):
        return self._exec(
            "INSERT INTO watched_txs (txid, label, created_by, created_at) VALUES (?,?,?,?)",
            (txid, label, created_by, utcnow_iso()),
        )

    def delete_tx(self, tx_id):
        self._exec("DELETE FROM watched_txs WHERE id = ?", (tx_id,))

    def update_tx_state(self, tx_id, status, block_height, confirmations, newly_confirmed):
        self._exec(
            "UPDATE watched_txs SET status=?, block_height=?, confirmations=?, "
            "is_newly_confirmed = CASE WHEN ?=1 THEN 1 ELSE is_newly_confirmed END, "
            "confirmed_at = CASE WHEN ?=1 THEN ? ELSE confirmed_at END, last_checked_at=? WHERE id=?",
            (status, block_height, confirmations, 1 if newly_confirmed else 0,
             1 if newly_confirmed else 0, utcnow_iso(), utcnow_iso(), tx_id),
        )

    def ack_tx(self, tx_id):
        self._exec("UPDATE watched_txs SET is_newly_confirmed=0 WHERE id=?", (tx_id,))

    # ------------------------------------------------------------------ #
    # Flagged coins
    # ------------------------------------------------------------------ #
    def list_coins(self):
        return self._all(
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM trace_hops h WHERE h.coin_id=c.id AND h.kind='descendant') AS hop_count, "
            "(SELECT COUNT(*) FROM trace_hops h WHERE h.coin_id=c.id AND h.is_new=1) AS new_hops "
            "FROM flagged_coins c ORDER BY c.created_at DESC"
        )

    def get_coin(self, coin_id):
        return self._one("SELECT * FROM flagged_coins WHERE id = ?", (coin_id,))

    def get_coin_by_outpoint(self, txid, vout):
        return self._one("SELECT * FROM flagged_coins WHERE txid=? AND vout=?", (txid, vout))

    def add_coin(self, txid, vout, label, created_by, value_sat, address):
        return self._exec(
            "INSERT INTO flagged_coins (txid, vout, label, created_by, created_at, value_sat, address) "
            "VALUES (?,?,?,?,?,?,?)",
            (txid, vout, label, created_by, utcnow_iso(), value_sat, address),
        )

    def delete_coin(self, coin_id):
        self._exec("DELETE FROM flagged_coins WHERE id = ?", (coin_id,))

    def update_coin(self, coin_id, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE flagged_coins SET {cols} WHERE id=?", (*fields.values(), coin_id))

    def touch_coin(self, coin_id):
        self._exec("UPDATE flagged_coins SET last_checked_at=? WHERE id=?", (utcnow_iso(), coin_id))

    def ack_coin(self, coin_id):
        conn = self._connect()
        try:
            conn.execute("UPDATE flagged_coins SET is_new_spend=0 WHERE id=?", (coin_id,))
            conn.execute("UPDATE trace_hops SET is_new=0 WHERE coin_id=?", (coin_id,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Trace hops
    # ------------------------------------------------------------------ #
    def add_hop(self, coin_id, depth, kind, txid, vout, value_sat, address,
                block_time=None, spent=0, expanded=0, taint_share=None,
                parent_hop_id=None, is_new=0):
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO trace_hops (coin_id, depth, kind, txid, vout, value_sat, "
                "address, block_time, spent, expanded, taint_share, parent_hop_id, discovered_at, is_new) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (coin_id, depth, kind, txid, vout, value_sat, address, block_time,
                 spent, expanded, taint_share, parent_hop_id, utcnow_iso(), is_new),
            )
            conn.commit()
            return cur.lastrowid if cur.rowcount else None
        finally:
            conn.close()

    def count_hops(self, coin_id):
        row = self._one("SELECT COUNT(*) AS n FROM trace_hops WHERE coin_id=?", (coin_id,))
        return row["n"] if row else 0

    def frontier_hops(self, coin_id):
        """Unspent, not-yet-expanded outpoints — the live edge of the forward trace."""
        return self._all(
            "SELECT * FROM trace_hops WHERE coin_id=? AND kind IN ('flagged','descendant') "
            "AND spent=0 AND vout IS NOT NULL ORDER BY depth ASC",
            (coin_id,),
        )

    def get_hops(self, coin_id):
        return self._all("SELECT * FROM trace_hops WHERE coin_id=? ORDER BY depth ASC, id ASC", (coin_id,))

    def mark_hop(self, hop_id, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE trace_hops SET {cols} WHERE id=?", (*fields.values(), hop_id))

    # ------------------------------------------------------------------ #
    # Dashboard counters
    # ------------------------------------------------------------------ #
    def summary(self):
        return {
            "addresses": self._one("SELECT COUNT(*) n, COALESCE(SUM(has_new),0) new FROM watched_addresses"),
            "txs": self._one("SELECT COUNT(*) n, COALESCE(SUM(is_newly_confirmed),0) new FROM watched_txs"),
            "coins": self._one("SELECT COUNT(*) n, COALESCE(SUM(is_new_spend),0) new FROM flagged_coins"),
        }
