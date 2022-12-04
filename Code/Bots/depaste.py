from time import sleep
import requests
import re

# -------------------------------------------------------------- #
# SETUP
# -------------------------------------------------------------- #
# Delay from updates in seconds:
DELAY = 15

# URLs:
main = "https://pastebin.com/archive"
raw = "https://pastebin.com/raw/"

# -------------------------------------------------------------- #
# PATTERNS
# -------------------------------------------------------------- #
patterns = [
    '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}',  # Emails
    '^(((([a-z,1-9]+)|[0-9,A-Z]+))([^a-z\.]))*',    # MD5, SHA1, SHA256, SHA512
    '^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',            # Bitcoin Wallet
    'bc1[a-z0-9]{39,59}',                           # Bitcoin Segwit
    '[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}',          # Monero (XMR) Wallet
    '0x[a-fA-F0-9]{40}',                            # Ether(eum) (ETH) Wallet
    'basic [a-zA-Z0-9_\\-:\\.=]+',                  # Auth Basic
    'bearer [a-zA-Z0-9_\\-\\.=]+',                  # Auth Bearer
    '(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}', # AWS Client ID
    'amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', # AWS MWS Key
    '(?i)aws(.{0,20})?(?-i)[\'\"][0-9a-zA-Z\/+]{40}[\'\"]', # AWS Secret Key
    'AIza[0-9A-Za-z\\-_]{35}',                      # Google API Key
    '(?i)(google|gcp|youtube|drive|yt)(.{0,20})?[\'\"][AIza[0-9a-z\\-_]{35}][\'\"]', # Google Cloud * API
    'AIza[0-9A-Za-z\\-_]{35}',                      # Google Drive API Key
    'AIza[0-9A-Za-z\\-_]{35}',                      # Gmail API Key
    '(?i)linkedin(.{0,20})?[\'\"][0-9a-z]{16}[\'\"]',   # LinkedIn API Key:
]

# -------------------------------------------------------------- #
# METHODS
# -------------------------------------------------------------- #
# Get url:
def get_url(url: str) -> str:
    return requests.get(url).text

# Extract links:
def extract_links(content: str) -> list:
    tmp = []
    links = re.findall('href=\"\/[A-Za-z0-9]{8}\"', content)
    for l in links:
        tmp.append(l.split('=\"/')[-1][:-1])
    return tmp

# Get raw data from paste:
def get_raw(url: str, token: str) -> str:
    return requests.get(url + token).text

# Save data:
def save_data(filename: str, data: str):
    with open(filename, "w") as fl:
        fl.write(data)
    print("[+] Data saved as {0}.txt".format(tk))


# -------------------------------------------------------------- #
# SCRAPY
# -------------------------------------------------------------- #
print("________        __________                  __          ")
print("\______ \   ____\______   \_____    _______/  |_  ____  ")
print(" |    |  \_/ __ \|     ___/\__  \  /  ___/\   __\/ __ \ ")
print(" |    `   \  ___/|    |     / __ \_\___ \  |  | \  ___/ ")
print("/_______  /\___  >____|    (____  /____  > |__|  \___  > ")
print("        \/     \/               \/     \/            \/ ")

print("\n\tAuthor: Corvo")
print("\n\tGithub: https://github.com/rf-peixoto/")
print("\n")

while True:
    # Updating:
    print("[*] Updating...")
    pg = get_url(main)
    # Extract first links:
    print("[*] Finding links...")
    links = extract_links(pg)
    print("[*] Scraping...")
    data_found = False
    # Looking for data:
    for tk in links:
        try:
            raw_data = get_raw(raw, tk)
            # Test patterns:
            if not data_found:
                for pt in patterns:
                    if re.match(pt, raw_data):
                        data_found = True
            else:
                print("[+] Possible data at {0}".format(raw + tk))
                save_data("{0}.txt".format(tk), raw_data)
        except Exception as error:
            print(error)
    sleep(DELAY)
