# DungeonFinder

**DungeonFinder** is a web application for **detecting and identifying code caves**
in executable files (PE, ELF, Mach-O). It is the analysis successor to the
`escavator` CLI, rebuilt as a Flask service with a Shadowrun *Sixth World* visual
identity.

A **code cave** is a contiguous run of padding bytes (e.g. `0x00`, `0xCC`, `0x90`)
inside a compiled binary — alignment slack, zeroed data, section gaps. DungeonFinder
finds them, maps the file's structure around them, and reports everything in a
shareable dossier.

## This tool is read-only

DungeonFinder **only analyzes**. It never modifies, patches, injects into, or emits
any executable. The shellcode-injection, add-section, entry-point-redirection,
certificate-stripping and checksum-patching features of the original `escavator`
CLI were **intentionally removed** — those turn a clean binary into a trojanized
one, which has no place in a public upload service.

## Features

**Analysis (`dungeon_core.py`)**
- PE / ELF / Mach-O parsing via LIEF (format, architecture, bit-width, entry point, section table)
- Multi-pattern padding scan (`\x00`, hex, `0x..`) with per-section, offset-range and alignment filters
- Per-section **Shannon entropy** (flags packed/encrypted regions)
- MD5 / SHA-1 / SHA-256 fingerprints
- Capstone **disassembly classification** that separates padding from stray code
  (single-repeated-byte runs are always treated as padding, so x86 null-runs aren't mislabeled)
- Robust statistics + size histogram (no crash on single-cave files)

**Web app (`app.py`)**
- Drag-and-drop upload for anyone
- **Forced extension matching**: the file's magic bytes must agree with its extension
- **Admin console** (password via env or CLI): max upload size, retention window, difficulty, force-extension toggle, purge
- **Auto-deletion**: uploads and reports are swept after the retention window; the raw upload is deleted immediately after analysis
- **Adaptive hashcash** proof-of-work on every upload, solved in-browser (Web Crypto), difficulty rising with global load and per-IP rate — HMAC-signed, single-use, expiring challenges
- Offset-accurate **cave map**, size distribution, section table, and **JSON/CSV** export

## Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Configure the admin

```bash
python app.py set-password                 # stores a PBKDF2 hash in dungeon/config.json
# or
export DUNGEONFINDER_ADMIN_PASSWORD='...'   # env password overrides the stored hash
```

Set a stable session secret in production:

```bash
export DUNGEONFINDER_SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
```

## Run

```bash
python app.py                 # dev server on :5000  (set PORT to change)
gunicorn -w 4 app:app         # production
```

Then open `http://localhost:5000`. Admin console is at `/admin`.

## Configuration (admin console)

| Setting | Default | Range |
|---|---|---|
| Max upload size (MB) | 32 | 1–1024 |
| Retention (minutes) | 30 | 1–10080 |
| Force extension matching | on | — |
| Hashcash base difficulty (bits) | 18 | 1–30 |
| Hashcash max difficulty (bits) | 26 | 1–30 |
| Adaptive difficulty | on | — |

`DUNGEONFINDER_DATA` overrides the data directory (default `./dungeon`).

## Notes on what changed from `escavator`

- Detection logic ported and hardened (LIEF 1.x API, fixed percentile crash, fixed
  disasm sampling, consistent PE/ELF/Mach-O offsets, section attribution, entropy).
- All injection / binary-modification code removed.
- CLI-only tool turned into a multi-user Flask web app with upload validation,
  retention, an admin console and anti-bot proof-of-work.

Use DungeonFinder only on files you are authorized to analyze.
