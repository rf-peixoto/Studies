# =======================================================
# Web Crawler
# =======================================================
import requests
import re

# Request Header:
header = {'user-agent': 'Graverobber'}

# URLs to look:
targets = input("Enter URLs: ").split(" ")
crawled = set()
#pattern = r'href=[\'"](https?://[\w:/\.\'\"_]+)'
# Template
pattern = r'<a href="?\'?(https?:\/\/[^"\'>]*)'
link_found = ""
links = []

# Requisition:
for target in targets:
    if target in crawled:
        continue
    else:
        try:
            html = requests.get(target, headers=header)
        except Exception as error:
            print("Error: {0}".format(error))
            continue
        link_found = re.findall(pattern, html.text)
        if link_found != None:
            links.append(link_found)
        crawled.add(target)

print(links)

# =======================================================
counter = 0
option = input("Continue? <y/n> ")

if option in "yY":
    for target in links[counter]:
        try:
            html = requests.get(target, headers=header)
        except Exception as error:
            print("Error: {0}".format(error))
            continue
        link_found = re.findall(pattern, html.text)
        if link_found != None:
            links.append(link_found)
        print("Crawling: {0}".format(target))
        counter += 1
        crawled.add(target)

print(links)
