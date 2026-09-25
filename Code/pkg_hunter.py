#!/usr/bin/env python3
"""
pkg_hunter.py - hunt public package registries for packages that mention your
keywords, DOWNLOAD the artifacts (never install, never extract, never execute),
and produce a report with links for manual malware review.
Optional: look up / upload every artifact to VirusTotal.

Registries
  pypi       PyPI (name match against the full project index, cached 24h)
  npm        npm registry
  nuget      NuGet
  maven      Maven Central
  rubygems   RubyGems
  crates     crates.io (Rust)
  go         Go modules (pkg.go.dev search + proxy.golang.org download)
  packagist  Packagist (PHP / Composer)
  pub        pub.dev (Dart / Flutter)
  hex        hex.pm (Elixir / Erlang)
  cpan       MetaCPAN (Perl)
  openvsx    Open VSX (VS Code-compatible extensions)
  vscode     Visual Studio Code Marketplace extensions
  (+ go-index: optional scan of index.golang.org for modules published in the
     last N hours, see --go-index-hours; catches brand-new typosquats)

Usage
  pip install requests
  python pkg_hunter.py -k acme -k acme-internal
  python pkg_hunter.py -K keywords.txt -r npm,pypi,nuget --vt
  VT_API_KEY=xxxx python pkg_hunter.py -K keywords.txt --vt --go-index-hours 48

Output (in --out, default ./pkg_hunt)
  report.html       clickable table: registry page, download URL, local file, VT
  results.csv/json  same data, machine readable
  downloads/<registry>/<name>-<version>.<ext>   read-only artifacts
  history.json      what was seen before -> "NEW" flag on later runs

SAFETY: the downloaded files may be live malware. Run this and do your review
inside a disposable VM / sandbox, don't extract archives on your host, and
never `pip install` / `npm install` anything you pulled down here.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import html
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    sys.exit("This script needs 'requests':  pip install requests")

log = logging.getLogger("pkg_hunter")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Pkg:
    registry: str
    name: str
    version: str = ""
    description: str = ""
    page_url: str = ""
    download_url: str = ""
    keyword: str = ""
    alt_urls: list = dataclasses.field(default_factory=list)
    local_file: str = ""
    sha256: str = ""
    size: int = 0
    is_new: bool = False
    first_seen: str = ""
    vt_link: str = ""
    vt_result: str = ""
    error: str = ""

    @property
    def key(self) -> str:
        return f"{self.registry}:{self.name}"

    @property
    def vkey(self) -> str:
        return f"{self.registry}:{self.name}@{self.version}"


# --------------------------------------------------------------------------- #
# HTTP with retries + per-host politeness
# --------------------------------------------------------------------------- #
HOST_MIN_INTERVAL = {  # seconds between requests to the same host
    "crates.io": 1.0,        # crates.io crawler policy: max 1 req/s
    "hex.pm": 0.7,
    "pkg.go.dev": 1.0,
    "rubygems.org": 0.15,
    "search.maven.org": 0.5,
    "packagist.org": 0.2,
    "fastapi.metacpan.org": 0.3,
}


class Http:
    def __init__(self, user_agent: str, timeout: int = 60):
        s = requests.Session()
        retry = Retry(
            total=5, backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "HEAD"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=32)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers["User-Agent"] = user_agent
        self.s = s
        self.timeout = timeout
        self._lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        interval = HOST_MIN_INTERVAL.get(host)
        if not interval:
            return
        with self._lock:
            hl = self._host_locks.setdefault(host, threading.Lock())
        with hl:
            wait = self._last.get(host, 0) + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def get(self, url, **kw) -> requests.Response:
        self._throttle(url)
        kw.setdefault("timeout", self.timeout)
        return self.s.get(url, **kw)

    def post(self, url, **kw) -> requests.Response:
        self._throttle(url)
        kw.setdefault("timeout", self.timeout)
        return self.s.post(url, **kw)

    def json(self, url, method="GET", **kw):
        r = self.post(url, **kw) if method == "POST" else self.get(url, **kw)
        r.raise_for_status()
        return r.json()


# --------------------------------------------------------------------------- #
# Context + keyword matching
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return re.sub(r"[-_.\s/]+", "", s.lower())


def hit(kw: str, *texts: str) -> bool:
    """Case-insensitive substring match; also ignores - _ . separators so
    'acme-core', 'acme_core' and 'acmecore' all match keyword 'acmecore'."""
    k, nk = kw.lower(), _norm(kw)
    for t in texts:
        if not t:
            continue
        if k in t.lower() or (nk and nk in _norm(t)):
            return True
    return False


class Ctx:
    def __init__(self, args, http: Http, out: Path):
        self.http = http
        self.out = out
        self.cache_dir = out / ".cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limit = args.max_results
        self.loose = args.loose
        self._memo: dict = {}
        self._memo_lock = threading.Lock()

    def memo(self, key, fn):
        with self._memo_lock:
            if key not in self._memo:
                self._memo[key] = fn()
            return self._memo[key]

    def keep(self, kw: str, p: Pkg) -> bool:
        return self.loose or hit(kw, p.name, p.description)


# --------------------------------------------------------------------------- #
# Registry searchers: each returns candidate Pkg objects for one keyword
# --------------------------------------------------------------------------- #
def search_pypi(ctx: Ctx, kw: str) -> list[Pkg]:
    # PyPI has no search API any more; match against the full project index.
    def load_names():
        cache = ctx.cache_dir / "pypi_simple.json"
        if cache.exists() and time.time() - cache.stat().st_mtime < 24 * 3600:
            return json.loads(cache.read_text())
        log.info("pypi: downloading full project index (cached for 24h)...")
        data = ctx.http.json("https://pypi.org/simple/", timeout=300,
                             headers={"Accept": "application/vnd.pypi.simple.v1+json"})
        names = [p["name"] for p in data["projects"]]
        cache.write_text(json.dumps(names))
        return names

    names = [n for n in ctx.memo("pypi_names", load_names) if hit(kw, n)][: ctx.limit]
    out = []
    for n in names:
        page = f"https://pypi.org/project/{n}/"
        try:
            d = ctx.http.json(f"https://pypi.org/pypi/{quote(n)}/json")
        except Exception as e:
            out.append(Pkg("pypi", n, page_url=page, keyword=kw, error=f"metadata: {e}"))
            continue
        info, urls = d["info"], d.get("urls") or []
        sdist = next((u for u in urls if u.get("packagetype") == "sdist"), None)
        f = sdist or (urls[0] if urls else None)
        out.append(Pkg("pypi", info["name"], info.get("version", ""), info.get("summary") or "",
                       f"https://pypi.org/project/{info['name']}/{info.get('version', '')}/",
                       f["url"] if f else "", kw,
                       alt_urls=[u["url"] for u in urls if u is not f][:1]))
    return out


def search_npm(ctx: Ctx, kw: str) -> list[Pkg]:
    out, frm = [], 0
    while frm < ctx.limit:
        d = ctx.http.json("https://registry.npmjs.org/-/v1/search",
                          params={"text": kw, "size": 250, "from": frm})
        objs = d.get("objects", [])
        for o in objs:
            p = o["package"]
            name, ver = p["name"], p.get("version", "")
            base = name.split("/")[-1]
            out.append(Pkg("npm", name, ver, p.get("description") or "",
                           f"https://www.npmjs.com/package/{name}/v/{ver}",
                           f"https://registry.npmjs.org/{name}/-/{base}-{ver}.tgz", kw))
        frm += len(objs)
        if not objs or frm >= d.get("total", 0):
            break
    return out


def search_nuget(ctx: Ctx, kw: str) -> list[Pkg]:
    endpoint = ctx.memo("nuget_search", lambda: next(
        r["@id"] for r in ctx.http.json("https://api.nuget.org/v3/index.json")["resources"]
        if r["@type"].startswith("SearchQueryService")))
    out, skip = [], 0
    while skip < ctx.limit:
        take = min(1000, ctx.limit - skip)
        d = ctx.http.json(endpoint, params={"q": kw, "skip": skip, "take": take,
                                            "prerelease": "true", "semVerLevel": "2.0.0"})
        data = d.get("data", [])
        for x in data:
            pid, ver = x["id"], x.get("version", "")
            lid, lv = pid.lower(), ver.split("+")[0].lower()
            out.append(Pkg("nuget", pid, ver, x.get("description") or "",
                           f"https://www.nuget.org/packages/{pid}/{ver}",
                           f"https://api.nuget.org/v3-flatcontainer/{lid}/{lv}/{lid}.{lv}.nupkg", kw))
        skip += len(data)
        if not data or skip >= d.get("totalHits", 0):
            break
    return out


def search_maven(ctx: Ctx, kw: str) -> list[Pkg]:
    out, start = [], 0
    while start < ctx.limit:
        d = ctx.http.json("https://search.maven.org/solrsearch/select",
                          params={"q": kw, "rows": 200, "start": start, "wt": "json"})
        docs = d.get("response", {}).get("docs", [])
        for x in docs:
            g, a = x["g"], x["a"]
            v = x.get("latestVersion") or x.get("v", "")
            ext = {"pom": "pom", "aar": "aar", "war": "war", "ear": "ear"}.get(x.get("p", "jar"), "jar")
            base = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{v}/{a}-{v}"
            out.append(Pkg("maven", f"{g}:{a}", v, "",
                           f"https://central.sonatype.com/artifact/{g}/{a}/{v}",
                           f"{base}.{ext}", kw, alt_urls=[f"{base}.pom"] if ext != "pom" else []))
        start += len(docs)
        if not docs or start >= d.get("response", {}).get("numFound", 0):
            break
    return out


def search_rubygems(ctx: Ctx, kw: str) -> list[Pkg]:
    out, page = [], 1
    while len(out) < ctx.limit:
        d = ctx.http.json("https://rubygems.org/api/v1/search.json", params={"query": kw, "page": page})
        if not d:
            break
        for g in d:
            n, v = g["name"], g.get("version", "")
            out.append(Pkg("rubygems", n, v, g.get("info") or "",
                           f"https://rubygems.org/gems/{n}/versions/{v}",
                           g.get("gem_uri") or f"https://rubygems.org/downloads/{n}-{v}.gem", kw))
        page += 1
    return out


def search_crates(ctx: Ctx, kw: str) -> list[Pkg]:
    out, page = [], 1
    while len(out) < ctx.limit:
        d = ctx.http.json("https://crates.io/api/v1/crates",
                          params={"q": kw, "per_page": 100, "page": page})
        crates = d.get("crates", [])
        for c in crates:
            n = c["name"]
            v = c.get("max_stable_version") or c.get("newest_version") or c.get("max_version", "")
            out.append(Pkg("crates", n, v, c.get("description") or "",
                           f"https://crates.io/crates/{n}/{v}",
                           f"https://static.crates.io/crates/{n}/{n}-{v}.crate", kw))
        if len(crates) < 100 or page * 100 >= d.get("meta", {}).get("total", 0):
            break
        page += 1
    return out


def _go_escape(s: str) -> str:
    # proxy.golang.org "case-encoding": uppercase X -> !x
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), s)


def _go_module_pkg(ctx: Ctx, mod: str, ver: str, kw: str, desc: str = "") -> Pkg:
    return Pkg("go", mod, ver, desc, f"https://pkg.go.dev/{mod}@{ver}",
               f"https://proxy.golang.org/{_go_escape(mod)}/@v/{_go_escape(ver)}.zip", kw)


def _go_resolve(ctx: Ctx, pkg_path: str):
    """Package path -> (module path, latest version) by walking up the path."""
    parts = pkg_path.split("/")
    for i in range(len(parts), 0, -1):
        mod = "/".join(parts[:i])
        r = ctx.http.get(f"https://proxy.golang.org/{_go_escape(mod)}/@latest")
        if r.status_code == 200:
            return mod, r.json().get("Version", "")
    return None, None


def search_go(ctx: Ctx, kw: str) -> list[Pkg]:
    paths: list[str] = []
    page = 1
    while len(paths) < ctx.limit and page <= 10:
        r = ctx.http.get("https://pkg.go.dev/search",
                         params={"q": kw, "m": "package", "limit": 100, "page": page})
        if r.status_code != 200:
            break
        found = 0
        for tag in re.findall(r"<a\b[^>]*>", r.text):
            if "snippet-title" not in tag and "search result" not in tag:
                continue
            m = re.search(r'href="/([^"?#]+)', tag)
            if m:
                p = html.unescape(m.group(1))
                if p not in paths:
                    paths.append(p)
                    found += 1
        if found == 0:
            break
        page += 1
    if not ctx.loose:
        paths = [p for p in paths if hit(kw, p)]
    out, seen_mods = [], set()
    for p in paths[: ctx.limit]:
        mod, ver = _go_resolve(ctx, p)
        if not mod:
            out.append(Pkg("go", p, page_url=f"https://pkg.go.dev/{p}", keyword=kw,
                           error="module not found on proxy.golang.org"))
            continue
        if mod in seen_mods:
            continue
        seen_mods.add(mod)
        out.append(_go_module_pkg(ctx, mod, ver, kw, desc=f"(matched package {p})" if p != mod else ""))
    return out


def scan_go_index(ctx: Ctx, keywords: list[str], hours: int) -> list[Pkg]:
    """Scan index.golang.org for every module version published in the last N hours."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    latest: dict[str, tuple[str, str]] = {}
    total = 0
    while True:
        r = ctx.http.get("https://index.golang.org/index", params={"since": since, "limit": 2000})
        r.raise_for_status()
        entries = [json.loads(l) for l in r.text.splitlines() if l.strip()]
        total += len(entries)
        for e in entries:
            for kw in keywords:
                if hit(kw, e["Path"]):
                    latest[e["Path"]] = (e["Version"], kw)
                    break
        if len(entries) < 2000:
            break
        since = entries[-1]["Timestamp"]
    log.info("go-index: scanned %d module versions from the last %dh, %d match", total, hours, len(latest))
    return [_go_module_pkg(ctx, m, v, kw, desc=f"published in last {hours}h (index.golang.org)")
            for m, (v, kw) in latest.items()]


