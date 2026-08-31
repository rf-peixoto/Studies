#!/usr/bin/env python3
"""
http_methods_scan.py
--------------------
Probe IPs / domains / URLs for insecure HTTP methods and PROVE the ones that
are actually exploitable, instead of trusting the OPTIONS `Allow` header.

Layers:
  1. OPTIONS -> record advertised methods.
  2. Reachability probe -> send each method; a 405/501/400 means blocked,
     anything else means the verb reached a handler. State-changing verbs are
     sent to a random dead sub-path so nothing real is touched.
  3. Proof-of-concept (default in --probe-all, disable with --no-poc) -> for the
     critical methods, run a real validation that yields evidence. Every PoC only
     ever touches a resource the scanner itself just created — never real data:
        PUT      upload inert marker files (extensions via --poc-ext), read them
                 back, and flag ones served as html/svg (stored-XSS) or accepted
                 script uploads (.php/.jsp -> code-exec if executed).
        DELETE   stage a temp file, delete it, confirm it is gone (404).
        MOVE     stage a temp file, move it, confirm src gone & dest present.
        COPY     stage a temp file, copy it, confirm the copy holds the marker.
        MKCOL    create a new random-named collection, confirm, then remove it.
        PATCH    stage a temp file, modify it, confirm the change round-trips.
        TRACE /  send a unique marker header and confirm the server echoes it
        TRACK    back in the body (Cross-Site Tracing / XST).
        PROPFIND send a WebDAV allprop request and confirm a 207 Multi-Status.
     Methods needing a staged file (DELETE/MOVE/COPY/PATCH) fall back to a plain
     reachability result when PUT is unavailable, rather than touching real data.
     Other destructive verbs (PURGE, ACL, DeltaV, ...) are never actively
     exercised — they appear as REACHABLE for manual review.

Output is finding-first: confirmed issues are loud, reachable-but-unvalidated
issues are amber, and expected/blocked results are hidden unless -v.

Only scan hosts you own or are explicitly authorized to test.

Examples:
    python3 http_methods_scan.py example.com --probe-all
    python3 http_methods_scan.py -f targets.txt --probe-all -o report.json
    python3 http_methods_scan.py https://x.tld --probe-all --no-poc   # reachability only

Requires: requests  (pip install requests)
"""

import argparse
import concurrent.futures
import json
import os
import random
import secrets
import string
import sys

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    sys.exit("This script needs the 'requests' library. Install it with:  pip install requests")


