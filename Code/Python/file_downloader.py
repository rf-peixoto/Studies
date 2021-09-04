import sys
import requests

output = sys.argv[1]
url = sys.argv[2]

data = requests.get(url)
with open(output, "wb") as fl:
    fl.write(data.content)

