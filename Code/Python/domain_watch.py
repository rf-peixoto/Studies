#!/usr/bin/env python3
"""
domain_watch.py
================
Free, no-cost pipeline to catch newly-registered / newly-certified domains
that look like they're impersonating your brand, so you can move fast on
takedown requests.

Data sources, all free:
  1. CertStream  - real-time firehose of every cert logged to public CT logs.
                   Attackers usually get a cert within minutes of standing up
                   a phishing site.
  2. WhoisDS     - free daily list of newly-registered domains (all TLDs).
  3. ICANN CZDS  - full daily zone files for TLDs you've been approved for.
                   Automated here via the CZDS REST API (no manual portal
                   clicks) -- requires your existing approved ICANN account.
  4. dnstwist    - generates typo/homoglyph/combosquat permutations of your
                   real domain(s), used as the match list for the above.

Config file
-----------
All brands/keywords/CZDS credentials live in a JSON config file, NOT in
command-line args. The file is re-read before every query, so you can edit
it live without restarting a long-running process. If it doesn't exist,
a template is generated on first run and the script exits so you can fill
it in.

Default path: ./domain_watch_config.json  (override with --config)

Install:
    pip install certstream dnstwist tldextract requests --break-system-packages

Usage:
    # First run - generates config template, then exits
    python3 domain_watch.py --mode stream

    # Long-running real-time CertStream watcher
    python3 domain_watch.py --mode stream

    # Daily batch check against WhoisDS newly-registered-domain list (cron this)
    python3 domain_watch.py --mode daily-batch

    # Daily automated CZDS zone-file pull + diff against known matches (cron this)
    python3 domain_watch.py --mode czds

# real-time CertStream watcher — run as a persistent service, not cron
python3 domain_watch.py --mode stream &

# daily batch checks
0 6 * * * python3 domain_watch.py --mode daily-batch
0 7 * * * python3 domain_watch.py --mode czds

"""

import argparse
import base64
import gzip
import io
import json
import re
import sys
import time
import zipfile
import datetime
from pathlib import Path

import requests

CONFIG_TEMPLATE = {
    "brands": [
        "yourbrand.com",
        "yourotherbrand.com"
    ],
    "keywords": [
        "yourbrand",
        "yourotherbrand"
    ],
    "czds": {
        "username": "you@example.com",
        "password": "CHANGE_ME",
        "tlds": ["com", "net"],
        "_note": "Only TLDs your ICANN CZDS account is already APPROVED for will download successfully."
    },
    "output": {
        "matches_file": "matches.jsonl",
        "known_matches_file": "known_matches.json"
    }
}


# ---------------------------------------------------------------------------
# Config handling
# ---------------------------------------------------------------------------
def ensure_config_exists(path: Path):
    if not path.exists():
        path.write_text(json.dumps(CONFIG_TEMPLATE, indent=2))
        print(f"No config found. Created a template at: {path}")
        print("Edit it with your real brand domains, keywords, and (optionally) "
              "CZDS credentials, then re-run.")
        sys.exit(0)


def load_config(path: Path):
    """Re-read the config file fresh every time this is called."""
    ensure_config_exists(path)
    with open(path) as f:
        return json.load(f)


def build_keyword_regex(keywords):
    kws = [k.strip().lower() for k in keywords if k.strip()]
    if not kws:
        return None
    return re.compile("|".join(re.escape(k) for k in kws))


# ---------------------------------------------------------------------------
# Known-matches tracking (so re-runs only alert on genuinely NEW hits)
# ---------------------------------------------------------------------------
def load_known(path: Path):
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def save_known(path: Path, known: set):
    path.write_text(json.dumps(sorted(known)))


def append_match(out_path: Path, record: dict):
    print(f"[MATCH] {record}", flush=True)
    with open(out_path, "a") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# 1. dnstwist permutation universe
# ---------------------------------------------------------------------------
def build_permutations(brand_domains):
    import dnstwist
    perms = set()
    for domain in brand_domains:
        domain = domain.strip().lower()
        if not domain:
            continue
        fuzzer = dnstwist.Fuzzer(domain)
        fuzzer.generate()
        for entry in fuzzer.domains:
            perms.add(entry["domain"].lower())
        perms.add(domain)
    return perms


