# FTP Contents Enum

import urllib.request
from bs4 import BeautifulSoup
import re

target = input("Set target: ")

with urllib.request.urlopen(target) as url:
    page = url.read()

soup = BeautifulSoup(page, "html.parser")
links = soup.find_all("a")

root_links = [] # Links do diretório atual

for link in links:
    root_links.append(target + str(link.contents)[2:-2:])


