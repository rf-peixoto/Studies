#!/usr/bin/env python3
"""
Web mention monitor
-------------------
Searches several free sources (no browser, no paid API keys) for mentions of a
list of URLs, remembers links already reported in SQLite, and sends a daily
Telegram summary grouped by which source found each link.

Sources
  Web search engines (query = the target URL):
    duckduckgo  - HTML version, strict rate limit (~4 requests in a row)
    bing        - Bing's RSS output format
    marginalia  - independent small-web index, shared public API key
    mojeek      - off by default (blocks many server IPs with a 403)
  Communities (query = the distinctive term, e.g. "rf-peixoto"):
    github      - issues/PRs and READMEs in other people's repos (public API, optional token)
    hackernews  - stories and comments via the Algolia HN API
    reddit      - posts via reddit's public JSON search

Usage:
    python3 monitor.py --config config.json            # normal daily run
    python3 monitor.py --config config.json --init     # store current results, send nothing
    python3 monitor.py --config config.json --dry-run  # print the report, send nothing, store nothing
    python3 monitor.py --config config.json --dry-run --only bing,reddit --save-html debug/
    python3 monitor.py --config config.json --test-telegram
"""

import argparse
import html
import json
import logging
import os
import random
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

import requests

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]
BOT_UA = "web-mention-monitor/1.0 (personal mention alerts)"  # for APIs that want an honest UA

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "trk", "ref_src")

# "query": "target" searches the URL itself, "term" searches the distinctive word
# (e.g. rf-peixoto). "trusted" sources match exactly, so the relevance filter is skipped.
DEFAULT_SOURCES = {
    "duckduckgo": {"enabled": True, "query": "target", "region": "wt-wt", "time_filter": "",
                   "max_pages": 1, "delay_seconds": [40, 70]},
    "bing":       {"enabled": True, "query": "target", "market": "en-US", "delay_seconds": [10, 20]},
    "marginalia": {"enabled": True, "query": "term", "delay_seconds": [5, 10]},
    "mojeek":     {"enabled": False, "query": "target", "max_pages": 1, "delay_seconds": [8, 15]},
    "github":     {"enabled": True, "query": "term", "token": "", "delay_seconds": [7, 10],
                   "trusted": True},
    "hackernews": {"enabled": True, "query": "term", "delay_seconds": [2, 4]},
    "reddit":     {"enabled": True, "query": "term", "delay_seconds": [5, 10]},
}

SOURCE_NAMES = {"duckduckgo": "DuckDuckGo", "bing": "Bing", "marginalia": "Marginalia",
                "mojeek": "Mojeek", "github": "GitHub", "hackernews": "Hacker News",
                "reddit": "Reddit"}

log = logging.getLogger("monitor")


class SourceBlocked(Exception):
    """The source is refusing requests (rate limit, bot check, IP block)."""


class SourceError(Exception):
    """Network or other temporary failure."""


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class Throttle:
    """Random minimum gap between requests to the same source."""

    def __init__(self, delay):
        self.lo, self.hi = delay
        self.next = 0.0

    def wait(self):
        now = time.monotonic()
        if self.next > now:
            time.sleep(self.next - now)
        self.next = time.monotonic() + random.uniform(self.lo, self.hi)


