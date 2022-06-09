from bs4 import BeautifulSoup
import urllib.parse
import urllib.request
import os, sys

url = sys.argv[1]
headers = {}
headers['User-Agent'] = "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:48.0) Gecko/20100101 Firefox/100.0"
req = urllib.request.Request(url, headers = headers)
content = BeautifulSoup(urllib.request.urlopen(req).read())

clear_links = []
for link in content.find_all("a"):
    tmp = link.get("href") #urllib.parse.quote(link.get("href"))
    print(tmp)
    if tmp.endswith(".pdf"):
        clear_links.append(link)
        os.system("wget '{0}'".format(tmp))
