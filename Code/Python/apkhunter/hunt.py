#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT = 20
DEFAULT_DELAY = 3.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) "
    "Gecko/20100101 Firefox/156.0",

    "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) "
    "Gecko/20100101 Firefox/156.0",
]


@dataclass
class Finding:
    app: str
    package: str
    query: str
    url: str
    domain: str
    title: str = ""
    source_name: str = ""
    source_type: str = ""
    category: str = ""
    score: int = 0
    http_status: int | None = None
    notes: str = ""


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def load_apps(path: Path) -> list[dict]:
    data = load_json(path)

    apps = []

    for app in data.get("apps", []):
        if not app.get("enabled", True):
            continue

        if not app.get("name"):
            raise ValueError("Application without name")

        if not app.get("package"):
            raise ValueError(
                f"Application {app['name']} has no package"
            )

        app.setdefault("aliases", [])
        app.setdefault("official_domains", [])
        app.setdefault("known_versions", [])

        if app["name"] not in app["aliases"]:
            app["aliases"].insert(0, app["name"])

        apps.append(app)

    return apps


def load_sources(path: Path) -> list[dict]:
    data = load_json(path)

    sources = []

    for source in data.get("sources", []):
        if not source.get("enabled", True):
            continue

        source.setdefault("domains", [])
        source.setdefault("type", "unknown")
        source.setdefault("status", "unknown")

        sources.append(source)

    return sources


