import requests
import sys

headers = {"User-Agent" : "Mozilla/5.0 (X11; Linux x86_64; rv:104.0) Gecko/20100101 Firefox/104.0"}

# Get:
req = requests.get(sys.argv[1], allow_redirects=False, headers=headers)

# Check if is redirect:
if req.status_code == 301:
    # Redirect. Request it again:
    req = requests.get(sys.argv[1], headers=headers)
    print(req.url)
else:
    print(req)
