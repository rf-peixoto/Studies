# VIBECODING ALERT!!!!
# Tested on win
# pip install --upgrade selenium webdriver-manager

import argparse
import datetime as dt
import json
import os
import sys
import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def parse_args():
    p = argparse.ArgumentParser(description="Busca recente no X via Selenium + cookies.json (Chrome export).")
    p.add_argument("--cookies", required=True, help="Caminho para cookies.json exportado do navegador.")
    p.add_argument("--query", required=True, help="Consulta base (sem since/until; o script adiciona).")
    p.add_argument("--days", type=int, default=7, help="Dias para trás (padrão: 7).")
    p.add_argument("--max-tweets", type=int, default=50, help="Quantidade máxima a coletar (padrão: 50).")
    p.add_argument("--output", default="tweets.jsonl", help="Arquivo de saída JSONL (padrão: tweets.jsonl).")
    p.add_argument("--headless", action="store_true", help="Rodar headless (menos confiável no X).")
    return p.parse_args()


def make_driver(headless: bool) -> webdriver.Firefox:
    opts = FirefoxOptions()
    if headless:
        opts.add_argument("--headless")
    driver = webdriver.Firefox(options=opts)
    driver.set_window_size(1280, 900)
    return driver


def load_cookies(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("cookies.json deve ser uma lista de cookies (export tipo Chrome).")
    return data


def normalize_cookie_for_selenium(c: dict) -> dict | None:
    """
    Converte cookie exportado (Chrome-like) para o formato que Selenium aceita.
    - expirationDate -> expiry
    - remove campos não suportados
    - ajusta domain (.x.com -> x.com) quando necessário
    """
    required = {"name", "value", "domain", "path"}
    if not required.issubset(set(c.keys())):
        return None

    out = {
        "name": c["name"],
        "value": c["value"],
        "domain": c["domain"],
        "path": c.get("path", "/"),
    }

    # Selenium: "expiry" (int, epoch seconds)
    if "expirationDate" in c and c["expirationDate"] is not None:
        try:
            out["expiry"] = int(float(c["expirationDate"]))
        except Exception:
            pass

    # Flags comuns
    if "secure" in c:
        out["secure"] = bool(c["secure"])
    if "httpOnly" in c:
        out["httpOnly"] = bool(c["httpOnly"])


    if isinstance(out["domain"], str) and out["domain"].startswith("."):
        out["domain"] = out["domain"][1:]

    return out


def add_cookies(driver: webdriver.Firefox, cookies_path: str):
    cookies_raw = load_cookies(cookies_path)
    cookies = [normalize_cookie_for_selenium(c) for c in cookies_raw]
    cookies = [c for c in cookies if c is not None]

    driver.get("https://x.com/")
    time.sleep(2)

    driver.delete_all_cookies()

    added = 0
    for c in cookies:
        dom = c.get("domain", "")
        if dom.endswith("x.com"):
            try:
                driver.add_cookie(c)
                added += 1
            except Exception:
                pass

    driver.get("https://x.com/home")
    time.sleep(3)
    return added


def is_logged_in(driver: webdriver.Firefox) -> bool:
    url = driver.current_url
    if "login" in url or "i/flow/login" in url:
        return False
    # Heurísticas simples:
    try:
        driver.find_element(By.CSS_SELECTOR, 'a[href="/home"], a[aria-label="Home"]')
        return True
    except Exception:
        pass
    try:
        driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Search query"], input[placeholder*="Search"]')
        return True
    except Exception:
        pass
    return False


def build_query(base_query: str, since_date: dt.date, until_date: dt.date) -> str:
    # Até onde dá para ser “determinístico” na busca:
    # - f=live para "Latest"
    # - lang:pt para português
    # - since/until (until é exclusivo)
    return f"({base_query}) lang:pt since:{since_date.isoformat()} until:{until_date.isoformat()}"


def extract_tweets(driver: webdriver.Firefox):
    tweets = []
    articles = driver.find_elements(By.CSS_SELECTOR, "article")
    for a in articles:
        try:
            time_el = a.find_element(By.CSS_SELECTOR, "time")
            dt_str = time_el.get_attribute("datetime")
            if not dt_str:
                continue

            # Link do tweet
            link = None
            for l in a.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
                href = l.get_attribute("href")
                if href and "/status/" in href:
                    link = href.split("?")[0]
                    break
            if not link:
                continue

            # Texto
            text = ""
            try:
                text = a.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text.strip()
            except Exception:
                text = a.text.strip()

            # Handle
            handle = None
            for l in a.find_elements(By.CSS_SELECTOR, 'a[href^="https://x.com/"], a[href^="/"]')[:12]:
                t = (l.text or "").strip()
                if t.startswith("@") and len(t) > 1:
                    handle = t
                    break

            tweets.append({
                "url": link,
                "datetime": dt_str,
                "handle": handle,
                "text": text,
            })
        except Exception:
            continue
    return tweets


def main():
    args = parse_args()
    driver = make_driver(args.headless)

    try:
        added = add_cookies(driver, args.cookies)
        print(f"[i] Cookies adicionados (tentativas bem-sucedidas): {added}")

        if not is_logged_in(driver):
            print(
                "[!] Ainda parece não estar logado após injetar cookies.\n"
                "    Possíveis causas:\n"
                "    - cookies expirados/invalidos (especialmente auth_token)\n"
                "    - X exigindo verificação adicional\n"
                "    - export incompleto (faltando cookies críticos)\n"
                "    Reexporte os cookies após logar no x.com e tente novamente.",
                file=sys.stderr
            )
            # Mesmo assim tentaremos a busca; às vezes funciona parcialmente.
            time.sleep(2)

        today = dt.datetime.now(dt.timezone.utc).date()
        since = today - dt.timedelta(days=args.days)
        until = today + dt.timedelta(days=1)

        q = build_query(args.query, since, until)
        search_url = f"https://x.com/search?q={quote_plus(q)}&f=live"
        driver.get(search_url)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article")))
        collected = {}
        stagnant = 0

        while len(collected) < args.max_tweets and stagnant < 6:
            before = len(collected)

            for t in extract_tweets(driver):
                u = t["url"]
                if u not in collected:
                    collected[u] = t

            if len(collected) == before:
                stagnant += 1
            else:
                stagnant = 0

            driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.8);")
            time.sleep(2)

        with open(args.output, "w", encoding="utf-8") as f:
            for t in collected.values():
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        print(f"[ok] Coletados {len(collected)} tweets (mais recentes) em PT. Salvo em {args.output}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
