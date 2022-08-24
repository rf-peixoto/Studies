import requests
import os, sys

# Request:
try:
    data = requests.get(sys.argv[1])
except Exception as error:
    print(error)
    sys.exit()

# Check for header:
try:
    xframe = data.headers['x-frame-options']
    print("[+] X-FRAME-OPTIONS found!")
except Exception as error:
    print("Error: {0} not found!".format(error))
    sys.exit()

# Try to clickjack:
print("[+] Trying to clickjack.")
html = """
<html>
	<body>
		<iframe src="{0}" height='600px' width='800px'></iframe>
	</body>
</html>
""".format(sys.argv[1])

print("[+] Saving on output.html.")
with open("output.html", "w") as fl:
    fl.write(html)
