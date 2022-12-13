from requests.exceptions import Timeout
import webbrowser
import requests
import sys

# -------------------------------------------------------------------------- #
# Menu:
# -------------------------------------------------------------------------- #


# -------------------------------------------------------------------------- #
# Options:
# -------------------------------------------------------------------------- #
if len(sys.argv) != 3:
    print("Usage:")
    print("{0} URL Filename".format(sys.argv[0]))
    sys.exit()

# URL:
target = sys.argv[1]
if not target.startswith("http"):
    target = "https://" + target

# DATA:
filename = sys.argv[2]
headers = {'Content-type':'text/html; charset=UTF-8',
           'Slug':filename}

# Request:
try:
    r = requests.put(target, data=open(filename, 'rb'), headers=headers, timeout=3)
except Timeout as error:
    print(error)
# -------------------------------------------------------------------------- #
# Print:
# -------------------------------------------------------------------------- #
# OK
if r.status_code == 200:
    print("[\033[92m{0}\033[00m] - {1}".format(r.status_code, r.reason))
    # Check:
    new_url = target + "/" + filename
    check = requests.get(new_url)
    if check.status_code == 200:
        print("[\033[92m Confirmed \033[00m] - {0}".format(new_url))
        webbrowser.open(target + "/{0}".format(filename), new=2)
    else:
        print("[\033[91m {0} - {1} \033[00m] - {2}".format(check.status_code, check.reason, new_url))

elif str(r.status_code).startswith("4"):
    print("[\033[91m{0}\033[00m] - {1}".format(r.status_code, r.reason))
else:
    print("[\033[93m{0}\033[00m] - {1}".format(r.status_code, r.reason))
