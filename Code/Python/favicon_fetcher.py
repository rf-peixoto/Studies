#!/usr/bin/env python3
"""
pip install requests mmh3

"""


import argparse
import base64
import hashlib
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

try:
    import mmh3
except ImportError as e:
    raise SystemExit(
        "Dependência ausente: mmh3\n"
        "Instale com: pip install mmh3 requests colorama"
    ) from e


# -------------------- Cor / UX --------------------

def _supports_color() -> bool:
    return sys.stdout.isatty()

class C:
    # ANSI fallback; se colorama existir, ele normaliza no Windows.
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

def colorize(enabled: bool):
    if not enabled:
        # desativa cores
        for k in dir(C):
            if k.isupper():
                setattr(C, k, "")
        return

    # tenta habilitar colorama (melhora no Windows)
    try:
        import colorama  # type: ignore
        colorama.just_fix_windows_console()
    except Exception:
        pass


# -------------------- HTML parsing --------------------

class FaviconLinkParser(HTMLParser):
    """
    Parser mínimo para localizar <link rel="...icon..."> href.
    Coleta candidatos e escolhe por prioridade (heurística).
    """
    def __init__(self):
        super().__init__()
        self.candidates: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        rel = attr.get("rel", "").lower()
        href = attr.get("href", "").strip()
        if not href:
            return
        if "icon" in rel:
            priority = 50
            if rel.strip() == "icon":
                priority = 10
            elif "shortcut icon" in rel:
                priority = 15
            elif "apple-touch-icon" in rel:
                priority = 30
            self.candidates.append((priority, href))


# -------------------- Lógica principal --------------------

def normalize_target(target: str) -> str:
    target = target.strip()
    if not target:
        raise ValueError("Alvo vazio.")

    if "://" in target:
        u = urlparse(target)
        if not u.netloc:
            raise ValueError(f"URL inválida: {target}")
        return u.netloc

    # permite "dominio.tld/path" sem esquema
    u = urlparse("https://" + target)
    if not u.netloc:
        raise ValueError(f"Domínio inválido: {target}")
    return u.netloc


def fetch_url(session: requests.Session, url: str, timeout: int = 12) -> requests.Response:
    return session.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": "favicon-hunt-queries/1.1"},
    )


def discover_favicon_url(session: requests.Session, base_url: str) -> str:
    """
    Tenta descobrir o favicon via HTML; se falhar, cai para /favicon.ico.
    """
    try:
        r = fetch_url(session, base_url)
        r.raise_for_status()
        html = r.text or ""
    except Exception:
        return urljoin(base_url, "/favicon.ico")

    parser = FaviconLinkParser()
    try:
        parser.feed(html)
    except Exception:
        return urljoin(r.url, "/favicon.ico")

    if parser.candidates:
        parser.candidates.sort(key=lambda x: x[0])
        best_href = parser.candidates[0][1]
        return urljoin(r.url, best_href)

    return urljoin(r.url, "/favicon.ico")


def get_favicon_bytes(session: requests.Session, favicon_url: str) -> bytes:
    r = fetch_url(session, favicon_url)
    r.raise_for_status()
    return r.content


def mmh3_shodan(favicon_bytes: bytes) -> int:
    # Shodan: base64 SEM \n
    b64 = base64.b64encode(favicon_bytes)
    return mmh3.hash(b64)


def mmh3_fofa(favicon_bytes: bytes) -> int:
    # FOFA: base64 COM \n (encodebytes insere quebras a cada 76 chars)
    b64 = base64.encodebytes(favicon_bytes)
    return mmh3.hash(b64)


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def print_block(title: str, lines: list[str]):
    print(f"{C.BOLD}{C.CYAN}{title}{C.RESET}")
    for ln in lines:
        print(f"  {ln}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="Domínio (ex: example.com) ou URL completa")
    ap.add_argument("--no-color", action="store_true", help="Desabilitar saída colorida")
    args = ap.parse_args()

    color_enabled = _supports_color() and not args.no_color
    colorize(color_enabled)

    try:
        netloc = normalize_target(args.target)
    except ValueError as e:
        print(f"{C.RED}Erro:{C.RESET} {e}", file=sys.stderr)
        return 2

    session = requests.Session()

    # Tenta HTTPS primeiro, depois HTTP.
    base_urls = [f"https://{netloc}/", f"http://{netloc}/"]

    last_err: Exception | None = None

    for base in base_urls:
        try:
            favicon_url = discover_favicon_url(session, base)
            fav = get_favicon_bytes(session, favicon_url)

            sh_hash = mmh3_shodan(fav)
            fo_hash = mmh3_fofa(fav)
            md5v = md5_hex(fav)
            sha256v = sha256_hex(fav)

            print(f"{C.BOLD}{C.GREEN}Alvo:{C.RESET} {netloc}")
            print(f"{C.BOLD}{C.GREEN}Favicon:{C.RESET} {favicon_url}")
            print()

            print_block("Hashes calculados", [
                f"{C.BOLD}Shodan mmh3{C.RESET}: {sh_hash}",
                f"{C.BOLD}FOFA  mmh3{C.RESET}: {fo_hash}",
                f"{C.BOLD}MD5{C.RESET}:        {md5v}",
                f"{C.BOLD}SHA256{C.RESET}:     {sha256v}",
            ])

            print_block("Consultas prontas para colar", [
                f"{C.BOLD}Shodan{C.RESET}:      http.favicon.hash:{sh_hash}",
                f"{C.BOLD}FOFA{C.RESET}:        icon_hash=\"{fo_hash}\"",
                f"{C.BOLD}ZoomEye{C.RESET}:     iconhash:{sh_hash}     {C.DIM}# mmh3 (decimal){C.RESET}",
                f"{C.BOLD}ZoomEye{C.RESET}:     iconhash:{md5v} {C.DIM}# md5 (hex) — também aceito{C.RESET}",
                f"{C.BOLD}Censys{C.RESET}:      services.http.response.favicons.shodan_hash={sh_hash}",
                f"{C.BOLD}Censys{C.RESET}:      services.http.response.favicons.md5_hash=\"{md5v}\"",
                f"{C.BOLD}BinaryEdge{C.RESET}:  web.favicon.mmh3:\"{sh_hash}\"",
                f"{C.BOLD}BinaryEdge{C.RESET}:  web.favicon.md5:\"{md5v}\"",
            ])

            print(f"{C.DIM}Observação:{C.RESET} Shodan e FOFA diferem no hashing por causa das quebras de linha no base64.")
            return 0

        except Exception as e:
            last_err = e

    print(f"{C.RED}Falha ao obter o favicon de {netloc}:{C.RESET} {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