# ---------------------------------------------------------------------------
# 2. CertStream real-time watch (long-running; reloads config on a timer
#    rather than per-message, since messages arrive very fast)
# ---------------------------------------------------------------------------
def run_certstream_watch(config_path: Path, reload_every_seconds=300):
    import certstream
    import tldextract

    state = {"permutations": set(), "keyword_re": None, "last_load": 0,
              "out_path": None, "known_path": None, "known": set()}

    def reload_if_needed():
        now = time.time()
        if now - state["last_load"] < reload_every_seconds and state["permutations"]:
            return
        cfg = load_config(config_path)
        state["permutations"] = build_permutations(cfg["brands"])
        state["keyword_re"] = build_keyword_regex(cfg["keywords"])
        state["out_path"] = Path(cfg["output"]["matches_file"])
        state["known_path"] = Path(cfg["output"]["known_matches_file"])
        if not state["known"]:
            state["known"] = load_known(state["known_path"])
        state["last_load"] = now
        print(f"[config reloaded] {len(state['permutations'])} permutations, "
              f"{len(cfg['brands'])} brand(s)")

    reload_if_needed()

    def callback(message, context):
        reload_if_needed()
        if message.get("message_type") != "certificate_update":
            return
        leaf = message["data"]["leaf_cert"]
        all_domains = set(d.lower() for d in leaf.get("all_domains", []) if d)

        for raw in all_domains:
            fqdn = raw.lstrip("*.")
            ext = tldextract.extract(fqdn)
            registrable = f"{ext.domain}.{ext.suffix}".lower()

            reason = None
            if registrable in state["permutations"] or fqdn in state["permutations"]:
                reason = "permutation_match"
            elif state["keyword_re"] and state["keyword_re"].search(fqdn):
                reason = "keyword_match"

            if reason and fqdn not in state["known"]:
                state["known"].add(fqdn)
                save_known(state["known_path"], state["known"])
                append_match(state["out_path"], {
                    "seen_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "domain": fqdn,
                    "reason": reason,
                    "cert_issuer": leaf.get("issuer", {}).get("O"),
                    "source": "certstream",
                })

    while True:
        try:
            certstream.listen_for_events(callback, url="wss://certstream.calidog.io/")
        except Exception as e:
            print(f"CertStream connection dropped ({e}), reconnecting in 10s...", file=sys.stderr)
            time.sleep(10)


# ---------------------------------------------------------------------------
# 3. WhoisDS daily batch (fixed: URL now requires base64-encoded filename)
# ---------------------------------------------------------------------------
def fetch_nrd_list(config_path: Path):
    cfg = load_config(config_path)
    keyword_re = build_keyword_regex(cfg["keywords"])
    permutations = build_permutations(cfg["brands"])
    out_path = Path(cfg["output"]["matches_file"])
    known_path = Path(cfg["output"]["known_matches_file"])
    known = load_known(known_path)

    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    filename = f"{yesterday}.zip"
    b64name = base64.b64encode(filename.encode()).decode()
    url = f"https://whoisds.com//whois-database/newly-registered-domains/{b64name}/nrd"

    resp = requests.get(url, timeout=60, headers={"User-Agent": "domain-watch/1.0"})
    resp.raise_for_status()

    if not resp.content.startswith(b"PK"):
        # Not a real zip -- WhoisDS returned an error/HTML page instead.
        print(f"WhoisDS did not return a zip file (got {len(resp.content)} bytes, "
              f"content-type={resp.headers.get('content-type')}). "
              f"Check https://www.whoisds.com/newly-registered-domains for current "
              f"URL format -- they change it periodically.", file=sys.stderr)
        return []

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    new_matches = []
    for name in zf.namelist():
        for line in zf.read(name).decode(errors="ignore").splitlines():
            domain = line.strip().lower()
            if not domain or domain in known:
                continue
            hit = None
            if domain in permutations:
                hit = "permutation_match"
            elif keyword_re and keyword_re.search(domain):
                hit = "keyword_match"
            if hit:
                known.add(domain)
                new_matches.append(domain)
                append_match(out_path, {
                    "seen_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "domain": domain,
                    "reason": hit,
                    "source": "whoisds_nrd",
                    "nrd_date": yesterday,
                })

    save_known(known_path, known)
    print(f"WhoisDS batch check for {yesterday}: {len(new_matches)} new matches.")
    return new_matches