def search_packagist(ctx: Ctx, kw: str) -> list[Pkg]:
    raw, url, params = [], "https://packagist.org/search.json", {"q": kw, "per_page": 100}
    while url and len(raw) < ctx.limit:
        d = ctx.http.json(url, params=params)
        params = None  # 'next' already carries the query string
        raw.extend(d.get("results", []))
        url = d.get("next")
    out = []
    for x in raw[: ctx.limit]:
        n, desc = x["name"], x.get("description") or ""
        if not ctx.loose and not hit(kw, n, desc):
            continue
        p = Pkg("packagist", n, "", desc, f"https://packagist.org/packages/{n}", "", kw)
        try:
            meta = ctx.http.json(f"https://repo.packagist.org/p2/{n}.json")
            vers = meta.get("packages", {}).get(n) or []
            stable = next((v for v in vers if not re.search(r"dev|alpha|beta|rc", v.get("version", ""), re.I)),
                          vers[0] if vers else None)
            if stable:
                p.version = stable.get("version", "")
                p.download_url = (stable.get("dist") or {}).get("url", "")
                if not p.download_url:
                    p.error = "no dist archive (source-only package): " + str((stable.get("source") or {}).get("url", ""))
        except Exception as e:
            p.error = f"metadata: {e}"
        out.append(p)
    return out