def unique(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []

    for value in values:
        value = value.strip()

        if not value or value in seen:
            continue

        seen.add(value)
        output.append(value)

    return output


def normalize_domain(domain: str) -> str:
    domain = domain.lower().strip()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def get_domain(url: str) -> str:
    try:
        return normalize_domain(urlparse(url).netloc)
    except Exception:
        return ""


def domain_matches(domain: str, candidate: str) -> bool:
    domain = normalize_domain(domain)
    candidate = normalize_domain(candidate)

    return (
        domain == candidate
        or domain.endswith("." + candidate)
    )


def find_source(domain: str, sources: list[dict]) -> dict | None:
    for source in sources:
        for candidate in source["domains"]:
            if domain_matches(domain, candidate):
                return source

    return None


def official_exclusions(app: dict) -> str:
    exclusions = [
        "-site:play.google.com",
        "-site:apps.apple.com",
    ]

    for domain in app["official_domains"]:
        exclusions.append(f"-site:{domain}")

    return " ".join(exclusions)


def generate_base_dorks(app: dict) -> list[str]:
    package = app["package"]

    return [
        f'"{package}" APK',
        f'"{package}" XAPK',
        f'"{package}" APKS',

        f'"{package}" "Download APK"',
        f'"{package}" "Baixar APK"',
        f'"{package}" "APK Download"',
        f'"{package}" "Download XAPK"',

        f'"{package}" "Old Versions"',
        f'"{package}" "Older Versions"',
        f'"{package}" "Previous Versions"',
        f'"{package}" "All Versions"',
        f'"{package}" "Version History"',
        f'"{package}" "Versões Antigas"',

        f'"{package}" SHA256',
        f'"{package}" "SHA-256"',
        f'"{package}" SHA1',
        f'"{package}" "SHA-1"',
        f'"{package}" MD5',

        f'"{package}" "Package Name"',
        f'"{package}" "Package name:"',
        f'"{package}" "Nome do pacote"',
        f'"{package}" "File Size"',
        f'"{package}" "APK size"',
        f'"{package}" "Requires Android"',
        f'"{package}" Architecture',
        f'"{package}" "Screen DPI"',

        f'"{package}" "Base APK"',
        f'"{package}" "Split APK"',
        f'"{package}" "Split APKs"',
        f'"{package}" OBB',

        f'intitle:APK "{package}"',
        f'intitle:"Download" "{package}"',
        f'inurl:apk "{package}"',
        f'inurl:download "{package}"',
        f'inurl:android "{package}"',

        f'intitle:"index of" "{package}"',
        f'intitle:"index of" "{package}" apk',

        f'"{package}.apk"',
        f'"{package}.xapk"',
        f'"{package}.apks"',
    ]


def generate_alias_dorks(app: dict) -> list[str]:
    exclusions = official_exclusions(app)

    dorks = []

    for alias in app["aliases"]:
        dorks.extend([
            f'"{alias}" APK {exclusions}',
            f'"{alias}" XAPK {exclusions}',
            f'"{alias}" APKS {exclusions}',

            f'"{alias}" "Download APK" {exclusions}',
            f'"{alias}" "Baixar APK" {exclusions}',
            f'"{alias}" "APK Download" {exclusions}',
            f'"{alias}" "Download XAPK" {exclusions}',

            f'"{alias}" "Old Versions" {exclusions}',
            f'"{alias}" "Versões Antigas" {exclusions}',

            f'"{alias}" SHA256 APK {exclusions}',
            f'"{alias}" "Package Name" APK {exclusions}',
        ])

    return dorks


def generate_version_dorks(app: dict) -> list[str]:
    dorks = []

    for version in app["known_versions"]:
        for alias in app["aliases"]:
            dorks.extend([
                f'"{alias}" "{version}" APK',
                f'"{alias}" "{version}" XAPK',
                f'"{alias}" "{version}" "Download APK"',
                f'"{alias}" "{version}" "Baixar APK"',
            ])

        dorks.extend([
            f'"{app["package"]}" "{version}"',
            f'"{app["package"]}" "{version}" APK',
        ])

    return dorks


def generate_marketplace_dorks(
    app: dict,
    sources: list[dict],
) -> list[str]:

    package = app["package"]

    dorks = []

    for source in sources:
        for domain in source["domains"]:

            dorks.extend([
                f'site:{domain} "{package}"',
                f'site:{domain} "{package}" APK',
                f'site:{domain} "{package}" XAPK',
                f'site:{domain} "{package}" APKS',
                f'site:{domain} "{package}" "Download APK"',
            ])

            for alias in app["aliases"]:
                dorks.extend([
                    f'site:{domain} "{alias}"',
                    f'site:{domain} "{alias}" APK',
                    f'site:{domain} "{alias}" "Download APK"',
                ])

    return dorks


def generate_filehost_dorks(
    app: dict,
    sources: list[dict],
) -> list[str]:

    dorks = []

    file_hosts = [
        source
        for source in sources
        if source["type"] == "file_host"
    ]

    for source in file_hosts:
        for domain in source["domains"]:

            package = app["package"]

            dorks.extend([
                f'site:{domain} "{package}"',
                f'site:{domain} "{package}.apk"',
                f'site:{domain} "{package}.xapk"',
            ])

            for alias in app["aliases"]:
                dorks.extend([
                    f'site:{domain} "{alias}" APK',
                    f'site:{domain} "{alias}.apk"',
                ])

    return dorks


def generate_seo_poisoning_dorks(app: dict) -> list[str]:
    package = app["package"]
    exclusions = official_exclusions(app)

    dorks = []

    institutional_domains = [
        "gov.br",
        "edu.br",
        "org.br",
        "gov",
        "edu",
    ]

    for alias in app["aliases"]:

        dorks.extend([
            f'"{alias}" "Baixar APK - Aplicativo Android"',
            f'"{alias}" "Download APK - Android App"',
            f'"{alias}" "APK Download for Android"',
            f'"{alias}" "Baixar APK" {exclusions}',
            f'"{alias}" "Download APK" {exclusions}',
        ])

        for domain in institutional_domains:

            dorks.extend([
                f'site:{domain} "{alias}" APK',
                f'site:{domain} "{alias}" XAPK',
                f'site:{domain} "{alias}" "Baixar APK"',
                f'site:{domain} "{alias}" "Download APK"',
            ])

    for domain in institutional_domains:

        dorks.extend([
            f'site:{domain} "{package}"',
            f'site:{domain} "{package}" APK',
            f'site:{domain} "{package}" XAPK',
        ])

    dorks.extend([
        f'"{package}" "Baixar APK - Aplicativo Android"',
        f'"{package}" "Download APK - Android App"',
        f'"{package}" "APK Download for Android"',
        f'"{package}" "SHA256:"',
    ])

    return dorks


def generate_generic_marketplace_dorks() -> list[str]:
    return [
        '"Package Name" "Download APK" "Android OS" "File Size"',
        '"Nome do pacote" "Baixar APK" "Versões Antigas"',
        '"Package Name" "Old Versions" "Download APK"',
        '"APK Information" "File Size" "Package Name"',
        '"Download XAPK" "Architecture" "Screen DPI"',
        '"Base APK" "Split APKs" "Download XAPK"',
        '"SHA1" "Requires Android" "Download APK"',
        '"APK OBB XAPK" "Package"',

        'inurl:/apps/ intitle:"Baixar" APK',
        'inurl:/android/ intitle:APK Download',
        'inurl:/download/ "Package Name" APK',
        'inurl:/apk/ "Old Versions"',
        'inurl:/apk-download/ Android',

        'intitle:"APK Download for Android"',
        'intitle:"Baixar APK" "Nome do Pacote"',

        '"Baixar APK" "Como instalar arquivos XAPK"',
        '"Download APK" "Package name:" "SHA256:"',

        '"APK Information" "Android OS" "File Size"',
        '"Baixar APK" "Android OS" "Tamanho do arquivo"',
        '"Download APK" Version Package Developer',
    ]


def generate_generic_seo_dorks() -> list[str]:
    return [
        '"Baixar APK - Aplicativo Android"',
        '"Download APK - Android App"',
        '"APK Download for Android"',

        '"Baixar APK" "Android OS" "Tamanho do arquivo"',
        '"Download APK" "SHA256:" "Package name:"',

        'site:gov.br "Baixar APK"',
        'site:edu.br "Baixar APK"',
        'site:org.br "Baixar APK"',

        'site:gov.br "Download APK"',
        'site:edu.br "Download APK"',

        'site:gov.br XAPK',
        'site:edu.br XAPK',

        'site:gov.br intitle:APK',
        'site:edu.br intitle:APK',

        'site:gov.br inurl:apk',
        'site:edu.br inurl:apk',

        '"Baixar APK - Aplicativo Android Produtividade"',
        '"Baixar APK - Aplicativo Android Ferramentas"',
        '"Baixar APK - Aplicativo Android Entretenimento"',
    ]


def generate_all_dorks(
    apps: list[dict],
    sources: list[dict],
) -> dict[str, list[str]]:

    result = {}

    for app in apps:

        queries = []

        queries += generate_base_dorks(app)
        queries += generate_alias_dorks(app)
        queries += generate_version_dorks(app)
        queries += generate_marketplace_dorks(app, sources)
        queries += generate_filehost_dorks(app, sources)
        queries += generate_seo_poisoning_dorks(app)

        result[app["name"]] = unique(queries)

    result["_MARKETPLACE_DISCOVERY_"] = (
        generate_generic_marketplace_dorks()
    )

    result["_SEO_POISONING_DISCOVERY_"] = (
        generate_generic_seo_dorks()
    )

    return result


def google_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def bing_url(query: str) -> str:
    return "https://www.bing.com/search?q=" + quote_plus(query)


def ddg_url(query: str) -> str:
    return "https://duckduckgo.com/?q=" + quote_plus(query)


def decode_ddg_redirect(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url

    parsed = urlparse(url)

    if "duckduckgo.com" in parsed.netloc:
        args = parse_qs(parsed.query)

        if "uddg" in args:
            return unquote(args["uddg"][0])

    return url


class SearchClient:

    def __init__(
        self,
        timeout: int,
        delay: float,
    ):

        self.timeout = timeout
        self.delay = delay

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        })

    def wait(self):
        time.sleep(
            self.delay + random.uniform(0.2, 0.8)
        )

    def search_ddg(
        self,
        query: str,
        max_results: int,
    ) -> list[tuple[str, str]]:

        try:
            response = self.session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                timeout=self.timeout,
            )

            self.wait()

        except requests.RequestException:
            return []

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        results = []

        for result in soup.select(".result"):

            anchor = result.select_one(".result__a")

            if not anchor:
                continue

            title = anchor.get_text(
                " ",
                strip=True,
            )

            url = decode_ddg_redirect(
                anchor.get("href", "")
            )

            if not url.startswith(
                ("http://", "https://")
            ):
                continue

            results.append(
                (title, url)
            )

            if len(results) >= max_results:
                break

        return results


