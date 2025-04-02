import requests
import time

# Replace these with your actual API keys
SERPAPI_KEY = 'your_serpapi_key_here'
BING_API_KEY = 'your_bing_api_key_here'

# Your dorks
dorks = [
    '("download" | "free download") ("apk" | "ipa" | "android app" | "ios app") ("marketplace" | "store" | "hub") -site:play.google.com -site:apple.com',
    'intitle:index.of (apk | ipa) ("android" | "ios") (download | app)',
    '("apk download" | "apk free") ("store" | "market") inurl:apk -site:play.google.com',
    'inurl:apk ("free download" | "latest version") ("android" | "app") -site:google.com',
    '("top 10" | "best" | "list of") ("apk sites" | "android app stores") -site:android.com',
    'filetype:apk OR filetype:ipa ("download" | "android app") -site:play.google.com -site:apple.com'
]

# Results
serpapi_results = []
bing_results = []
duckduckgo_results = []

# SerpAPI
for dork in dorks:
    print(f"[SerpAPI] Searching: {dork}")
    params = {
        "engine": "google",
        "q": dork,
        "api_key": SERPAPI_KEY,
        "num": 10
    }
    try:
        response = requests.get("https://serpapi.com/search", params=params)
        data = response.json()
        for result in data.get("organic_results", []):
            link = result.get("link")
            if link:
                serpapi_results.append(link)
    except Exception as e:
        print(f"SerpAPI error: {e}")
    time.sleep(1)

# Bing API
for dork in dorks:
    print(f"[Bing] Searching: {dork}")
    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    params = {"q": dork, "count": 10}
    try:
        response = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params)
        data = response.json()
        for result in data.get("webPages", {}).get("value", []):
            link = result.get("url")
            if link:
                bing_results.append(link)
    except Exception as e:
        print(f"Bing error: {e}")
    time.sleep(1)

# DuckDuckGo (manual fallback)
for dork in dorks:
    print(f"[DuckDuckGo] Generated manual search for: {dork}")
    duckduckgo_results.append(f"https://lite.duckduckgo.com/lite/?q={dork.replace(' ', '+')}")

# Save results
with open("search_results.txt", "w", encoding="utf-8") as f:
    f.write("=== Google (SerpAPI) ===\n")
    for url in serpapi_results:
        f.write(url + "\n")
    f.write("\n=== Bing ===\n")
    for url in bing_results:
        f.write(url + "\n")
    f.write("\n=== DuckDuckGo ===\n")
    for url in duckduckgo_results:
        f.write(url + "\n")

print("✅ Done. Results saved to 'search_results.txt'")