def search_pub(ctx: Ctx, kw: str) -> list[Pkg]:
    names, page = [], 1
    while len(names) < ctx.limit:
        d = ctx.http.json("https://pub.dev/api/search", params={"q": kw, "page": page})
        names += [p["package"] for p in d.get("packages", [])]
        if not d.get("next"):
            break
        page += 1
    out = []
    for n in names[: ctx.limit]:
        try:
            d = ctx.http.json(f"https://pub.dev/api/packages/{n}")
            latest = d.get("latest", {})
            v = latest.get("version", "")
            out.append(Pkg("pub", n, v, (latest.get("pubspec") or {}).get("description") or "",
                           f"https://pub.dev/packages/{n}/versions/{v}", latest.get("archive_url", ""), kw))
        except Exception as e:
            out.append(Pkg("pub", n, page_url=f"https://pub.dev/packages/{n}", keyword=kw, error=str(e)))
    return out


def search_hex(ctx: Ctx, kw: str) -> list[Pkg]:
    out, page = [], 1
    while len(out) < ctx.limit:
        d = ctx.http.json("https://hex.pm/api/packages", params={"search": kw, "page": page})
        for x in d:
            n = x["name"]
            v = x.get("latest_stable_version") or x.get("latest_version") or ""
            out.append(Pkg("hex", n, v, (x.get("meta") or {}).get("description") or "",
                           x.get("html_url") or f"https://hex.pm/packages/{n}",
                           f"https://repo.hex.pm/tarballs/{n}-{v}.tar", kw))
        if len(d) < 100:
            break
        page += 1
    return out