# ---------------------------------------------------------------------------
# 4. ICANN CZDS - fully automated via the REST API
#    Auth:      POST https://account-api.icann.org/api/authenticate
#    List URLs: GET  https://czds-api.icann.org/czds/downloads/links
#    Download:  GET  each returned URL (gzip, streamed) with Bearer token
# ---------------------------------------------------------------------------
def czds_authenticate(username, password):
    resp = requests.post(
        "https://account-api.icann.org/api/authenticate",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"CZDS auth failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["accessToken"]


def czds_list_zone_urls(token):
    resp = requests.get(
        "https://czds-api.icann.org/czds/downloads/links",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()  # list of URLs like https://czds-api.icann.org/czds/downloads/com.zone


def czds_stream_zone_domains(url, token):
    """Stream-download a gzipped zone file and yield each domain name found
    (from NS/A/etc record lines), without holding the whole file in memory --
    zone files for big TLDs (.com etc) can be gigabytes."""
    with requests.get(url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with gzip.GzipFile(fileobj=resp.raw) as gz:
            buf = io.BufferedReader(gz)
            for raw_line in buf:
                try:
                    line = raw_line.decode(errors="ignore")
                except Exception:
                    continue
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                # BIND zone format: "example.com. 3600 IN NS ns1.foo.com."
                parts = line.split()
                if len(parts) >= 1:
                    domain = parts[0].rstrip(".").lower()
                    if domain:
                        yield domain


def run_czds(config_path: Path):
    cfg = load_config(config_path)
    czds_cfg = cfg.get("czds", {})
    username, password = czds_cfg.get("username"), czds_cfg.get("password")
    wanted_tlds = set(t.lower() for t in czds_cfg.get("tlds", []))

    if not username or "CHANGE_ME" in (password or ""):
        print("CZDS credentials not set in config -- skipping CZDS mode. "
              "Fill in czds.username / czds.password in the config file.", file=sys.stderr)
        return []

    keyword_re = build_keyword_regex(cfg["keywords"])
    permutations = build_permutations(cfg["brands"])
    out_path = Path(cfg["output"]["matches_file"])
    known_path = Path(cfg["output"]["known_matches_file"])
    known = load_known(known_path)

    token = czds_authenticate(username, password)
    zone_urls = czds_list_zone_urls(token)

    new_matches = []
    for url in zone_urls:
        tld = url.rstrip("/").split("/")[-1].replace(".zone", "").lower()
        if wanted_tlds and tld not in wanted_tlds:
            continue
        print(f"Streaming zone file for .{tld} ...")
        try:
            for domain in czds_stream_zone_domains(url, token):
                if domain in known:
                    continue
                hit = None
                if domain in permutations:
                    hit = "permutation_match"
                elif keyword_re and keyword_re.search(domain):
                    hit = "keyword_match"
                if hit:
                    known.add(domain)
                    new_matches.append(domain)
                    append_match(out_path, {
                        "seen_at": datetime.datetime.utcnow().isoformat() + "Z",
                        "domain": domain,
                        "reason": hit,
                        "source": f"czds_{tld}",
                    })
        except requests.HTTPError as e:
            print(f"  skipped .{tld}: {e}", file=sys.stderr)

    save_known(known_path, known)
    print(f"CZDS run complete: {len(new_matches)} new matches across {len(zone_urls)} available zones.")
    return new_matches


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="domain_watch_config.json",
                     help="Path to JSON config file (auto-created on first run)")
    ap.add_argument("--mode", choices=["stream", "daily-batch", "czds"], default="stream",
                     help="'stream' = long-running CertStream watch (run as a service); "
                          "'daily-batch' = one-shot WhoisDS NRD check (cron daily); "
                          "'czds' = one-shot ICANN CZDS zone pull + diff (cron daily)")
    args = ap.parse_args()

    cfg_path = Path(args.config)

    if args.mode == "stream":
        run_certstream_watch(cfg_path)
    elif args.mode == "daily-batch":
        fetch_nrd_list(cfg_path)
    elif args.mode == "czds":
        run_czds(cfg_path)