class Ctx:
    """What a source function needs besides the query."""

    def __init__(self, session, scfg, throttle, retries, save_dir, name, cfg):
        self.session, self.scfg, self.throttle = session, scfg, throttle
        self.retries, self.save_dir, self.name, self.cfg = retries, save_dir, name, cfg

    def get(self, method, url, browser_ua=True, **kw):
        self.throttle.wait()
        headers = {"User-Agent": random.choice(USER_AGENTS) if browser_ua else BOT_UA,
                   "Accept-Language": "en-US,en;q=0.8,pt-BR;q=0.6"}
        headers.update(kw.pop("headers", {}))
        for attempt in range(self.retries):
            try:
                r = self.session.request(method, url, headers=headers, timeout=30, **kw)
            except requests.RequestException as e:
                log.warning("%s network error: %s (attempt %d)", self.name, e, attempt + 1)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (202, 403, 429, 503):
                raise SourceBlocked(f"status {r.status_code}")
            return r
        raise SourceError("network error")

    def save(self, query, body, ext="html"):
        if not self.save_dir:
            return
        os.makedirs(self.save_dir, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in query)[:60]
        path = os.path.join(self.save_dir, f"{self.name}_{safe}_{int(time.time())}.{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        log.info("Saved raw response to %s", path)


def clean(text):
    return " ".join((text or "").split())


def strip_tags(text):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", text or "")))


def result(url, title, snippet="", text=""):
    """snippet is shown in the report; text is extra content used only for relevance."""
    return {"url": url, "title": clean(title), "snippet": clean(snippet), "text": text or ""}


# --------------------------------------------------------------------------- #
# DuckDuckGo
# --------------------------------------------------------------------------- #
class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results, self.forms = [], []
        self._cur, self._in_title, self._snippet_tag, self._form = None, False, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._cur = {"href": a.get("href", ""), "title": "", "snippet": ""}
            self.results.append(self._cur)
            self._in_title = True
        elif "result__snippet" in classes and self._cur is not None:
            self._snippet_tag = tag
        elif tag == "form":
            self._form = {"inputs": {}, "submit": None}
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            if (a.get("type") or "").lower() == "submit":
                self._form["submit"] = a.get("value")
            elif a.get("name"):
                self._form["inputs"][a["name"]] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_title = False
        if self._snippet_tag and tag == self._snippet_tag:
            self._snippet_tag = None
        if tag == "form":
            self._form = None

    def handle_data(self, data):
        if self._in_title and self._cur is not None:
            self._cur["title"] += data
        elif self._snippet_tag and self._cur is not None:
            self._cur["snippet"] += data

    def next_page_params(self):
        for f in self.forms:
            if (f["submit"] or "").strip().lower() == "next":
                return f["inputs"]
        return None


def unwrap_ddg_link(href):
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    p = urlparse(href)
    if p.netloc.endswith("duckduckgo.com"):
        if p.path.startswith("/l/"):
            target = parse_qs(p.query).get("uddg", [None])[0]
            return unquote(target) if target else None
        return None  # ads (/y.js) and internal links
    return href if p.scheme in ("http", "https") else None


def src_duckduckgo(ctx, query):
    data = {"q": query, "kl": ctx.scfg["region"]}
    if ctx.scfg.get("time_filter"):
        data["df"] = ctx.scfg["time_filter"]
    out = []
    for _ in range(ctx.scfg["max_pages"]):
        r = ctx.get("POST", "https://html.duckduckgo.com/html/", data=data,
                    headers={"Referer": "https://html.duckduckgo.com/"})
        low = r.text.lower()
        if "anomaly-modal" in low or "bots use duckduckgo" in low:
            raise SourceBlocked("bot check page")
        ctx.save(query, r.text)
        parser = DDGParser()
        parser.feed(r.text)
        for item in parser.results:
            link = unwrap_ddg_link(item["href"])
            if link:
                out.append(result(link, item["title"], item["snippet"]))
        nxt = parser.next_page_params()
        if not nxt or not parser.results:
            break
        data = nxt
    return out


# --------------------------------------------------------------------------- #
# Bing (RSS output)
# --------------------------------------------------------------------------- #
def src_bing(ctx, query):
    r = ctx.get("GET", "https://www.bing.com/search",
                params={"q": query, "format": "rss", "count": 30, "mkt": ctx.scfg["market"]})
    ctx.save(query, r.text, "xml")
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        if "captcha" in r.text.lower():
            raise SourceBlocked("captcha page")
        raise SourceError("Bing did not return RSS (layout change or block?)")
    return [result(item.findtext("link", ""), item.findtext("title", ""),
                   strip_tags(item.findtext("description", "")))
            for item in root.iter("item") if item.findtext("link")]


# --------------------------------------------------------------------------- #
# Marginalia
# --------------------------------------------------------------------------- #
def src_marginalia(ctx, query):
    r = ctx.get("GET", f"https://api.marginalia.nu/public/search/{quote(query, safe='')}",
                browser_ua=False, params={"count": 30})
    ctx.save(query, r.text, "json")
    try:
        data = r.json()
    except ValueError:
        raise SourceError("Marginalia did not return JSON")
    return [result(x.get("url", ""), x.get("title", ""), x.get("description", ""))
            for x in data.get("results", []) if x.get("url")]


# --------------------------------------------------------------------------- #
# Mojeek
# --------------------------------------------------------------------------- #
class MojeekParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._depth = 0
        self._cur = None
        self._in_h2 = self._in_title = self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "ul":
            if self._depth:
                self._depth += 1
            elif any(c.startswith("results") for c in classes):
                self._depth = 1
        elif tag == "li" and self._depth == 1:
            self._cur = {"href": "", "title": "", "snippet": ""}
            self.results.append(self._cur)
        elif self._cur is None:
            return
        elif tag == "h2":
            self._in_h2 = True
        elif tag == "a" and not self._cur["href"] and ("title" in classes or self._in_h2):
            self._cur["href"] = a.get("href", "")
            self._in_title = True
        elif tag == "p" and "s" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "ul" and self._depth:
            self._depth -= 1
            if not self._depth:
                self._cur = None
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "a":
            self._in_title = False
        elif tag == "p":
            self._in_snippet = False

    def handle_data(self, data):
        if self._cur is None:
            return
        if self._in_title:
            self._cur["title"] += data
        elif self._in_snippet:
            self._cur["snippet"] += data


def src_mojeek(ctx, query):
    out = []
    for page in range(ctx.scfg["max_pages"]):
        params = {"q": query}
        if page:
            params["s"] = page * 10 + 1
        r = ctx.get("GET", "https://www.mojeek.com/search", params=params)
        if "automated queries" in r.text.lower():
            raise SourceBlocked("bot check page")
        ctx.save(query, r.text)
        parser = MojeekParser()
        parser.feed(r.text)
        found = [x for x in parser.results if x["href"].startswith(("http://", "https://"))]
        out += [result(x["href"], x["title"], x["snippet"]) for x in found]
        if len(found) < 10:
            break
    return out


# --------------------------------------------------------------------------- #
# GitHub (public search API; 10 searches/min without a token)
# --------------------------------------------------------------------------- #
def src_github(ctx, term):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if ctx.scfg.get("token"):
        headers["Authorization"] = f"Bearer {ctx.scfg['token']}"
    not_mine = " ".join(f"-user:{u}" for u in github_users(ctx.cfg))
    out = []

    # Issues, pull requests and their text mentioning you in other people's repos
    r = ctx.get("GET", "https://api.github.com/search/issues", browser_ua=False, headers=headers,
                params={"q": f'"{term}" {not_mine}', "sort": "created", "order": "desc",
                        "per_page": 30})
    ctx.save(term + "_issues", r.text, "json")
    for x in r.json().get("items", []):
        repo = "/".join(x.get("repository_url", "").split("/")[-2:])
        kind = "PR" if x.get("pull_request") else "Issue"
        out.append(result(x["html_url"], f"{kind} in {repo}: {x.get('title', '')}",
                          (x.get("body") or "")[:400]))

    # Repositories whose README mentions you (awesome-lists, forks of ideas, write-ups)
    r = ctx.get("GET", "https://api.github.com/search/repositories", browser_ua=False,
                headers=headers, params={"q": f'"{term}" in:readme {not_mine}',
                                         "sort": "updated", "per_page": 30})
    ctx.save(term + "_repos", r.text, "json")
    for x in r.json().get("items", []):
        out.append(result(x["html_url"], f"Repo {x['full_name']} mentions you in its README",
                          x.get("description") or ""))
    return out


# --------------------------------------------------------------------------- #
# Hacker News (Algolia)
# --------------------------------------------------------------------------- #
def src_hackernews(ctx, term):
    r = ctx.get("GET", "https://hn.algolia.com/api/v1/search_by_date", browser_ua=False,
                params={"query": term, "tags": "(story,comment)", "hitsPerPage": 50})
    ctx.save(term, r.text, "json")
    out = []
    for h in r.json().get("hits", []):
        link = f"https://news.ycombinator.com/item?id={h['objectID']}"
        if h.get("comment_text"):
            title = f"HN comment on: {h.get('story_title') or 'a story'}"
            body = h["comment_text"]
        else:
            title = f"HN story: {h.get('title') or ''}"
            body = h.get("story_text") or ""
        out.append(result(link, title, strip_tags(body)[:400],
                          text=" ".join(filter(None, [h.get("url"), h.get("story_url"), body]))))
    return out


# --------------------------------------------------------------------------- #
# Reddit (public JSON search)
# --------------------------------------------------------------------------- #
def src_reddit(ctx, term):
    r = ctx.get("GET", "https://www.reddit.com/search.json", browser_ua=False,
                params={"q": term, "sort": "new", "limit": 50, "type": "link"})
    ctx.save(term, r.text, "json")
    try:
        children = r.json()["data"]["children"]
    except (ValueError, KeyError):
        raise SourceBlocked("unexpected response (reddit may require login from this IP)")
    out = []
    for c in children:
        d = c.get("data", {})
        link = "https://www.reddit.com" + d.get("permalink", "")
        out.append(result(link, f"r/{d.get('subreddit', '?')}: {d.get('title', '')}",
                          (d.get("selftext") or "")[:400],
                          text=" ".join(filter(None, [d.get("url"), d.get("selftext")]))))
    return out


SOURCES = {"duckduckgo": src_duckduckgo, "bing": src_bing, "marginalia": src_marginalia,
           "mojeek": src_mojeek, "github": src_github, "hackernews": src_hackernews,
           "reddit": src_reddit}


# --------------------------------------------------------------------------- #
# Targets, terms, URLs
# --------------------------------------------------------------------------- #
def strip_scheme(u):
    u = u.strip()
    for pre in ("https://", "http://"):
        if u.lower().startswith(pre):
            u = u[len(pre):]
    if u.lower().startswith("www."):
        u = u[4:]
    return u.rstrip("/").lower()


def github_users(cfg):
    users = []
    for t in cfg["targets"]:
        host, _, path = strip_scheme(t).partition("/")
        if host == "github.com" and path:
            users.append(path.split("/")[0])
    return users


def match_terms(target, cfg):
    """Words a result must contain to count as a real mention of this target."""
    custom = cfg.get("match_terms", {}).get(target)
    if custom:
        return [t.lower() for t in custom]
    host, _, path = target.partition("/")
    return [path.rsplit("/", 1)[-1] if path else host]


def build_jobs(cfg):
    """Per source: list of (label, query, relevance_terms)."""
    targets = [strip_scheme(t) for t in cfg["targets"]]
    terms = {}
    for t in targets:
        for term in match_terms(t, cfg):
            terms.setdefault(term, t)
    jobs = {}
    for name, scfg in cfg["sources"].items():
        if scfg["query"] == "target":
            q = [(t, t, match_terms(t, cfg)) for t in targets]
        else:
            q = [(term, term, [term]) for term in terms]
        q += [("extra", x, []) for x in cfg.get("extra_queries", [])]
        jobs[name] = q
    return jobs


def is_relevant(res, terms):
    if not terms:
        return True
    hay = " ".join((unquote(res["url"]), res["title"], res["snippet"], res["text"])).lower()
    return any(t in hay for t in terms)


def normalize_url(url):
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if host.endswith("reddit.com"):
        host = "reddit.com"  # old./new./np. all point to the same post
    path = p.path.rstrip("/") or "/"
    params = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
              if not k.lower().startswith(TRACKING_PREFIXES)]
    return urlunparse(("https", host, path, "", urlencode(sorted(params)), ""))


