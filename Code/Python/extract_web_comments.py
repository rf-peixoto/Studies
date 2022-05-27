import sys, re
import requests

# Prepare input:
if sys.argv[1].startswith("http"):
    input = sys.argv[1]
else:
    input = "https://" + sys.argv[1]

# Request Page:
print("\033[92m[*]\033[00m Requesting data from {0}".format(input))
headers = {
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0'
    }
try:
    page = requests.get(input, headers=headers)
except Exception as error:
    print("\n\033[31m[x] Error while requesting page:")
    print("\033[31m{0}\033[00m".format(error))
    sys.exit()

# Verify Request:
if page.status_code != 200:
    print("\n\033[31m[-] Error while getting page:")
    print("\033[31mStatus Code: {0} Reason: {1}\033[00m".format(page.status_code, page.reason))
else:
    # Parsing Response:
    try:
        body = page.content.decode()
    except Exception as error:
        print("\033[31m[x] Error with content encoding. Converting everything to string.\033[00m")
        body = str(page.content)

    # Searching comments:
    print("\033[92m[+]\033[00m Parsing comments.")
    # HTML
    comments = re.findall('<!--(.*?)-->', body)
    if len(comments) > 0:
        print("\n\033[94m<!----- HTML ----->\033[00m")
        for comm in comments:
            print("\033[94m[*]\033[0m {0}".format(comm))
    else:
        print("\n\033[31m[x] Something went wrong. No HTML comment was found.")

    # CSS & Js
    comments = re.findall('(\/\*[\w\'\s\r\n\*]*\*\/)|(\/\/[\w\s\']*)', body)
    if len(comments) > 0:
        print("\n\033[94m/*----- CSS & JS -----*/\033[00m")
        for comm in comments:
            print("\033[94m[*]\033[0m {0}".format(comm))
    else:
        print("\n\033[31m[x] Something went wrong. No CSS or JS comment was found.")

# Finish program:
print("\n\033[92m[*]\033[00m Done.")
