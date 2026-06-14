"""Bitcoin blockchain explorer engine.

A thin client over a Blockstream/Esplora-compatible HTTP API plus the helpers
that shape raw API JSON into template-friendly dicts. Deliberately free of any
Flask import so it can be unit-tested on its own; the Flask layer in
``__init__.py`` passes in the configured base URL, timeout and User-Agent.

The same endpoints are served by blockstream.info (mainnet/testnet) and by any
self-hosted Esplora instance, so pointing this at a private node is just a
settings change.
"""
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests

SATS_PER_BTC = 100_000_000

# txid: 64 hex chars. address: alphanumeric only (a safe superset of base58 and
# bech32 across mainnet/testnet/signet), length-bounded. Both are additionally
# run through the platform character blacklist before use and URL-path-encoded.
TXID_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^[0-9a-zA-Z]{20,90}$")


class ExplorerError(Exception):
    """Raised with a human-readable message when a lookup cannot be completed."""


def parse_outpoint(value: str):
    """Parse a 'txid:vout' string into (txid, vout) or return None.

    An outpoint identifies a single coin (a transaction output)."""
    value = (value or "").strip()
    if ":" not in value:
        return None
    txid, _, vout = value.partition(":")
    if not is_txid(txid) or not vout.isdigit():
        return None
    return txid, int(vout)


# --------------------------------------------------------------------------- #
# Classification / formatting
# --------------------------------------------------------------------------- #
def is_txid(value: str) -> bool:
    return bool(TXID_RE.match(value or ""))


def looks_like_address(value: str) -> bool:
    return bool(ADDRESS_RE.match(value or ""))


def classify_query(value: str) -> str | None:
    """Return 'tx', 'address', or None for an operator's search input."""
    value = (value or "").strip()
    if is_txid(value):
        return "tx"
    if looks_like_address(value):
        return "address"
    return None


def address_delta(tx: dict, address: str) -> dict:
    """How a transaction affects a given address. Returns received/sent/net
    sats and a direction label ('received' | 'sent' | 'self')."""
    received = sum(
        (o.get("value", 0) for o in (tx.get("vout") or [])
         if o.get("scriptpubkey_address") == address)
    )
    sent = sum(
        ((vin.get("prevout") or {}).get("value", 0) for vin in (tx.get("vin") or [])
         if (vin.get("prevout") or {}).get("scriptpubkey_address") == address)
    )
    net = received - sent
    if received and sent:
        direction = "self"
    elif net >= 0:
        direction = "received"
    else:
        direction = "sent"
    return {"received": received, "sent": sent, "net": net, "direction": direction}


def sats_to_btc(sats: int) -> str:
    """Format satoshis as a BTC string with 8 dp (trailing zeros trimmed)."""
    btc = (sats or 0) / SATS_PER_BTC
    return f"{btc:.8f}".rstrip("0").rstrip(".") or "0"


def format_timestamp(ts) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return "—"


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #
class ExplorerClient:
    def __init__(self, base_url: str, timeout: float = 10.0, user_agent: str = "OSINT-Console"):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def _get(self, path: str):
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ExplorerError(f"Could not reach the explorer API: {exc}")
        if resp.status_code == 404:
            raise ExplorerError("Not found on this network.")
        if resp.status_code != 200:
            raise ExplorerError(f"Explorer API returned HTTP {resp.status_code}.")
        return resp

    def _get_json(self, path: str):
        try:
            return self._get(path).json()
        except ValueError:
            raise ExplorerError("Explorer API returned an unexpected (non-JSON) response.")

    def address(self, address: str) -> dict:
        return self._get_json(f"address/{quote(address, safe='')}")

    def address_txs(self, address: str) -> list:
        return self._get_json(f"address/{quote(address, safe='')}/txs")

    def transaction(self, txid: str) -> dict:
        return self._get_json(f"tx/{quote(txid, safe='')}")

    def outspends(self, txid: str) -> list:
        return self._get_json(f"tx/{quote(txid, safe='')}/outspends")

    def tip_height(self) -> int:
        """Current chain tip height (for computing confirmation counts)."""
        try:
            return int(self._get("blocks/tip/height").text.strip())
        except (ValueError, ExplorerError):
            return 0


# --------------------------------------------------------------------------- #
# Shaping raw JSON -> view models
# --------------------------------------------------------------------------- #
def summarize_address(address: str, data: dict, txs: list, recent_limit: int) -> dict:
    chain = data.get("chain_stats", {}) or {}
    mempool = data.get("mempool_stats", {}) or {}
    funded = chain.get("funded_txo_sum", 0)
    spent = chain.get("spent_txo_sum", 0)
    balance = funded - spent

    recent = []
    for tx in (txs or [])[:recent_limit]:
        status = tx.get("status", {}) or {}
        recent.append({
            "txid": tx.get("txid", ""),
            "confirmed": bool(status.get("confirmed")),
            "block_time": status.get("block_time"),
            "date": format_timestamp(status.get("block_time")),
            "fee": tx.get("fee", 0),
        })

    return {
        "address": address,
        "balance_sat": balance,
        "balance_btc": sats_to_btc(balance),
        "received_sat": funded,
        "received_btc": sats_to_btc(funded),
        "sent_sat": spent,
        "sent_btc": sats_to_btc(spent),
        "tx_count": chain.get("tx_count", 0),
        "unconfirmed_count": mempool.get("tx_count", 0),
        "recent": recent,
    }


def summarize_tx(data: dict, outspends: list | None) -> dict:
    status = data.get("status", {}) or {}
    outspends = outspends or []

    inputs = []
    for vin in data.get("vin", []) or []:
        if vin.get("is_coinbase"):
            inputs.append({"coinbase": True})
            continue
        prevout = vin.get("prevout") or {}
        inputs.append({
            "coinbase": False,
            "prev_txid": vin.get("txid"),
            "prev_vout": vin.get("vout"),
            "address": prevout.get("scriptpubkey_address"),
            "value_sat": prevout.get("value", 0),
            "value_btc": sats_to_btc(prevout.get("value", 0)),
        })

    outputs = []
    total_out = 0
    for i, vout in enumerate(data.get("vout", []) or []):
        value = vout.get("value", 0)
        total_out += value
        spend = outspends[i] if i < len(outspends) else None
        outputs.append({
            "index": i,
            "address": vout.get("scriptpubkey_address"),
            "type": vout.get("scriptpubkey_type"),
            "value_sat": value,
            "value_btc": sats_to_btc(value),
            "spent": bool(spend and spend.get("spent")),
            "spent_txid": (spend or {}).get("txid"),
        })

    fee = data.get("fee", 0)
    return {
        "txid": data.get("txid", ""),
        "confirmed": bool(status.get("confirmed")),
        "block_height": status.get("block_height"),
        "block_time": status.get("block_time"),
        "date": format_timestamp(status.get("block_time")),
        "fee_sat": fee,
        "fee_btc": sats_to_btc(fee),
        "size": data.get("size"),
        "weight": data.get("weight"),
        "input_count": len(inputs),
        "output_count": len(outputs),
        "total_out_sat": total_out,
        "total_out_btc": sats_to_btc(total_out),
        "inputs": inputs,
        "outputs": outputs,
    }
