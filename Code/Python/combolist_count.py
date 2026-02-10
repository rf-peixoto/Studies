#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter
from urllib.parse import urlsplit

# ---------------------------
# Configuration
# ---------------------------

# Known 2-level public suffixes (extend if needed)
PUBLIC_SUFFIX_2L = {
    "com.br", "net.br", "org.br", "gov.br",
    "co.uk", "org.uk", "ac.uk",
}

TRAILING_PUNCT = ".,;:!?)\"]}'"

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"
    r"(?![A-Za-z0-9._%+-])"
)

SCHEME_URL_RE = re.compile(r"\bhttps?://[^\s<>'\"()]+", re.IGNORECASE)

BARE_FQDN_RE = re.compile(
    r"(?<!@)\b"
    r"((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})"
    r"(?::\d{1,5})?"
    r"(?:/[^\s<>'\"()]*)?"
    r"\b(?!@)",
    re.IGNORECASE
)


def is_valid_registrable_domain(domain: str) -> bool:
    """
    Rejects public suffixes like:
      - com
      - br
      - com.br
    Requires at least one label left of the public suffix.
    """
    labels = domain.lower().split(".")
    if len(labels) < 2:
        return False

    suffix_2l = ".".join(labels[-2:])
    if suffix_2l in PUBLIC_SUFFIX_2L:
        return len(labels) >= 3

    # Default rule: at least domain.tld
    return len(labels) >= 2


def normalize_fqdn(value: str) -> str | None:
    value = value.strip().strip(TRAILING_PUNCT)
    if not value:
        return None

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "http://" + value

    try:
        parts = urlsplit(value)
    except Exception:
        return None

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if not is_valid_registrable_domain(host):
        return None

    return host


def write_csv(counter: Counter, path: str, h1: str, h2: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([h1, h2])
        for k, v in counter.most_common():
            w.writerow([k, v])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out-prefix", default="report")
    args = ap.parse_args()

    email_domains = Counter()
    fqdn_counts = Counter()

    for path in args.files:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Emails
                for domain in EMAIL_RE.findall(line):
                    domain = domain.lower()
                    if is_valid_registrable_domain(domain):
                        email_domains[domain] += 1

                # URLs with scheme
                for url in SCHEME_URL_RE.findall(line):
                    fqdn = normalize_fqdn(url)
                    if fqdn:
                        fqdn_counts[fqdn] += 1

                # Bare FQDNs
                for raw in BARE_FQDN_RE.findall(line):
                    fqdn = normalize_fqdn(raw)
                    if fqdn:
                        fqdn_counts[fqdn] += 1

    write_csv(email_domains, f"{args.out_prefix}_email_domains.csv", "email_domain", "count")
    write_csv(fqdn_counts, f"{args.out_prefix}_url_fqdns.csv", "fqdn", "count")

    print("Done.")
    print("Email domains (top 10):")
    for k, v in email_domains.most_common(10):
        print(f"  {k}: {v}")

    print("URL FQDNs (top 10):")
    for k, v in fqdn_counts.most_common(10):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
