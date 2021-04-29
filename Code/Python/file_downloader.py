import sys
import requests

file = sys.argv[1]
url = sys.argv[2]

data = requests.get(url)
with open(file, "wb") as fl:
    fl.write(data.content)