def classify(
    app: dict,
    url: str,
    title: str,
    sources: list[dict],
) -> tuple[str, int, str, str]:

    domain = get_domain(url)

    haystack = (
        f"{url} {title}"
    ).lower()

    score = 0
    notes = []

    source = find_source(
        domain,
        sources,
    )

    source_type = ""

    if source:
        source_type = source["type"]

        score += 30

        notes.append(
            f"known source: {source['name']}"
        )

    if app["package"].lower() in haystack:
        score += 40
        notes.append("package match")

    if any(
        alias.lower() in haystack
        for alias in app["aliases"]
    ):
        score += 15
        notes.append("name match")

    if any(
        keyword in haystack
        for keyword in (
            "apk",
            "xapk",
            "apks",
            "download",
            "baixar",
        )
    ):
        score += 10

    institutional = (
        ".gov.br",
        ".edu.br",
        ".gov.",
        ".edu.",
    )

    if any(x in domain for x in institutional):
        score += 30
        category = "possible_seo_poisoning"

    elif source_type == "file_host":
        category = "file_host_exposure"

    elif source_type in (
        "apk_marketplace",
        "apk_downloader",
        "mod_marketplace",
        "official_alternative_store",
    ):
        category = "alternative_distribution"

    elif source_type == "metadata":
        category = "metadata_only"

    elif "apk" in haystack or "xapk" in haystack:
        category = "possible_apk_distribution"

    else:
        category = "unclassified"

    for official_domain in app["official_domains"]:
        if domain_matches(domain, official_domain):
            score -= 50
            notes.append("official domain")

    return (
        category,
        max(score, 0),
        "; ".join(notes),
        source_type,
    )