# --------------------------------------------------------------------------- #
# Method catalog  ->  method: (is_risky, is_destructive, note)
# destructive = never actively exercised (only a dead-path reachability probe)
# --------------------------------------------------------------------------- #
METHOD_CATALOG = {
    "GET":              (False, False, "Standard read."),
    "HEAD":             (False, False, "Standard read (headers only)."),
    "POST":             (False, True,  "Standard submit (may change state)."),
    "OPTIONS":          (False, False, "Capability discovery."),
    "PUT":              (True,  False, "Upload/overwrite files (RCE if writable)."),
    "DELETE":           (True,  True,  "Remove resources."),
    "PATCH":            (True,  True,  "Partially modify resources."),
    "TRACE":            (True,  False, "Cross-Site Tracing (XST); echoes request."),
    "CONNECT":          (True,  True,  "Can turn the server into a proxy/tunnel."),
    "TRACK":            (True,  False, "Microsoft TRACE equivalent; XST."),
    "DEBUG":            (True,  True,  "ASP.NET debug verb; state/info disclosure."),
    "LINK":             (True,  True,  "Legacy: associate resources."),
    "UNLINK":           (True,  True,  "Legacy: remove associations."),
    "PROPFIND":         (True,  False, "WebDAV: enumerate properties/resources."),
    "PROPPATCH":        (True,  True,  "WebDAV: modify properties."),
    "MKCOL":            (True,  True,  "WebDAV: create collections."),
    "COPY":             (True,  True,  "WebDAV: copy resources."),
    "MOVE":             (True,  True,  "WebDAV: move/rename resources."),
    "LOCK":             (True,  True,  "WebDAV: lock resources."),
    "UNLOCK":           (True,  True,  "WebDAV: unlock resources."),
    "SEARCH":           (True,  False, "WebDAV: server-side search/enumeration."),
    "ORDERPATCH":       (True,  True,  "WebDAV: reorder collection members."),
    "ACL":              (True,  True,  "WebDAV: modify access-control lists."),
    "BIND":             (True,  True,  "WebDAV: create bindings/aliases."),
    "UNBIND":           (True,  True,  "WebDAV: remove bindings."),
    "REBIND":           (True,  True,  "WebDAV: move bindings."),
    "VERSION-CONTROL":  (True,  True,  "DeltaV: put under version control."),
    "REPORT":           (True,  False, "DeltaV: run reports (info disclosure)."),
    "CHECKOUT":         (True,  True,  "DeltaV: check out a version."),
    "CHECKIN":          (True,  True,  "DeltaV: check in a version."),
    "UNCHECKOUT":       (True,  True,  "DeltaV: cancel a checkout."),
    "MKWORKSPACE":      (True,  True,  "DeltaV: create a workspace."),
    "UPDATE":           (True,  True,  "DeltaV: update a working resource."),
    "LABEL":            (True,  True,  "DeltaV: add/modify labels."),
    "MERGE":            (True,  True,  "DeltaV: merge resources."),
    "BASELINE-CONTROL": (True,  True,  "DeltaV: baseline a collection."),
    "MKACTIVITY":       (True,  True,  "DeltaV: create an activity."),
    "PURGE":            (True,  True,  "Cache purge (Varnish/Squid); poisoning/DoS."),
    "BAN":              (True,  True,  "Varnish cache ban."),
    "REFRESH":          (True,  True,  "Squid cache refresh."),
}
ALL_METHODS = list(METHOD_CATALOG.keys())

def is_risky(m):        return METHOD_CATALOG.get(m, (True, True, ""))[0]
def is_destructive(m):  return METHOD_CATALOG.get(m, (True, True, ""))[1]
def note_for(m):        return METHOD_CATALOG.get(m, (True, True, ""))[2]


