# =========================================================================== #
# Connect Over Tor
# =========================================================================== #
#import os
#os.system("sudo service tor start")
import requests
from random import choice
# =========================================================================== #
# CONFIGURATION:
# =========================================================================== #
user_agents = ['Chrome', 'Edge', 'Firefox', 'Safari', 'Opera', 'Lynx', 'Brave']
headers = {'User-Agent':choice(user_agents)}
proxies = {'http':'socks5://127.0.0.1:9050',
           'https':'socks5://127.0.0.1:9050'}

# =========================================================================== #
# Check IP
# =========================================================================== #
def check_ip(proxies, headers):
    return requests.get('https://ident.me', proxies=proxies, headers=headers).text