def search_cpan(ctx: Ctx, kw: str) -> list[Pkg]:
    variants = {kw, kw.lower(), kw.capitalize(), kw.upper()}
    def esc(v: str) -> str:  # escape Lucene special chars
        return re.sub(r"([^A-Za-z0-9_-])", r"\\\1", v)
    wild = " OR ".join("distribution:*" + esc(v) + "*" for v in variants)
    body = {
        "size": min(ctx.limit, 500),
        "query": {"bool": {"must": [
            {"term": {"status": "latest"}},
            {"query_string": {"query": f"({wild}) OR abstract:\"{kw}\"", "analyze_wildcard": True}},
        ]}},
        "_source": ["distribution", "version", "abstract", "download_url", "author", "name"],
    }
    d = ctx.http.json("https://fastapi.metacpan.org/v1/release/_search", method="POST", json=body)
    out = []
    for h in d.get("hits", {}).get("hits", []):
        s = h.get("_source", {})
        out.append(Pkg("cpan", s.get("distribution", ""), str(s.get("version", "")), s.get("abstract") or "",
                       f"https://metacpan.org/release/{s.get('author')}/{s.get('name')}",
                       s.get("download_url", ""), kw))
    return out


def search_openvsx(ctx: Ctx, kw: str) -> list[Pkg]:
    out, off = [], 0
    while off < ctx.limit:
        d = ctx.http.json("https://open-vsx.org/api/-/search",
                          params={"query": kw, "size": 100, "offset": off})
        exts = d.get("extensions", [])
        for e in exts:
            ns, n, v = e.get("namespace", ""), e.get("name", ""), e.get("version", "")
            out.append(Pkg("openvsx", f"{ns}.{n}", v, e.get("description") or "",
                           f"https://open-vsx.org/extension/{ns}/{n}/{v}",
                           (e.get("files") or {}).get("download", ""), kw))
        off += len(exts)
        if not exts or off >= d.get("totalSize", 0):
            break
    return out