def canonical_url(url: str) -> str:
    parsed = urlparse(url)

    domain = normalize_domain(
        parsed.netloc
    )

    path = re.sub(
        r"/+",
        "/",
        parsed.path,
    ).rstrip("/")

    return f"https://{domain}{path}"


def deduplicate(
    findings: list[Finding],
) -> list[Finding]:

    best = {}

    for finding in findings:

        key = canonical_url(
            finding.url
        )

        previous = best.get(key)

        if (
            previous is None
            or finding.score > previous.score
        ):
            best[key] = finding

    return sorted(
        best.values(),
        key=lambda x: (
            -x.score,
            x.app.lower(),
            x.domain,
        ),
    )


def write_dorks(
    dorks: dict[str, list[str]],
    path: Path,
):

    with path.open(
        "w",
        encoding="utf-8",
    ) as fp:

        for section, queries in dorks.items():

            fp.write(
                f"\n{'=' * 78}\n"
                f"{section}\n"
                f"{'=' * 78}\n\n"
            )

            for query in queries:
                fp.write(query + "\n")


def write_search_urls(
    queries: list[str],
    output_dir: Path,
):

    generators = {
        "google_searches.txt": google_url,
        "bing_searches.txt": bing_url,
        "duckduckgo_searches.txt": ddg_url,
    }

    for filename, generator in generators.items():

        with (
            output_dir / filename
        ).open("w", encoding="utf-8") as fp:

            for query in queries:
                fp.write(
                    generator(query) + "\n"
                )


