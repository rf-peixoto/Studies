import requests
import webbrowser
import json  
from time import sleep
#-----#
while True:
    link = requests.get("https://api.thecatapi.com/v1/images/search").content.decode()[1:-1]
    img = json.loads(link)
    webbrowser.open(img['url'], new=2)
    sleep(3600)
#-----#