def search_vscode(ctx: Ctx, kw: str) -> list[Pkg]:
    url = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
    headers = {"Accept": "application/json;api-version=7.2-preview.1", "Content-Type": "application/json"}
    out, page = [], 1
    while len(out) < ctx.limit:
        body = {
            "filters": [{
                "criteria": [
                    {"filterType": 8, "value": "Microsoft.VisualStudio.Code"},
                    {"filterType": 10, "value": kw},
                    {"filterType": 12, "value": "4096"},
                ],
                "pageNumber": page, "pageSize": 100, "sortBy": 0, "sortOrder": 0,
            }],
            "assetTypes": [],
            # IncludeVersions | IncludeFiles | IncludeAssetUri | IncludeLatestVersionOnly
            "flags": 0x1 | 0x2 | 0x80 | 0x200,
        }
        d = ctx.http.json(url, method="POST", json=body, headers=headers)
        res = (d.get("results") or [{}])[0]
        exts = res.get("extensions", [])
        for e in exts:
            pub = (e.get("publisher") or {}).get("publisherName", "")
            n = e.get("extensionName", "")
            vers = e.get("versions") or [{}]
            v = vers[0].get("version", "")
            vsix = next((f.get("source") for f in vers[0].get("files", [])
                         if f.get("assetType") == "Microsoft.VisualStudio.Services.VSIXPackage"), None)
            vsix = vsix or (f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
                            f"{pub}/vsextensions/{n}/{v}/vspackage")
            out.append(Pkg("vscode", f"{pub}.{n}", v, e.get("shortDescription") or e.get("displayName") or "",
                           f"https://marketplace.visualstudio.com/items?itemName={pub}.{n}", vsix, kw))
        if len(exts) < 100:
            break
        page += 1
    return out


REGISTRIES = {
    "pypi": search_pypi,
    "npm": search_npm,
    "nuget": search_nuget,
    "maven": search_maven,
    "rubygems": search_rubygems,
    "crates": search_crates,
    "go": search_go,
    "packagist": search_packagist,
    "pub": search_pub,
    "hex": search_hex,
    "cpan": search_cpan,
    "openvsx": search_openvsx,
    "vscode": search_vscode,
}


# --------------------------------------------------------------------------- #
# Download (never extract / install)
# --------------------------------------------------------------------------- #
KNOWN_EXT = (".tar.gz", ".tar.bz2", ".tgz", ".whl", ".zip", ".nupkg", ".jar", ".pom", ".aar",
             ".war", ".ear", ".gem", ".crate", ".tar", ".vsix", ".egg")
DEFAULT_EXT = {"vscode": ".vsix", "openvsx": ".vsix", "go": ".zip", "packagist": ".zip",
               "hex": ".tar", "crates": ".crate", "pub": ".tar.gz", "npm": ".tgz", "nuget": ".nupkg",
               "rubygems": ".gem", "cpan": ".tar.gz"}


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@+-]+", "_", s).strip("._")[:180] or "pkg"


