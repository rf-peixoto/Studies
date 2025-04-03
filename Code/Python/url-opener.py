import webbrowser
import time
from colorama import Fore, Style, init

init(autoreset=True)

def normalize_url(url):
    url = url.strip()
    if not url:
        return None
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    return url

def read_urls_from_file(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()
    return [normalize_url(line) for line in lines if normalize_url(line)]

def open_in_batches(urls, batch_size=5):
    total = len(urls)
    for i in range(0, total, batch_size):
        batch = urls[i:i+batch_size]
        print(Fore.YELLOW + f"\nOpening batch {i // batch_size + 1} ({len(batch)} URLs):\n")
        for url in batch:
            print(Fore.GREEN + f" - {url}")
            webbrowser.open_new_tab(url)
            time.sleep(0.2)  # short delay to avoid browser throttling
        if i + batch_size < total:
            input(Fore.CYAN + "\nPress Enter to open next batch...")
        else:
            print(Fore.CYAN + "\nAll URLs processed.")

def main():
    file_path = "urls.txt"  # Change path if needed
    print(Style.BRIGHT + Fore.BLUE + f"Reading URLs from: {file_path}")
    urls = read_urls_from_file(file_path)
    if not urls:
        print(Fore.RED + "No valid URLs found.")
        return
    open_in_batches(urls)

if __name__ == "__main__":
    main()
