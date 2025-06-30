#!/usr/bin/env python3
import sys
import requests
from bs4 import BeautifulSoup
from colorama import init, Fore, Style

# Common browser User-Agent string
BROWSER_USER_AGENT = (
    "1"
    "2"
    "3"
)

def check_url(url, timeout=5):
    """
    Attempts to fetch `url` using a browser User-Agent.
    Returns (reachable: bool, title: str|None).
    """
    headers = {"User-Agent": BROWSER_USER_AGENT}
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        # Treat any 2xx or 3xx status as reachable
        if resp.status_code < 400:
            soup = BeautifulSoup(resp.text, 'html.parser')
            title_tag = soup.title
            title = title_tag.string.strip() if title_tag and title_tag.string else 'No title found'
            return True, title
        else:
            return False, None
    except requests.RequestException:
        return False, None

def main(filepath):
    init(autoreset=True)  # initialize colorama

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue

                # Split off the last two colon-separated fields
                try:
                    url, _, _ = line.rsplit(':', 2)
                except ValueError:
                    print(f"{Fore.YELLOW}[SKIP]{Style.RESET_ALL} Line {lineno}: unexpected format: {line}")
                    continue

                url = url.strip()
                if not (url.startswith('http://') or url.startswith('https://')):
                    print(f"{Fore.YELLOW}[SKIP]{Style.RESET_ALL} Line {lineno}: invalid or missing scheme: {url}")
                    continue

                reachable, title = check_url(url)
                if reachable:
                    print(f"{Fore.GREEN}[REACHABLE]{Style.RESET_ALL} {url} — “{title}” - {line}")
                else:
                    pass
                    #print(f"{Fore.RED}[UNREACHABLE]{Style.RESET_ALL} {url}")
    except FileNotFoundError:
        print(f"{Fore.RED}Error:{Style.RESET_ALL} File not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}Unexpected error:{Style.RESET_ALL} {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python check_urls.py <path_to_input_file>")
        sys.exit(1)
    main(sys.argv[1])
