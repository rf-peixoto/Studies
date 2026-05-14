# Internet Metrics — Domain Feed

Personal internet usage tracker. Collects domains from all pages you visit in Firefox
and exposes them as a local JSON feed for processing scripts.

## Architecture

```
Firefox page → content.js → background.js → POST /ingest → server.py → GET /feed → collector.py
```

---

## 1. Feed Server

```bash
pip install flask
python server.py
```

Runs on `http://localhost:5555`. Keep this running whenever you want to collect data.

---

## 2. Firefox Extension

1. Open Firefox and go to `about:debugging`
2. Click **This Firefox** → **Load Temporary Add-on**
3. Select `extension/manifest.json`

To install permanently (without re-loading after every restart):
- Sign it via [Firefox Add-on Hub](https://addons.mozilla.org/developers/) or
- Set `xpinstall.signatures.required = false` in `about:config` (dev only)

**Usage:** Click the extension icon in the toolbar to toggle tracking on/off.

---

## 3. Collector Script

```bash
pip install requests
python collector.py
```

Polls `/feed` every 5 minutes and prints domain stats. Extend `process()` to write to
a file, database, or anything else you need.

---

## Feed API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest` | Extension sends `{ "domains": ["example.com", ...] }` |
| `GET`  | `/feed` | Returns all buffered entries |
| `GET`  | `/feed?since=<ISO timestamp>` | Returns only entries newer than the given time |

### Entry format

```json
{ "domain": "example.com", "ts": "2026-05-14T21:00:00.000000+00:00" }
```

---

## Customisation ideas

- **Blacklist** — filter out noise like `localhost`, `cdn.jsdelivr.net`, etc.
- **Categories** — map domains to categories (social, news, work…)
- **Dashboard** — pipe collector output into a simple HTML chart
- **Alerts** — notify when you spend too much time on a specific domain