def is_excluded(norm_url, exclusions):
    p = urlparse(norm_url)
    host, path = p.hostname or "", p.path.lower()
    for ex in exclusions:
        ex_host, _, ex_path = ex.partition("/")
        if not (host == ex_host or host.endswith("." + ex_host)):
            continue
        if not ex_path:
            return True
        ex_path = "/" + ex_path.rstrip("/")
        if path == ex_path or path.startswith(ex_path + "/") or path.startswith(ex_path + "_"):
            return True
    return False


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def open_db(path):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            url        TEXT PRIMARY KEY,
            title      TEXT,
            target     TEXT,
            query      TEXT,
            first_seen TEXT NOT NULL
        )""")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(seen)")}
    if "last_seen" not in cols:
        conn.execute("ALTER TABLE seen ADD COLUMN last_seen TEXT")
        conn.execute("UPDATE seen SET last_seen = first_seen")
    if "engines" not in cols:
        conn.execute("ALTER TABLE seen ADD COLUMN engines TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seen_last ON seen(last_seen)")
    conn.commit()
    return conn


def purge_old(conn, days):
    """Drops links no source has returned for `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    cur = conn.execute("DELETE FROM seen WHERE last_seen < ?", (cutoff,))
    conn.commit()
    if cur.rowcount:
        log.info("Purged %d links not seen for %d days", cur.rowcount, days)


def already_seen(conn, url):
    return conn.execute("SELECT 1 FROM seen WHERE url = ?", (url,)).fetchone() is not None


def store(conn, new_items, seen_again, today):
    conn.executemany(
        "INSERT OR IGNORE INTO seen (url, title, target, query, engines, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(i["key"], i["title"], i["target"], i["query"], ",".join(sorted(i["sources"])),
          today, today) for i in new_items])
    conn.executemany("UPDATE seen SET last_seen = ? WHERE url = ?",
                     [(today, key) for key in seen_again])
    conn.commit()


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in split_message(text):
        r = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML",
                                     "disable_web_page_preview": True}, timeout=30)
        if r.status_code != 200 or not r.json().get("ok"):
            raise RuntimeError(f"Telegram error {r.status_code}: {r.text[:300]}")
        time.sleep(1)


def split_message(text, limit=4000):
    """Splits on blank lines, then on single lines, so HTML tags never get cut."""
    chunks, cur = [], ""
    pieces = []
    for block in text.split("\n\n"):
        if len(block) <= limit:
            pieces.append(block)
        else:
            pieces += [ln[:limit] for ln in block.split("\n")]
    for piece in pieces:
        candidate = (cur + "\n\n" + piece) if cur else piece
        if len(candidate) > limit and cur:
            chunks.append(cur)
            cur = piece
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def format_item(i, show_sources=False):
    e = html.escape
    line = f'• <a href="{e(i["url"], quote=True)}">{e(i["title"] or i["url"])}</a>'
    if i["target"] != "extra":
        line += f"  <code>{e(i['target'])}</code>"
    if show_sources:
        line += "  [" + ", ".join(SOURCE_NAMES[s] for s in sorted(i["sources"])) + "]"
    if i["snippet"]:
        s = i["snippet"] if len(i["snippet"]) <= 200 else i["snippet"][:197] + "..."
        line += f"\n   <i>{e(s)}</i>"
    return line


def build_report(new_items, today, stats, n_checked, show_common):
    header = f"🔎 <b>Web monitor</b> — {today}"
    status = []
    for name, st in stats.items():
        line = f"{SOURCE_NAMES[name]} {st['ok']}/{st['ok'] + st['failed']}"
        if st["blocked"]:
            line += " (blocked)"
        status.append(line)
    footer = "<i>" + " · ".join(status) + "</i>"

    if sum(st["ok"] for st in stats.values()) == 0:
        return f"{header}\n\n⚠️ All searches failed, nothing was checked today.\n{footer}"

    if len(stats) > 1 and any(st["failed"] for st in stats.values()):
        footer += "\n⚠️ Some sources missed searches, so a few \"only on\" links may exist elsewhere too."

    sections = []
    for name in stats:
        only = [i for i in new_items if i["sources"] == {name}]
        if only:
            sections.append(f"<b>Only on {SOURCE_NAMES[name]}</b> ({len(only)})\n"
                            + "\n".join(format_item(i) for i in only))
    common = [i for i in new_items if len(i["sources"]) > 1]
    if show_common and common:
        sections.append(f"<b>Found by several sources</b> ({len(common)})\n"
                        + "\n".join(format_item(i, show_sources=True) for i in common))

    if not sections:
        return f"{header}\n\nNothing new found ({n_checked} results checked).\n{footer}"
    shown = sum(1 for i in new_items if show_common or len(i["sources"]) == 1)
    return f"{header}\n{shown} new result(s):\n\n" + "\n\n".join(sections) + f"\n\n{footer}"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_config(path, only=None):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    user_sources = cfg.get("sources") or cfg.get("engines") or {}  # "engines" = older config name
    sources = {}
    for name, defaults in DEFAULT_SOURCES.items():
        merged = {**defaults, **user_sources.get(name, {})}
        enabled = (name in only) if only else merged["enabled"]
        if enabled:
            sources[name] = merged
    if not sources:
        raise SystemExit("No source enabled (check config 'sources' or --only)")
    cfg["sources"] = sources
    cfg.setdefault("retention_days", 90)
    cfg.setdefault("exclude", [])
    cfg.setdefault("retries", 2)
    cfg.setdefault("require_match", True)
    cfg.setdefault("show_common", True)
    db = cfg.get("database", "monitor.db")
    if not os.path.isabs(db):
        db = os.path.join(os.path.dirname(os.path.abspath(path)), db)
    cfg["database"] = db
    own = {strip_scheme(x) for x in cfg["targets"] + cfg["exclude"]}
    own |= {f"{u}.github.io" for u in github_users(cfg)}  # your GitHub Pages sites
    cfg["exclusions"] = sorted(own)
    return cfg


def run(cfg, mode, save_dir=None):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = open_db(cfg["database"])
    if mode != "dry-run":
        purge_old(conn, cfg["retention_days"])

    session = requests.Session()
    jobs = build_jobs(cfg)
    stats, ctxs = {}, {}
    for name, scfg in cfg["sources"].items():
        stats[name] = {"ok": 0, "failed": 0, "blocked": False}
        ctxs[name] = Ctx(session, scfg, Throttle(scfg["delay_seconds"]), cfg["retries"],
                         save_dir, name, cfg)
    found, seen_again, n_checked = {}, set(), 0

    # Always run the source that is allowed to go soonest, so the long
    # DuckDuckGo pauses are spent querying the other sources.
    while any(jobs.values()):
        name = min((n for n in jobs if jobs[n]), key=lambda n: ctxs[n].throttle.next)
        label, query, terms = jobs[name].pop(0)
        st = stats[name]
        if st["blocked"]:
            st["failed"] += 1
            continue
        try:
            results = SOURCES[name](ctxs[name], query)
        except SourceBlocked as e:
            log.warning("%s blocked on %r (%s); skipping it for the rest of this run",
                        SOURCE_NAMES[name], query, e)
            st["blocked"] = True
            st["failed"] += 1
            continue
        except (SourceError, ValueError, KeyError) as e:
            log.error("%s failed on %r: %s", SOURCE_NAMES[name], query, e)
            st["failed"] += 1
            continue
        st["ok"] += 1
        log.info("%s %r -> %d results", SOURCE_NAMES[name], query, len(results))

        check = cfg["require_match"] and not cfg["sources"][name].get("trusted")
        for r in results:
            n_checked += 1
            key = normalize_url(r["url"])
            if not key or is_excluded(key, cfg["exclusions"]):
                continue
            if check and not is_relevant(r, terms):
                continue
            if key in found:
                found[key]["sources"].add(name)
            elif already_seen(conn, key):
                seen_again.add(key)
            else:
                found[key] = {**r, "key": key, "target": label, "query": query,
                              "sources": {name}}

    new_items = list(found.values())
    report = build_report(new_items, today, stats, n_checked, cfg["show_common"])

    if mode == "dry-run":
        print(report)
    elif mode == "init":
        store(conn, new_items, seen_again, today)
        log.info("Init: stored %d existing links without alerting", len(new_items))
    else:
        tg = cfg["telegram"]
        send_telegram(tg["bot_token"], tg["chat_id"], report)
        store(conn, new_items, seen_again, today)  # only after a successful send
        log.info("Sent report with %d new links", len(new_items))
    conn.close()


def main():
    ap = argparse.ArgumentParser(description="Monitor web mentions of your URLs")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--dry-run", action="store_true", help="print report, don't send or store")
    ap.add_argument("--init", action="store_true", help="store current results without alerting")
    ap.add_argument("--test-telegram", action="store_true", help="send a test message and exit")
    ap.add_argument("--only", metavar="SOURCES",
                    help="comma-separated sources to use this run, e.g. bing,reddit")
    ap.add_argument("--save-html", metavar="DIR", help="save raw responses (for debugging parsers)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    only = None
    if args.only:
        only = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        unknown = only - set(DEFAULT_SOURCES)
        if unknown:
            raise SystemExit(f"Unknown source(s): {', '.join(sorted(unknown))}. "
                             f"Available: {', '.join(DEFAULT_SOURCES)}")
    cfg = load_config(args.config, only)

    if args.test_telegram:
        send_telegram(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"],
                      "✅ Web monitor: Telegram is configured correctly.")
        return

    mode = "dry-run" if args.dry_run else "init" if args.init else "normal"
    try:
        run(cfg, mode, args.save_html)
    except Exception as e:
        log.exception("Run failed")
        if mode == "normal":
            try:
                send_telegram(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"],
                              f"❌ Web monitor failed: {html.escape(str(e))[:500]}")
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
