# OSINT Console

A modular, self-hosted OSINT platform built with Python + Flask. Users register
and sign in to run **modules**; an admin controls which modules exist, who may
use the platform, and global settings. Each module is a self-contained Flask
sub-app (a Blueprint package) that you drop into `modules/` — no changes to the
core are needed to add or remove one.

The bundled reference module, **Usernames**, checks whether a handle exists
across a configurable list of sites (Sherlock-style) and links straight to any
hit.

---

## Table of contents

1. [Features](#features)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [Security model](#security-model)
5. [Project layout](#project-layout)
6. [Admin guide](#admin-guide)
7. [Writing a module](#writing-a-module) ← the main developer guide
8. [The Usernames module, explained](#the-usernames-module-explained)
9. [Deployment](#deployment)
10. [Responsible use](#responsible-use)

---

## Features

- **Auth** — username/password registration and login with a strong-password
  policy, Argon2 hashing, CSRF on every form, and secure session cookies.
- **Brute-force protection** — 3 failed logins from an IP locks that IP out for
  one hour. General per-route rate limiting on top (Flask-Limiter).
- **Dashboard** — lists the modules currently available to the signed-in user.
- **Per-module pages** — each module gets its own URL space under `/m/<id>`.
- **Admin panel** — manage users (ban permanently or for a timespan, unban),
  open/close registration, toggle maintenance mode, and enable / disable /
  configure / delete modules.
- **Drop-in modules** — a module is a package in `modules/`. Discovered
  automatically on startup.
- **Global input hardening** — the characters `" ' \ %` are rejected across the
  platform and before any outbound request, on top of parameterised queries and
  URL-encoding.

---

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set a real secret and a strong bootstrap admin password (recommended):
export OSINT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export OSINT_ADMIN_USER="admin"
export OSINT_ADMIN_PASSWORD="Replace-This!2025xyz"

python app.py        # http://127.0.0.1:5000
```

On first run the database is created and a **bootstrap admin** is made from
`OSINT_ADMIN_USER` / `OSINT_ADMIN_PASSWORD`. Sign in and change the password
(or create your own admin) immediately.

For production, run behind an HTTPS reverse proxy with a WSGI server:

```bash
OSINT_HTTPS=1 gunicorn 'app:app' --workers 4 --bind 127.0.0.1:8000
```

---

## Configuration

All settings live in `config.py` and read from environment variables where it
matters. The defaults are safe for local self-hosting; override the starred
ones before exposing the app.

| Variable | Default | Purpose |
|---|---|---|
| `OSINT_SECRET_KEY` ★ | `dev-only-change-me` | Flask session signing key. **Set this.** |
| `OSINT_DATABASE_URI` | SQLite in `instance/` | Swap for Postgres/MySQL with no code change. |
| `OSINT_HTTPS` | `0` | Set `1` to mark session cookies `Secure` (behind HTTPS). |
| `OSINT_ADMIN_USER` | `admin` | Bootstrap admin username (first run only). |
| `OSINT_ADMIN_PASSWORD` ★ | a placeholder | Bootstrap admin password (first run only). |
| `OSINT_RATELIMIT_URI` | `memory://` | Use `redis://…` for multi-worker rate limiting. |

Policy knobs (edit in `config.py`): password length/symbols, the character
blacklist, login-lockout thresholds, outbound user-agent, request timeout and
the concurrency worker count.

---

## Security model

- **Passwords** are hashed with Argon2 (`argon2-cffi`). Policy: ≥12 chars with
  upper, lower, digit and symbol; the blacklisted characters are disallowed.
- **CSRF** protection is global (Flask-WTF). Every form includes `csrf_token()`.
- **Login lockout** is per-IP: `LOGIN_MAX_FAILURES` failures within the window
  trigger a `LOGIN_LOCKOUT` block. Successful login clears the counter.
- **Character blacklist** — `assert_clean()` / `contains_blacklisted()` reject
  `" ' \ %` in usernames, module inputs, and any string used to build an
  outbound request. This is defence-in-depth; the real protections are the
  SQLAlchemy ORM (parameterised queries) and URL-encoding of user input.
- **Outbound requests** made by modules use a real browser User-Agent, a hard
  timeout, and a bounded thread pool.
- **Authorization** — `@login_required` gates user pages; `@admin_required`
  gates admin pages; disabled or deleted modules return `404`.

> The blacklist intentionally trades a little input flexibility for safety. If a
> module needs richer input, validate it explicitly rather than removing the
> global check.

---

## Project layout

```
osint_platform/
├── app.py                  # entry point (creates the app)
├── config.py               # all configuration
├── requirements.txt
├── README.md
├── instance/               # SQLite db lives here (created at runtime)
├── core/                   # the platform itself
│   ├── __init__.py         # app factory, request gates, error handlers
│   ├── models.py           # User, LoginAttempt, Setting, ModuleState, ModuleConfig
│   ├── extensions.py       # login_manager, limiter singletons
│   ├── security.py         # password policy, blacklist, settings, decorators
│   ├── store.py            # module config storage API  ← modules use this
│   ├── module_loader.py    # discovers + registers module blueprints
│   ├── auth.py             # register / login / logout
│   ├── dashboard.py        # module listing
│   ├── admin.py            # users / modules / settings
│   ├── static/css/app.css  # design system (modules inherit it)
│   └── templates/          # base.html + core pages
└── modules/
    ├── __init__.py         # marks modules/ as a package (leave empty)
    └── usernames/          # the reference module
        ├── __init__.py     # MANIFEST + blueprint factories
        ├── checker.py      # framework-free checking engine
        └── templates/      # usernames_index.html, usernames_config.html
```

---

## Admin guide

Sign in as an admin and open **Admin** in the top bar.

- **Users** — ban a user permanently or for a number of hours, or unban them.
  Banned users are signed out on their next request and cannot log in. Admins
  cannot be banned, and you cannot ban yourself.
- **Modules** — every folder discovered in `modules/` is listed with its
  enabled state. **Disable** hides a module from users immediately. **Configure**
  opens the module's own admin screen (if it has one). **Delete** removes the
  module's folder from disk and its stored config; its routes fully unload on
  the next restart.
- **Settings** — *Allow new registrations* opens/closes signup; *Maintenance
  mode* makes the whole platform return a maintenance page to everyone except
  admins.

**Adding a module:** drop its folder into `modules/`, restart the app, then
enable it under Admin → Modules.

---

## Writing a module

A module is a normal Python package placed in `modules/`. The core discovers it
on startup, reads its `MANIFEST`, and registers its Blueprint(s). You never edit
the core to add one.

### The contract

Your package's `__init__.py` must expose:

```python
MANIFEST = {
    "id": "mymodule",          # required, [a-z0-9_], MUST equal the folder name
    "name": "My Module",       # shown in the UI
    "description": "What it does.",
    "version": "1.0.0",
    "author": "you",
    "has_config": False,       # True if you provide an admin config screen
}

def create_blueprint():                 # REQUIRED — the user-facing sub-app
    ...
    return blueprint

def create_config_blueprint():          # REQUIRED only if has_config is True
    ...
    return blueprint
```

Routing is handled for you:

| Blueprint | Mounted at | Endpoint name |
|---|---|---|
| `create_blueprint()` | `/m/<id>/…` | `mod_<id>.<view>` |
| `create_config_blueprint()` | `/admin/modules/<id>/…` | `modcfg_<id>.<view>` |

The core renames your blueprints to `mod_<id>` / `modcfg_<id>`, so **inside your
module always use relative `url_for(".view")`** — it resolves correctly no matter
what the final name is. The dashboard links to your module via `mod_<id>.index`,
so your user blueprint must define a view named **`index`**.

### Helpers the core gives you

Import these — they are the entire surface your module depends on:

```python
from flask_login import login_required, current_user        # auth
from core.security import admin_required                     # admin-only views
from core.security import assert_clean, contains_blacklisted # input hardening
from core.store import get_module_config, save_module_config # persistence
```

- `get_module_config(module_id, default)` / `save_module_config(module_id, data)`
  store an arbitrary JSON-serialisable dict for your module. The core never
  inspects it, which is what keeps modules portable. Don't create your own
  tables unless you truly need to.
- `assert_clean(value)` raises `ValueError` if `value` contains a blacklisted
  character. Call it on any free text **before** you put it in an outbound URL,
  a shell command, a filename, etc. `contains_blacklisted(value)` is the boolean
  form.
- `@login_required` on user views; `@admin_required` on config views.

### Templates

Create a `templates/` folder in your module and pass `template_folder="templates"`
to the Blueprint. Because all modules share one Jinja namespace, **prefix your
template filenames with your module id** (e.g. `mymodule_index.html`) to avoid
collisions.

Extend the platform shell to inherit the nav, flash messages and styling:

```jinja
{% extends "base.html" %}
{% block title %}My Module{% endblock %}
{% block content %} … {% endblock %}
```

Available to your templates: `current_user`, `csrf_token()` (put it in every
form), and the design-system CSS classes — `card`, `grid`, `btn`,
`btn-primary`, `btn-danger`, `eyebrow`, `pill` (`found`/`absent`/`error`),
`readout` / `readout-row`, `muted`, `mono`. Reusing these keeps every module
visually consistent.

### Security requirements (modules must follow these)

1. Decorate every user view with `@login_required` and every config view with
   `@admin_required`.
2. Validate user input with an allow-list regex where possible, and call
   `assert_clean()` / `contains_blacklisted()` on anything used to build an
   outbound request.
3. URL-encode user input before inserting it into a URL (`urllib.parse.quote`).
4. For outbound HTTP: set the configured User-Agent, always pass a `timeout`,
   and cap concurrency. Catch exceptions — never let a target failure crash the
   request.
5. Be mindful of SSRF: prefer admin-defined destinations (as Usernames does)
   over letting users supply arbitrary URLs.
6. Include `csrf_token()` in every form.

### A minimal, complete module

Create `modules/greeter/` with these two files, restart, and enable it under
Admin → Modules. It has no config screen (`has_config` is `False`).

`modules/greeter/__init__.py`:

```python
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
```

`modules/greeter/templates/greeter_index.html`:

```jinja
{% extends "base.html" %}
{% block title %}Greeter{% endblock %}
{% block content %}
<div class="eyebrow">Module</div>
<h1>Greeter</h1>
<div class="card">
  <form method="post" class="row" style="align-items:flex-end">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div style="flex:1"><label style="margin-top:0">Name</label>
      <input type="text" name="name"></div>
    <button class="btn btn-primary" type="submit">Greet</button>
  </form>
  {% if greeting %}<p class="pill found" style="margin-top:1rem">{{ greeting }}</p>{% endif %}
</div>
{% endblock %}
```

That is the whole contract. Add `has_config = True` plus a
`create_config_blueprint()` to get an admin screen, and use
`get_module_config` / `save_module_config` to persist whatever the admin sets —
exactly what Usernames does next.

---

## The Usernames module, explained

`modules/usernames/` is the worked example for a module with admin
configuration, persisted state, concurrency, and outbound requests.

- **`MANIFEST`** sets `has_config = True`, so the core also mounts the config
  blueprint at `/admin/modules/usernames/`.
- **User flow** (`create_blueprint`): the operator submits a username. It is
  validated against an allow-list regex and the blacklist, then passed to the
  checker. Results render as a scan readout; hits get an "Open ↗" button that
  opens the profile in a new tab (`rel="noopener"`).
- **Admin flow** (`create_config_blueprint`, `@admin_required`): add / edit /
  remove **targets**. A target is a site to check:
  - **URL template** — use `{}` where the username goes
    (`https://example.com/u/{}`), or omit it to append at the end
    (`https://example.com/u/`).
  - **Detection method** — how a "hit" is decided:
    - `status` — exists if the HTTP status is one of *Expected status*.
    - `body_contains` — exists if the *Match string* appears in the page.
    - `body_absent` — exists if the *Match string* (a "not found" marker) is
      **absent** and the page loaded.
  - **Enabled** — skip a target without deleting it.
  Targets are stored as JSON via `save_module_config("usernames", …)`.
- **`checker.py`** is deliberately framework-free (easy to test):
  - `build_url(template, username)` — substitutes the URL-encoded username.
  - `check_one(target, username, …)` — one request; never raises (failures come
    back as `status="error"`).
  - `run_checks(targets, username, …)` — runs enabled targets concurrently with
    a bounded `ThreadPoolExecutor`, preserving input order.

To extend it, add a new detection method to `checker.METHODS` and handle it in
`_decide()`, then surface it in the config template's method dropdown.

---

## Deployment

- Put the app behind an HTTPS-terminating reverse proxy (nginx/Caddy) and set
  `OSINT_HTTPS=1` so session cookies are marked `Secure`.
- Set a strong `OSINT_SECRET_KEY` and rotate the bootstrap admin password.
- Run with a WSGI server (`gunicorn 'app:app' --workers 4`).
- For more than one worker, point `OSINT_RATELIMIT_URI` at Redis so rate limits
  and lockouts are shared across workers.
- Back up `instance/osint.sqlite3` (or your external database).
- The SQLite default suits a single host; switch `OSINT_DATABASE_URI` to
  Postgres for heavier use.

---

## Responsible use

The Usernames module (and any module you write that fires automated requests at
third-party sites) should be used responsibly:

- Respect each target site's Terms of Service and `robots`/rate expectations.
  Aggressive scanning can get your IP blocked or violate a site's terms.
- Keep the target list and concurrency reasonable; the timeout and worker count
  in `config.py` exist so a scan can't hammer endpoints unbounded.
- Only investigate accounts/handles you have a lawful basis to investigate, and
  comply with the privacy laws that apply to you.

This software is provided for legitimate research, security, and investigative
work. You are responsible for how you use it.
