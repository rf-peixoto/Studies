
import requests
import time

# === Configuration ===
SERPAPI_KEY = 'SERP API KEY'

# === Dorks ===
dorks = [
    '("download" | "free download") ("apk" | "ipa" | "android app" | "ios app") ("marketplace" | "store" | "hub") -site:play.google.com -site:apple.com',
    'intitle:index.of (apk | ipa) ("android" | "ios") (download | app)',
    '("apk download" | "apk free") ("store" | "market") inurl:apk -site:play.google.com',
    'inurl:apk ("free download" | "latest version") ("android" | "app") -site:google.com',
    '("top 10" | "best" | "list of") ("apk sites" | "android app stores") -site:android.com',
    'filetype:apk OR filetype:ipa ("download" | "android app") -site:play.google.com -site:apple.com'
]

# === Target Keywords ===
keywords = ["keyword1", "keyword2"]

# === Storage ===
serpapi_results = []
duckduckgo_results = []

# === Search Loop ===
for dork in dorks:
    for keyword in keywords:
        query = f'{dork} "{keyword}"'
        print(f"[SerpAPI] Searching: {query}")
        # SerpAPI query
        try:
            params = {
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "num": 10
            }
            response = requests.get("https://serpapi.com/search", params=params)
            data = response.json()
            for result in data.get("organic_results", []):
                link = result.get("link")
                if link:
                    serpapi_results.append(f"[{keyword}] {link}")
        except Exception as e:
            print(f"SerpAPI error: {e}")
        time.sleep(1)

        # DuckDuckGo manual search link
        ddg_link = f"https://lite.duckduckgo.com/lite/?q={query.replace(' ', '+')}"
        duckduckgo_results.append(f"[{keyword}] {ddg_link}")
        time.sleep(1)

# === Save Results ===
output_path = "search_results.txt"
with open(output_path, "w", encoding="utf-8") as f:
    f.write("=== Google (SerpAPI) ===\n")
    for url in serpapi_results:
        f.write(url + "\n")
    f.write("\n=== DuckDuckGo (Manual Search) ===\n")
    for url in duckduckgo_results:
        f.write(url + "\n")

print("✅ Done. Results saved to 'search_results.txt'")
