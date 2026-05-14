"""
Domain Feed Server
==================
Receives domain batches from the browser extension and exposes them
as a simple JSON feed for local scripts to consume.

Endpoints:
  POST /ingest          — Extension posts { "domains": [...] }
  GET  /feed            — Returns all buffered entries as JSON
  GET  /feed?since=ISO  — Returns only entries newer than the given timestamp

Run:
  pip install flask
  python server.py
"""

from flask import Flask, jsonify, request
from collections import deque
from datetime import datetime, timezone

app = Flask(__name__)

# In-memory rolling buffer. Holds up to 100k entries (no persistence).
BUFFER: deque = deque(maxlen=100_000)


@app.post("/ingest")
def ingest():
    data = request.get_json(silent=True) or {}
    domains = data.get("domains", [])
    if not isinstance(domains, list):
        return jsonify({"error": "domains must be a list"}), 400

    ts = datetime.now(timezone.utc).isoformat()
    for domain in domains:
        if isinstance(domain, str) and domain:
            BUFFER.append({"domain": domain, "ts": ts})

    return jsonify({"ok": True, "ingested": len(domains), "buffer_size": len(BUFFER)})


@app.get("/feed")
def feed():
    since = request.args.get("since")

    if since:
        try:
            entries = [e for e in BUFFER if e["ts"] > since]
        except Exception:
            return jsonify({"error": "invalid 'since' value"}), 400
    else:
        entries = list(BUFFER)

    return jsonify(entries)


if __name__ == "__main__":
    print("Domain Feed Server running on http://localhost:5555")
    print("  POST /ingest  — receives domains from extension")
    print("  GET  /feed    — returns buffered domains")
    app.run(host="127.0.0.1", port=5555, debug=False)
