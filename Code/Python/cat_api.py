import requests
import webbrowser
import json

# Request new picture:
link = requests.get("https://api.thecatapi.com/v1/images/search").content.decode()>
img = json.loads(link)

# Show:
webbrowser.open(img['url'], new=2)
