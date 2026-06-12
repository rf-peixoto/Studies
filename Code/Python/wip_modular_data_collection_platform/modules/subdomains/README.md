# InventoryKeeper v1

A minimal Flask application to track domains and subdomains discovered via `subfinder`.

## Features

- Add a root domain and automatically start an initial scan.
- Re-scan previously added domains.
- Store subdomains in SQLite.
- Mark newly discovered subdomains with `[new]` until the first time the domain detail page is viewed.
- Flag hostnames outside the monitored root domain as `[suspicious]`.
- Resolve IPv4/IPv6 addresses for each discovered hostname.
- Keep scan history and basic active/stale state.

## Important behavior

- A hostname is considered valid for `example.com` only if it is exactly `example.com` or ends with `.example.com`.
- Everything else is flagged as suspicious instead of being discarded.
- A subdomain becomes `[stale]` when it was seen in older scans but not in the current one.
- Timeouts are configurable through environment variables.

## Requirements

- Python 3.11+
- `subfinder` installed and available in your `$PATH`

## Configuration

Environment variables:

- `FLASK_SECRET_KEY` — Flask session secret.
- `INVENTORY_DB_PATH` — optional SQLite path. Default: `./inventory.db`
- `SUBFINDER_BIN` — path to the subfinder binary. Default: `subfinder`
- `SUBFINDER_TIMEOUT` — timeout in seconds for each subfinder execution. Default: `300`
- `DNS_TIMEOUT` — timeout in seconds for each DNS resolution. Default: `3.0`

Example:

```bash
export FLASK_SECRET_KEY='change-me'
export SUBFINDER_TIMEOUT=600
export DNS_TIMEOUT=5
python3 app.py
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Project structure

```text
inventorykeeper/
├── app.py
├── inventory.db        # created on first run
├── requirements.txt
├── README.md
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── domain_detail.html
    └── index.html
```

## Limitations of this v1

- Background work uses local Python threads, not a job queue.
- DNS resolution uses the system resolver through Python sockets.
- There is no authentication.
- There are no exports, notifications, or scheduled scans yet.