def export_findings(
    findings: list[Finding],
    output_dir: Path,
):

    with (
        output_dir / "findings.json"
    ).open("w", encoding="utf-8") as fp:

        json.dump(
            [asdict(x) for x in findings],
            fp,
            indent=2,
            ensure_ascii=False,
        )

    with (
        output_dir / "findings.csv"
    ).open(
        "w",
        encoding="utf-8",
        newline="",
    ) as fp:

        fields = list(
            Finding.__dataclass_fields__.keys()
        )

        writer = csv.DictWriter(
            fp,
            fieldnames=fields,
        )

        writer.writeheader()

        for finding in findings:
            writer.writerow(
                asdict(finding)
            )


def check_sources(
    sources: list[dict],
    client: SearchClient,
):

    print("\nSOURCE AVAILABILITY\n")

    for source in sources:

        for domain in source["domains"]:

            url = f"https://{domain}"

            try:
                response = client.session.get(
                    url,
                    timeout=client.timeout,
                    allow_redirects=True,
                )

                print(
                    f"{response.status_code:3d} "
                    f"{domain:35s} -> "
                    f"{response.url}"
                )

            except requests.RequestException as exc:

                print(
                    f"ERR {domain:35s} "
                    f"{type(exc).__name__}"
                )

            client.wait()


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apps",
        type=Path,
        default=Path("apps.json"),
    )

    parser.add_argument(
        "--marketplaces",
        type=Path,
        default=Path("marketplaces.json"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
    )

    parser.add_argument(
        "--generate-only",
        action="store_true",
    )

    parser.add_argument(
        "--check-marketplaces",
        action="store_true",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
    )

    return parser.parse_args()


def main():

    args = parse_args()

    apps = load_apps(args.apps)
    sources = load_sources(args.marketplaces)

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"[+] Loaded {len(apps)} applications"
    )

    print(
        f"[+] Loaded {len(sources)} enabled sources"
    )

    dork_map = generate_all_dorks(
        apps,
        sources,
    )

    write_dorks(
        dork_map,
        args.output / "dorks.txt",
    )

    all_queries = unique(
        query
        for queries in dork_map.values()
        for query in queries
    )

    write_search_urls(
        all_queries,
        args.output,
    )

    print(
        f"[+] Generated {len(all_queries)} unique queries"
    )

    client = SearchClient(
        timeout=args.timeout,
        delay=args.delay,
    )

    if args.check_marketplaces:
        check_sources(
            sources,
            client,
        )

    if args.generate_only:
        return

    findings = []

    query_count = 0

    app_lookup = {
        app["name"]: app
        for app in apps
    }

    for app_name, queries in dork_map.items():

        if app_name.startswith("_"):
            continue

        app = app_lookup[app_name]

        for query in queries:

            if (
                args.max_queries is not None
                and query_count >= args.max_queries
            ):
                break

            query_count += 1

            print(
                f"[{query_count}] "
                f"{app_name}: {query}"
            )

            results = client.search_ddg(
                query,
                args.max_results,
            )

            for title, url in results:

                category, score, notes, source_type = (
                    classify(
                        app,
                        url,
                        title,
                        sources,
                    )
                )

                source = find_source(
                    get_domain(url),
                    sources,
                )

                findings.append(
                    Finding(
                        app=app["name"],
                        package=app["package"],
                        query=query,
                        url=url,
                        domain=get_domain(url),
                        title=title,
                        source_name=(
                            source["name"]
                            if source
                            else ""
                        ),
                        source_type=source_type,
                        category=category,
                        score=score,
                        notes=notes,
                    )
                )

    findings = deduplicate(
        findings
    )

    export_findings(
        findings,
        args.output,
    )

    print()
    print(
        f"[+] Findings: {len(findings)}"
    )

    print(
        f"[+] Output: {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