# --------------------------------------------------------------------------- #
# Colors  (severity-driven: findings are loud, expected results recede)
# --------------------------------------------------------------------------- #
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"; GREY = "\033[90m"

    @classmethod
    def disable(cls):
        for n in dir(cls):
            if n.isupper():
                setattr(cls, n, "")


def maybe_disable_color(force):
    if not force and (os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()):
        C.disable()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def build_urls(target, scheme_mode):
    target = target.strip()
    if not target or target.startswith("#"):
        return []
    if "://" in target:
        return [target]
    if scheme_mode in ("http", "https"):
        return [f"{scheme_mode}://{target}"]
    return [f"https://{target}", f"http://{target}"]


def parse_allow(headers):
    out = set()
    for h in ("Allow", "Public"):
        raw = headers.get(h) or headers.get(h.lower()) or ""
        out |= {m.strip().upper() for m in raw.split(",") if m.strip()}
    return out


def rand_token(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def safe_request(session, method, url, timeout, verify, **kw):
    try:
        r = session.request(method, url, timeout=timeout, verify=verify,
                            allow_redirects=False, **kw)
        return r, None
    except requests.RequestException as e:
        return None, e


# --------------------------------------------------------------------------- #
# Proof-of-concept validators  ->  (verdict, status, evidence, leftover)
#   verdict in: confirmed | reachable | gated | blocked | error
# --------------------------------------------------------------------------- #
def _link(url):
    # Make the artifact URL stand out even inside dim evidence text.
    return f"{C.CYAN}{url}{C.RESET}{C.DIM}"

# Extension risk classes. Uploaded PoC content is ALWAYS inert (comments/plain
# text, never live script) — the finding is that the server accepts and serves
# attacker-controlled content of a dangerous type, not that we planted a payload.
_MARKUP_EXTS = {".html", ".htm", ".xhtml", ".shtml", ".svg", ".xml"}
_SCRIPT_EXTS = {".php", ".php3", ".php4", ".php5", ".phtml", ".asp", ".aspx",
                ".jsp", ".jspx", ".cgi", ".pl", ".py", ".sh", ".rb"}


def _content_for_ext(ext, token):
    """Return (bytes, content_type) with an inert but detectable marker."""
    e = ext.lower()
    marker = f"methodscan-poc {token}"
    if e in (".html", ".htm", ".xhtml", ".shtml"):
        return f"<!-- {marker} -->\n".encode(), "text/html"
    if e == ".svg":
        return (f'<svg xmlns="http://www.w3.org/2000/svg"><!-- {marker} --></svg>'
                ).encode(), "image/svg+xml"
    if e == ".xml":
        return f"<!-- {marker} -->\n".encode(), "application/xml"
    return f"{marker}\n".encode(), "text/plain"      # scripts too: inert text only


def _ext_risk(ext, served_ct):
    e = ext.lower()
    ct = (served_ct or "").lower().split(";")[0].strip()
    if e in _MARKUP_EXTS and any(d in ct for d in ("text/html", "xhtml", "svg", "xml")):
        return f"STORED-XSS: served as {ct or 'dangerous type'}"
    if e in _SCRIPT_EXTS:
        return f"CODE-EXEC risk if the server executes {e}"
    return ""


def _delete(session, url, timeout, verify):
    r, _ = safe_request(session, "DELETE", url, timeout, verify)
    return bool(r is not None and r.status_code in (200, 202, 204, 404))


def _put_temp(session, base, timeout, verify, ext=".txt"):
    """Stage a scanner-owned temp file. Returns (path, token, status, ok)."""
    token = secrets.token_urlsafe(24)
    path = base.rstrip("/") + f"/.methodscan-poc-{rand_token()}{ext}"
    content, ct = _content_for_ext(ext, token)
    r, err = safe_request(session, "PUT", path, timeout, verify,
                          data=content, headers={"Content-Type": ct})
    ok = bool(err is None and r is not None and r.status_code in (200, 201, 204))
    return path, token, (r.status_code if r is not None else None), ok


# --- PUT: write, read back, and probe dangerous extensions ------------------ #
def validate_put(session, base, timeout, verify, keep, exts):
    exts = exts or [".txt"]
    written, confirmed, danger, leftovers, statuses = [], [], [], [], []
    link_url, cstatus, gated = None, None, False

    for ext in exts:
        token = secrets.token_urlsafe(24)
        path = base.rstrip("/") + f"/.methodscan-poc-{rand_token()}{ext}"
        content, ct = _content_for_ext(ext, token)
        r, err = safe_request(session, "PUT", path, timeout, verify,
                              data=content, headers={"Content-Type": ct})
        if err:
            statuses.append(None); continue
        statuses.append(r.status_code)
        if r.status_code in (401, 403):
            gated = True; continue
        if r.status_code not in (200, 201, 204):
            continue
        written.append(ext)
        gb, _ = safe_request(session, "GET", path, timeout, verify)
        served_ct = gb.headers.get("Content-Type", "") if gb is not None else ""
        read_back = bool(gb is not None and gb.status_code == 200 and token in (gb.text or ""))
        risk = _ext_risk(ext, served_ct)
        if read_back:
            confirmed.append(ext)
            if link_url is None:
                link_url, cstatus = path, r.status_code
            if risk:
                danger.append(f"{ext} [{risk}]")
        elif risk:
            danger.append(f"{ext} [{risk}; not served back]")
        if keep:
            leftovers.append(path)
        elif not _delete(session, path, timeout, verify):
            leftovers.append(path)

    if confirmed:
        ev = f"file written & readable at {_link(link_url)}"
        if len(confirmed) > 1:
            ev += f" (+{len(confirmed)-1} more ext)"
        if danger:
            ev += " · " + C.RED + "; ".join(danger) + C.RESET + C.DIM
        if keep:
            ev += " · KEPT (open to verify)"
        return "confirmed", cstatus, ev, (leftovers or None)
    if written:
        ev = f"PUT accepted for {', '.join(written)} but nothing read back — UNVERIFIED"
        if danger:
            ev += " · " + "; ".join(danger)
        return "reachable", statuses[0] if statuses else None, ev, (leftovers or None)
    if gated:
        return "gated", 403, "auth/forbidden on write", None
    return "blocked", statuses[0] if statuses else None, "", None


# --- TRACE / TRACK: prove the request is echoed (XST) ----------------------- #
def validate_trace(session, base, method, timeout, verify):
    marker = secrets.token_urlsafe(12)
    r, err = safe_request(session, method, base, timeout, verify,
                          headers={"X-Methodscan-Marker": marker})
    if err:
        return "error", None, str(err), None
    if r.status_code in (405, 501, 400):
        return "blocked", r.status_code, "", None
    if r.status_code == 200 and marker in (r.text or ""):
        return "confirmed", 200, f"request echoed (XST) · marker {marker[:8]}…", None
    if r.status_code in (401, 403):
        return "gated", r.status_code, "", None
    return "reachable", r.status_code, "200 but no echo observed", None


# --- PROPFIND: prove WebDAV enumeration (207 Multi-Status) ------------------- #
def validate_propfind(session, base, timeout, verify):
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            '<D:propfind xmlns:D="DAV:"><D:allprop/></D:propfind>')
    r, err = safe_request(session, "PROPFIND", base, timeout, verify,
                          data=body.encode(),
                          headers={"Depth": "1", "Content-Type": "application/xml"})
    if err:
        return "error", None, str(err), None
    if r.status_code == 207:
        hrefs = (r.text or "").upper().count("<D:HREF") + (r.text or "").upper().count("<HREF")
        return "confirmed", 207, f"207 Multi-Status · {hrefs} href(s) listed", None
    if r.status_code in (405, 501, 400):
        return "blocked", r.status_code, "", None
    if r.status_code in (401, 403):
        return "gated", r.status_code, "", None
    return "reachable", r.status_code, "responded, no multistatus", None


# --- DELETE: stage a temp file, delete it, verify it is gone ---------------- #
def validate_delete(session, base, timeout, verify, keep):
    path, _t, pstat, ok = _put_temp(session, base, timeout, verify)
    if not ok:
        return "reachable", pstat, "not validated — couldn't stage a temp file (PUT unavailable)", None
    r, err = safe_request(session, "DELETE", path, timeout, verify)
    if err:
        return "error", None, str(err), [path]
    if r.status_code in (405, 501, 400):
        return "blocked", r.status_code, "DELETE blocked (temp file left behind)", [path]
    gb, _ = safe_request(session, "GET", path, timeout, verify)
    gone = bool(gb is not None and gb.status_code in (404, 410))
    if gone:
        return "confirmed", r.status_code, f"created then DELETED scanner temp {_link(path)} (verified gone)", None
    return "reachable", r.status_code, f"DELETE {r.status_code} but {_link(path)} still present — UNVERIFIED", [path]


# --- MOVE: stage a temp file, move it, verify src gone & dest present ------- #
def validate_move(session, base, timeout, verify, keep):
    src, token, pstat, ok = _put_temp(session, base, timeout, verify)
    if not ok:
        return "reachable", pstat, "not validated — couldn't stage a temp file (PUT unavailable)", None
    dest = base.rstrip("/") + f"/.methodscan-poc-{rand_token()}.txt"
    r, err = safe_request(session, "MOVE", src, timeout, verify,
                          headers={"Destination": dest, "Overwrite": "T"})
    if err:
        _delete(session, src, timeout, verify)
        return "error", None, str(err), None
    if r.status_code in (405, 501, 400):
        _delete(session, src, timeout, verify)
        return "blocked", r.status_code, "", None
    db, _ = safe_request(session, "GET", dest, timeout, verify)
    moved = bool(db is not None and db.status_code == 200 and token in (db.text or ""))
    if keep:
        v = "confirmed" if moved else "reachable"
        return v, r.status_code, f"MOVED scanner temp → {_link(dest)} · KEPT", [src, dest]
    leftovers = []
    if not _delete(session, dest, timeout, verify):
        leftovers.append(dest)
    _delete(session, src, timeout, verify)
    if moved:
        return "confirmed", r.status_code, f"MOVED scanner temp to {_link(dest)} then cleaned", (leftovers or None)
    return "reachable", r.status_code, f"MOVE {r.status_code} but move not verified — UNVERIFIED", (leftovers or None)


# --- COPY: stage a temp file, copy it, verify the copy holds the marker ----- #
def validate_copy(session, base, timeout, verify, keep):
    src, token, pstat, ok = _put_temp(session, base, timeout, verify)
    if not ok:
        return "reachable", pstat, "not validated — couldn't stage a temp file (PUT unavailable)", None
    dest = base.rstrip("/") + f"/.methodscan-poc-{rand_token()}.txt"
    r, err = safe_request(session, "COPY", src, timeout, verify,
                          headers={"Destination": dest, "Overwrite": "T"})
    if err:
        _delete(session, src, timeout, verify)
        return "error", None, str(err), None
    if r.status_code in (405, 501, 400):
        _delete(session, src, timeout, verify)
        return "blocked", r.status_code, "", None
    db, _ = safe_request(session, "GET", dest, timeout, verify)
    copied = bool(db is not None and db.status_code == 200 and token in (db.text or ""))
    if keep:
        v = "confirmed" if copied else "reachable"
        return v, r.status_code, f"COPIED scanner temp → {_link(dest)} · KEPT", [src, dest]
    leftovers = []
    for u in (dest, src):
        if not _delete(session, u, timeout, verify):
            leftovers.append(u)
    if copied:
        return "confirmed", r.status_code, f"COPIED scanner temp to {_link(dest)} then cleaned", (leftovers or None)
    return "reachable", r.status_code, f"COPY {r.status_code} but copy not verified — UNVERIFIED", (leftovers or None)


# --- MKCOL: create a new (random-named) collection, verify, remove ---------- #
def validate_mkcol(session, base, timeout, verify, keep):
    coll = base.rstrip("/") + f"/.methodscan-poc-{rand_token()}/"
    r, err = safe_request(session, "MKCOL", coll, timeout, verify)
    if err:
        return "error", None, str(err), None
    if r.status_code in (405, 501, 400):
        return "blocked", r.status_code, "", None
    if r.status_code in (401, 403):
        return "gated", r.status_code, "", None
    if r.status_code in (200, 201):
        pb, _ = safe_request(session, "PROPFIND", coll, timeout, verify, headers={"Depth": "0"})
        verified = bool(pb is not None and pb.status_code in (200, 207))
        if not verified:
            gb, _ = safe_request(session, "GET", coll, timeout, verify)
            verified = bool(gb is not None and gb.status_code in (200, 301, 401, 403))
        v = "confirmed" if verified else "reachable"
        if keep:
            return v, r.status_code, f"created collection {_link(coll)} · KEPT", [coll]
        cleaned = _delete(session, coll, timeout, verify)
        note = f"created collection {_link(coll)}"
        note += " · cleanup: deleted" if cleaned else " · cleanup FAILED"
        return v, r.status_code, note, (None if cleaned else [coll])
    return "reachable", r.status_code, f"MKCOL {r.status_code}", None


# --- PATCH: stage a temp file, modify it, verify the change ----------------- #
def validate_patch(session, base, timeout, verify, keep):
    src, _t, pstat, ok = _put_temp(session, base, timeout, verify)
    if not ok:
        return "reachable", pstat, "not validated — couldn't stage a temp file (PUT unavailable)", None
    newtok = secrets.token_urlsafe(12)
    r, err = safe_request(session, "PATCH", src, timeout, verify,
                          data=f"methodscan-patched {newtok}\n".encode(),
                          headers={"Content-Type": "text/plain"})
    if err:
        _delete(session, src, timeout, verify)
        return "error", None, str(err), None
    if r.status_code in (405, 501, 400):
        _delete(session, src, timeout, verify)
        return "blocked", r.status_code, "", None
    gb, _ = safe_request(session, "GET", src, timeout, verify)
    applied = bool(gb is not None and gb.status_code == 200 and newtok in (gb.text or ""))
    if keep:
        v = "confirmed" if applied else "reachable"
        note = (f"PATCH modified {_link(src)}" if applied
                else f"PATCH {r.status_code}, change not observed at {_link(src)} — UNVERIFIED")
        return v, r.status_code, note + " · KEPT", [src]
    cleaned = _delete(session, src, timeout, verify)
    lo = None if cleaned else [src]
    if applied:
        return "confirmed", r.status_code, f"PATCH modified scanner temp {_link(src)} (verified)", lo
    return "reachable", r.status_code, f"PATCH {r.status_code} but change not observed — UNVERIFIED", lo


VALIDATORS = {
    "PUT":      lambda s, b, t, v, k, exts: validate_put(s, b, t, v, k, exts),
    "TRACE":    lambda s, b, t, v, k, exts: validate_trace(s, b, "TRACE", t, v),
    "TRACK":    lambda s, b, t, v, k, exts: validate_trace(s, b, "TRACK", t, v),
    "PROPFIND": lambda s, b, t, v, k, exts: validate_propfind(s, b, t, v),
    "DELETE":   lambda s, b, t, v, k, exts: validate_delete(s, b, t, v, k),
    "MOVE":     lambda s, b, t, v, k, exts: validate_move(s, b, t, v, k),
    "COPY":     lambda s, b, t, v, k, exts: validate_copy(s, b, t, v, k),
    "MKCOL":    lambda s, b, t, v, k, exts: validate_mkcol(s, b, t, v, k),
    "PATCH":    lambda s, b, t, v, k, exts: validate_patch(s, b, t, v, k),
}


# --------------------------------------------------------------------------- #
# Reachability probe for everything else
# --------------------------------------------------------------------------- #
def probe_reachability(session, base, method, timeout, verify, probe_root):
    # State-changing verbs go to a random dead path so nothing real is touched.
    url = base
    if is_destructive(method) and not probe_root:
        url = base.rstrip("/") + "/.probe-" + rand_token()
    r, err = safe_request(session, method, url, timeout, verify)
    if err:
        return "error", None, ""
    s = r.status_code
    if s in (405, 501, 400):
        return "blocked", s, ""
    if s in (401, 403):
        return "gated", s, ""
    return "reachable", s, ("destructive — not validated" if is_destructive(method)
                            else "reachable — no validator")


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def scan_url(session, url, methods, timeout, verify, probe_root, do_poc, keep_poc, exts):
    result = {"url": url, "status": None, "advertised": [], "findings": {}, "error": None}
    r, err = safe_request(session, "OPTIONS", url, timeout, verify)
    if err:
        msg = "connection failed"
        if isinstance(err, requests.exceptions.SSLError):        msg = "SSL error"
        elif isinstance(err, requests.exceptions.ConnectTimeout): msg = "connect timeout"
        elif isinstance(err, requests.exceptions.ReadTimeout):    msg = "read timeout"
        result["error"] = msg
        return result
    result["status"] = r.status_code
    result["advertised"] = sorted(parse_allow(r.headers))

    for m in methods:
        if do_poc and m in VALIDATORS:
            verdict, status, ev, leftover = VALIDATORS[m](session, url, timeout, verify, keep_poc, exts)
        else:
            verdict, status, ev = probe_reachability(session, url, m, timeout, verify, probe_root)
            leftover = None
        result["findings"][m] = {"verdict": verdict, "status": status,
                                 "evidence": ev, "leftover": leftover}
    return result


def scan_target(target, scheme_mode, methods, timeout, verify, probe_root, do_poc, keep_poc, exts, user_agent):
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    last = None
    for url in build_urls(target, scheme_mode):
        last = scan_url(session, url, methods, timeout, verify, probe_root, do_poc, keep_poc, exts)
        if last["error"] is None and scheme_mode == "auto":
            return last
    return last


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
SEV_ORDER = {"confirmed": 0, "reachable": 1, "gated": 2, "blocked": 3, "error": 4}

def derive(r):
    adv = set(r["advertised"])
    confirmed, reachable, gated, hidden, leftovers = [], [], [], [], []
    for m, f in r["findings"].items():
        v = f["verdict"]
        if v == "confirmed":
            confirmed.append(m)
        elif v == "reachable" and is_risky(m):
            reachable.append(m)
        elif v == "gated" and is_risky(m):
            gated.append(m)
        if v in ("confirmed", "reachable") and is_risky(m) and m not in adv:
            hidden.append(m)
        lo = f.get("leftover")
        if lo:
            leftovers.extend(lo if isinstance(lo, list) else [lo])
    r["_confirmed"] = sorted(confirmed)
    r["_reachable"] = sorted(reachable)
    r["_gated"] = sorted(gated)
    r["_hidden"] = sorted(set(hidden))
    r["_leftovers"] = leftovers
    r["_advertised_risky"] = sorted(m for m in adv if is_risky(m))
    return r


def sev_style(verdict):
    return {
        "confirmed": (f"{C.RED}{C.BOLD}", "CONFIRMED"),
        "reachable": (C.YELLOW,            "REACHABLE"),
        "gated":     (f"{C.DIM}{C.CYAN}",  "GATED    "),
        "blocked":   (C.GREY,              "blocked  "),
        "error":     (C.GREY,              "error    "),
    }[verdict]


def print_result(r, verbose):
    if r is None:
        return
    if r["error"]:
        print(f"{C.GREY}[--] {r['url']}  ({r['error']}){C.RESET}")
        return
    derive(r)

    if r["_confirmed"]:
        tag = f"{C.RED}{C.BOLD}[VULN]{C.RESET}"
    elif r["_reachable"]:
        tag = f"{C.YELLOW}[warn]{C.RESET}"
    elif r["_advertised_risky"]:
        tag = f"{C.YELLOW}[adv?]{C.RESET}"
    else:
        tag = f"{C.GREY}[ ok ]{C.RESET}"

    # Compact header line.
    adv = ", ".join(r["advertised"]) or "none"
    print(f"{tag} {C.BOLD}{r['url']}{C.RESET} {C.DIM}· OPTIONS {r['status']} · advertised: {adv}{C.RESET}")

    # Only interesting rows by default; -v shows blocked/expected too.
    rows = sorted(r["findings"].items(),
                  key=lambda kv: (SEV_ORDER[kv[1]["verdict"]], kv[0]))
    for m, f in rows:
        v = f["verdict"]
        interesting = (v == "confirmed") or (v in ("reachable", "gated") and is_risky(m))
        if not interesting and not verbose:
            continue
        col, word = sev_style(v)
        code = f["status"] if f["status"] is not None else "---"
        hid = f" {C.MAGENTA}(hidden){C.RESET}" if m in r["_hidden"] else ""
        ev = f["evidence"] or note_for(m)
        print(f"     {col}{word}{C.RESET} {C.BOLD}{m:<16}{C.RESET}{C.DIM}{str(code):>4}{C.RESET}"
              f"{hid}  {C.DIM}{ev}{C.RESET}")

    for lo in r["_leftovers"]:
        print(f"     {C.RED}! left artifact on server: {lo}{C.RESET}")


def print_summary(results):
    total = len(results)
    reachable_hosts = sum(1 for r in results if r and not r["error"])
    vuln = [r for r in results if r and r.get("_confirmed")]
    warn = [r for r in results if r and not r.get("_confirmed") and r.get("_reachable")]
    hidden = [r for r in results if r and r.get("_hidden")]
    leftovers = [lo for r in results if r for lo in r.get("_leftovers", [])]

    print(f"\n{C.BOLD}{'='*70}{C.RESET}")
    print(f"{C.BOLD}Summary{C.RESET}  "
          f"scanned {total} · reachable {reachable_hosts} · "
          f"{C.RED}confirmed {len(vuln)}{C.RESET} · "
          f"{C.YELLOW}unvalidated {len(warn)}{C.RESET} · "
          f"{C.MAGENTA}hidden {len(hidden)}{C.RESET}")

    for r in vuln:
        methods = ", ".join(f"{m}" for m in r["_confirmed"])
        print(f"  {C.RED}{C.BOLD}VULN{C.RESET} {r['url']}  {C.RED}{methods}{C.RESET}")
    for r in warn:
        print(f"  {C.YELLOW}warn{C.RESET} {r['url']}  {C.DIM}reachable: {', '.join(r['_reachable'])}{C.RESET}")
    if leftovers:
        print(f"\n  {C.RED}PoC artifacts on server (open to verify, then remove):{C.RESET}")
        for lo in leftovers:
            print(f"    {C.CYAN}- {lo}{C.RESET}")
    print(f"{C.BOLD}{'='*70}{C.RESET}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_targets(args):
    targets = list(args.targets)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            targets += [ln.strip() for ln in fh if ln.strip()]
    if not targets and not sys.stdin.isatty():
        targets += [ln.strip() for ln in sys.stdin if ln.strip()]
    seen, out = set(), []
    for t in targets:
        if t and not t.startswith("#") and t not in seen:
            seen.add(t); out.append(t)
    return out


def main():
    p = argparse.ArgumentParser(
        description="Flag and PROVE insecure HTTP methods (advertised or hidden).",
        epilog="Only scan systems you are authorized to test.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("targets", nargs="*", help="IPs, domains, or URLs")
    p.add_argument("-f", "--file", help="File with one target per line")
    p.add_argument("--probe-all", action="store_true",
                   help="Test every catalog method, ignoring the Allow list")
    p.add_argument("--methods", help="Comma-separated methods to test (overrides --probe-all)")
    p.add_argument("--no-poc", action="store_true",
                   help="Reachability only — skip the active PoC validation (PUT/TRACE/PROPFIND)")
    p.add_argument("--keep-poc", action="store_true",
                   help="Do NOT delete the PUT proof file — leave it live so you can open the URL")
    p.add_argument("--probe-root", action="store_true",
                   help="Send destructive verbs to the real URL, not a random dead path (LOUD)")
    p.add_argument("-t", "--timeout", type=float, default=8.0, help="Per-request timeout (s)")
    p.add_argument("--threads", type=int, default=10, help="Concurrent targets")
    p.add_argument("--scheme", choices=["auto", "http", "https"], default="auto")
    p.add_argument("--insecure", action="store_true", help="Do NOT verify TLS certificates")
    p.add_argument("-v", "--verbose", action="store_true", help="Show blocked/expected rows too")
    p.add_argument("-o", "--output", help="Write full results (incl. evidence) to JSON")
    p.add_argument("--poc-ext", metavar="EXTS",
                   help="Comma-separated extensions the PUT PoC should try, e.g. "
                        ".txt,.html,.svg,.php — flags stored-XSS (served as html/svg) "
                        "and code-exec (script upload accepted). Content is always inert.")
    p.add_argument("--user-agent", default="http-methods-scan/3.0",
                   help="User-Agent sent on all requests (handy for spotting your "
                        "tests in the target's logs)")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args()

    maybe_disable_color(force=False)
    if args.no_color:
        C.disable()

    targets = load_targets(args)
    if not targets:
        p.error("No targets given. Pass them as arguments, with -f, or via stdin.")

    if args.methods:
        methods = [m.strip().upper() for m in args.methods.split(",") if m.strip()]
    elif args.probe_all:
        methods = list(ALL_METHODS)
    else:
        methods = []

    verify = not args.insecure
    do_poc = not args.no_poc
    keep_poc = args.keep_poc
    if args.poc_ext:
        exts = ["." + e.strip().lstrip(".").lower()
                for e in args.poc_ext.split(",") if e.strip()]
    else:
        exts = [".txt"]
    mode = (f"active + PoC ({len(methods)} methods)" if (methods and do_poc)
            else f"reachability ({len(methods)} methods)" if methods
            else "passive (OPTIONS only)")
    flags = ""
    if args.probe_root and methods:
        flags += f"  {C.YELLOW}[probe-root ON]{C.RESET}"
    if keep_poc and do_poc:
        flags += f"  {C.YELLOW}[keep-poc ON]{C.RESET}"
    if args.poc_ext and do_poc:
        flags += f"  {C.YELLOW}[poc-ext: {','.join(exts)}]{C.RESET}"
    print(f"{C.BOLD}Scanning {len(targets)} target(s) — {mode}{C.RESET}{flags}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(scan_target, t, args.scheme, methods, args.timeout,
                          verify, args.probe_root, do_poc, keep_poc, exts, args.user_agent): t
                for t in targets}
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            print_result(r, args.verbose)

    print_summary(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump([r for r in results if r], fh, indent=2)
        print(f"\n{C.DIM}Full results (with evidence) written to {args.output}{C.RESET}")

    sys.exit(1 if any(r and (r.get("_confirmed") or r.get("_reachable")) for r in results) else 0)


if __name__ == "__main__":
    main()