def _ext_for(p: Pkg, url: str) -> str:
    path = urlparse(url).path.lower()
    for e in KNOWN_EXT:
        if path.endswith(e):
            return e
    return DEFAULT_EXT.get(p.registry, ".bin")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(http: Http, out: Path, p: Pkg, max_bytes: int) -> None:
    if not p.download_url:
        p.error = p.error or "no download URL"
        return
    d = out / "downloads" / p.registry
    d.mkdir(parents=True, exist_ok=True)
    urls = [p.download_url, *p.alt_urls]
    for i, url in enumerate(urls):
        target = d / (_safe(f"{p.name}-{p.version}") + _ext_for(p, url))
        if target.exists() and target.stat().st_size > 0:  # already downloaded on an earlier run
            p.local_file, p.size, p.sha256 = str(target.relative_to(out)), target.stat().st_size, _sha256_file(target)
            return
        tmp = target.with_name(target.name + ".part")
        try:
            with http.s.get(url, stream=True, timeout=http.timeout, allow_redirects=True) as r:
                if r.status_code == 404 and i < len(urls) - 1:
                    continue
                r.raise_for_status()
                if int(r.headers.get("Content-Length") or 0) > max_bytes:
                    p.error = f"skipped: larger than {max_bytes // 2**20} MB"
                    return
                h, n = hashlib.sha256(), 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        n += len(chunk)
                        if n > max_bytes:
                            raise ValueError(f"larger than {max_bytes // 2**20} MB, aborted")
                        h.update(chunk)
                        f.write(chunk)
            os.replace(tmp, target)
            os.chmod(target, 0o444)  # read-only, never executable
            p.local_file, p.size, p.sha256 = str(target.relative_to(out)), n, h.hexdigest()
            if url != p.download_url:
                p.download_url = url
            return
        except Exception as e:
            tmp.unlink(missing_ok=True)
            p.error = f"download: {e}"
            return


# --------------------------------------------------------------------------- #
# VirusTotal
# --------------------------------------------------------------------------- #
class VirusTotal:
    API = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: str, per_minute: float):
        self.s = requests.Session()
        self.s.headers.update({"x-apikey": api_key, "accept": "application/json"})
        self.interval = 60.0 / per_minute
        self._last = 0.0

    def _req(self, method, url, **kw):
        for _ in range(3):
            wait = self._last + self.interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = self.s.request(method, url, timeout=300, **kw)
            if r.status_code == 429:
                log.warning("VirusTotal quota hit, sleeping 60s")
                time.sleep(60)
                continue
            return r
        return r

    def process(self, out: Path, p: Pkg) -> None:
        if not p.sha256:
            return
        p.vt_link = f"https://www.virustotal.com/gui/file/{p.sha256}"
        r = self._req("GET", f"{self.API}/files/{p.sha256}")
        if r.status_code == 200:
            attrs = r.json()["data"]["attributes"]
            st = attrs.get("last_analysis_stats", {})
            if not st or sum(st.values()) == 0:
                p.vt_result = "known to VT, analysis pending"
            else:
                p.vt_result = (f"{st.get('malicious', 0)} malicious / {st.get('suspicious', 0)} suspicious "
                               f"of {sum(st.values())}")
            return
        if r.status_code != 404:
            p.vt_result = f"lookup error {r.status_code}"
            return
        path = out / p.local_file
        size = path.stat().st_size
        if size > 650 * 2**20:
            p.vt_result = "too large for VT upload"
            return
        url = f"{self.API}/files"
        if size > 32 * 2**20:
            u = self._req("GET", f"{self.API}/files/upload_url")
            if u.status_code != 200:
                p.vt_result = f"upload_url error {u.status_code}"
                return
            url = u.json()["data"]
        with open(path, "rb") as f:
            r = self._req("POST", url, files={"file": (path.name, f)})
        p.vt_result = ("uploaded, analysis pending - re-run with --vt later for the verdict"
                       if r.status_code == 200 else f"upload error {r.status_code}: {r.text[:120]}")


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
FIELDS = ["is_new", "registry", "name", "version", "keyword", "description", "page_url",
          "download_url", "local_file", "sha256", "size", "first_seen", "vt_result", "vt_link", "error"]


def write_reports(out: Path, pkgs: list[Pkg], keywords: list[str]) -> Path:
    rows = [{k: getattr(p, k) for k in FIELDS} for p in pkgs]
    (out / "results.json").write_text(json.dumps(rows, indent=2))
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    e = html.escape

    def a(url, label):
        return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(label)}</a>' if url else ""

    trs = []
    for p in pkgs:
        vt_cls = "bad" if re.match(r"[1-9]", p.vt_result or "") else ""
        links = " · ".join(x for x in [a(p.page_url, "page"), a(p.download_url, "download"),
                                       a(p.local_file, "local file"), a(p.vt_link, "VirusTotal")] if x)
        trs.append(
            f'<tr class="{"new" if p.is_new else ""}">'
            f'<td>{"NEW" if p.is_new else ""}</td><td>{e(p.registry)}</td>'
            f'<td class="mono">{e(p.name)}</td><td class="mono">{e(p.version)}</td>'
            f'<td>{e(p.keyword)}</td><td class="desc">{e(p.description[:300])}</td>'
            f'<td>{links}</td><td class="mono" title="{e(p.sha256)}">{e(p.sha256[:12])}</td>'
            f'<td class="{vt_cls}">{e(p.vt_result)}</td><td class="err">{e(p.error)}</td></tr>')
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Package hunt report</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#1d1d1f;background:#fff}}
h1{{font-size:20px;margin:0 0 4px}} .meta{{color:#666;margin-bottom:12px}}
input{{padding:6px 10px;width:320px;max-width:100%;border:1px solid #ccc;border-radius:6px}}
label{{margin-left:12px}} table{{border-collapse:collapse;width:100%;margin-top:12px}}
th,td{{border-bottom:1px solid #e5e5e5;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f5f5f7;position:sticky;top:0;cursor:pointer}} tr.new td{{background:#fff8e1}}
.mono{{font-family:ui-monospace,monospace;font-size:12.5px}} .desc{{max-width:380px;color:#444}}
.err{{color:#b00020;font-size:12px}} .bad{{color:#b00020;font-weight:600}} a{{color:#0b57d0}}
</style></head><body>
<h1>Package hunt report</h1>
<div class="meta">{e(now)} · keywords: {e(", ".join(keywords))} · {len(pkgs)} packages ·
{sum(p.is_new for p in pkgs)} new · downloaded artifacts are read-only in <code>downloads/</code> - review in a sandbox</div>
<input id="q" placeholder="Filter rows..."><label><input type="checkbox" id="onlynew"> only new</label>
<table id="t"><thead><tr><th>New</th><th>Registry</th><th>Package</th><th>Version</th><th>Keyword</th>
<th>Description</th><th>Links</th><th>SHA-256</th><th>VirusTotal</th><th>Error</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table>
<script>
const q=document.getElementById('q'),o=document.getElementById('onlynew'),rows=[...document.querySelectorAll('#t tbody tr')];
function f(){{const s=q.value.toLowerCase();rows.forEach(r=>{{r.style.display=(r.textContent.toLowerCase().includes(s)&&(!o.checked||r.classList.contains('new')))?'':'none'}})}}
q.oninput=f;o.onchange=f;
document.querySelectorAll('#t th').forEach((th,i)=>th.onclick=()=>{{const tb=document.querySelector('#t tbody');
const d=th.dataset.d=th.dataset.d==='1'?'0':'1';[...tb.rows].sort((a,b)=>(a.cells[i].textContent.localeCompare(b.cells[i].textContent))*(d==='1'?1:-1)).forEach(r=>tb.appendChild(r))}});
</script></body></html>"""
    path = out / "report.html"
    path.write_text(doc, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Search package registries for keywords, download artifacts for review.")
    ap.add_argument("-k", "--keyword", action="append", default=[], help="keyword (repeatable)")
    ap.add_argument("-K", "--keywords-file", help="file with one keyword per line (# comments ok)")
    ap.add_argument("-r", "--registries", default="all",
                    help=f"comma list or 'all' (default). Available: {','.join(REGISTRIES)}")
    ap.add_argument("-o", "--out", default="pkg_hunt", help="output directory (default ./pkg_hunt)")
    ap.add_argument("--max-results", type=int, default=300,
                    help="max search results scanned per registry per keyword (default 300)")
    ap.add_argument("--loose", action="store_true",
                    help="keep every search hit, even if name/description doesn't literally contain the keyword")
    ap.add_argument("--no-download", action="store_true", help="only list links, don't download")
    ap.add_argument("--max-size-mb", type=int, default=100, help="skip artifacts bigger than this (default 100)")
    ap.add_argument("--workers", type=int, default=6, help="parallel searches/downloads (default 6)")
    ap.add_argument("--go-index-hours", type=int, default=0,
                    help="also scan index.golang.org for Go modules published in the last N hours")
    ap.add_argument("--new-only", action="store_true", help="report only packages/versions not seen in earlier runs")
    ap.add_argument("--vt", action="store_true", help="look up / upload artifacts to VirusTotal (needs VT_API_KEY)")
    ap.add_argument("--vt-rate", type=float, default=4, help="VT requests per minute (public API: 4)")
    ap.add_argument("--contact", default="", help="contact info added to User-Agent (crates.io asks for one)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    keywords = [k.strip() for k in args.keyword if k.strip()]
    if args.keywords_file:
        keywords += [l.strip() for l in Path(args.keywords_file).read_text().splitlines()
                     if l.strip() and not l.lstrip().startswith("#")]
    keywords = list(dict.fromkeys(keywords))
    if not keywords:
        ap.error("give at least one keyword with -k or -K")

    regs = list(REGISTRIES) if args.registries == "all" else [r.strip() for r in args.registries.split(",") if r.strip()]
    unknown = [r for r in regs if r not in REGISTRIES]
    if unknown:
        ap.error(f"unknown registries: {unknown}")

    vt = None
    if args.vt:
        key = os.environ.get("VT_API_KEY")
        if not key:
            ap.error("--vt needs the VT_API_KEY environment variable")
        vt = VirusTotal(key, args.vt_rate)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ua = "pkg-hunter/1.0 (package security review" + (f"; {args.contact}" if args.contact else "") + ")"
    http = Http(ua)
    ctx = Ctx(args, http, out)

    # ---- search -------------------------------------------------------------
    found: dict[str, Pkg] = {}
    jobs = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for r in regs:
            for kw in keywords:
                jobs[ex.submit(REGISTRIES[r], ctx, kw)] = (r, kw)
        if args.go_index_hours > 0:
            jobs[ex.submit(scan_go_index, ctx, keywords, args.go_index_hours)] = ("go-index", "*")
        for fut in as_completed(jobs):
            r, kw = jobs[fut]
            try:
                cands = fut.result()
            except Exception as e:
                log.error("%s [%s]: search failed: %s", r, kw, e)
                continue
            kept = [p for p in cands if p.error or p.keyword == "*" or ctx.keep(p.keyword, p)]
            log.info("%-9s [%s]: %d results, %d match", r, kw, len(cands), len(kept))
            for p in kept:
                found.setdefault(p.key, p)

    pkgs = sorted(found.values(), key=lambda p: (p.registry, p.name.lower()))

    # ---- history / new flag ---------------------------------------------------
    hist_path = out / "history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for p in pkgs:
        p.is_new = p.vkey not in history
        p.first_seen = history.setdefault(p.vkey, now)
    hist_path.write_text(json.dumps(history, indent=1, sort_keys=True))
    if args.new_only:
        pkgs = [p for p in pkgs if p.is_new]

    # ---- download ---------------------------------------------------------------
    if not args.no_download:
        todo = [p for p in pkgs if p.download_url]
        log.info("downloading %d artifacts to %s", len(todo), out / "downloads")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(download, http, out, p, args.max_size_mb * 2**20) for p in todo]
            for i, _ in enumerate(as_completed(futs), 1):
                if i % 25 == 0 or i == len(futs):
                    log.info("  %d/%d downloaded", i, len(futs))

    # ---- VirusTotal ---------------------------------------------------------------
    if vt:
        todo = [p for p in pkgs if p.sha256]
        eta = len(todo) * 60 / args.vt_rate / 60
        log.info("VirusTotal: %d files (~%.0f min at %.0f req/min, more if uploads are needed)",
                 len(todo), eta, args.vt_rate)
        for i, p in enumerate(todo, 1):
            try:
                vt.process(out, p)
            except Exception as e:
                p.vt_result = f"error: {e}"
            log.info("  VT %d/%d %s:%s -> %s", i, len(todo), p.registry, p.name, p.vt_result)
            write_reports(out, pkgs, keywords)  # keep report current during long VT runs

    report = write_reports(out, pkgs, keywords)

    # ---- console summary ---------------------------------------------------------
    print(f"\n{len(pkgs)} packages ({sum(p.is_new for p in pkgs)} new). Report: {report}\n")
    for p in pkgs:
        flag = "NEW " if p.is_new else "    "
        print(f"{flag}{p.registry:<9} {p.name} {p.version}")
        print(f"          page:     {p.page_url}")
        if p.download_url:
            print(f"          download: {p.download_url}")
        if p.local_file:
            print(f"          local:    {out / p.local_file}")
        if p.vt_result:
            print(f"          VT:       {p.vt_result}  {p.vt_link}")
        if p.error:
            print(f"          error:    {p.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
