# ================================================= #
# Python Wikipedia Searcher			    #
# ================================================= #
import os
import sys
import colorama
import wikipedia
from colorama import Fore, Back, Style
# ================================================= #
# Some Commands					    #
# ================================================= #
# Get a list of results:
# results = wikipedia.search("string")
# results = wikipedia.search("String", suggestion=True)

# Get summary:
# summ = wikipedia.summary("string")
# Set language:
# wikipedia.languages()
# wikipedia.set_lang("pt")

# Get page details:
# page = wikipedia.page("string")
# page.title
# page.url
# page.content

# ================================================= #
# Config					    #
# ================================================= #
# Initialize and setup colors:
colorama.init()
print(Style.BRIGHT)
# Wiki langauge:
wikipedia.set_lang("pt")

# ================================================= #
# Initialize					    #
# ================================================= #
# Welcome message:
print("Bem vindo ao buscador da  " + Fore.YELLOW  + "Wikipédia" + Fore.RESET + ".")
print("Digite o termo pelo qual você busca:")
# Target:
target = input(Fore.YELLOW + ">>> " + Fore.RESET).capitalize()
print("\n" + Fore.BLUE + "[*] " + Fore.RESET + "Pesquisando. Por favor, aguarde...\n")
# Search:
results = wikipedia.search(target)
if not len(results) > 0:
    print(Fore.RED + "[-] " + Fore.RESET + "Nenhum resultado encontrado. :( ")
    sys.exit()
# Print results:
print(Fore.GREEN + "[+] " + Fore.RESET + "Selecione uma das páginas encontradas:")
for i in range(len(results)):
    print(Fore.BLUE + "{0}".format(i) + Fore.RESET + " - " + "{0}".format(results[i]))
# Select option:
try:
    option = int(input(Fore.YELLOW + ">>> " + Fore.RESET))
    if not results[option] == None:
        # Fetch Data:
        print(Fore.BLUE + "[*] " + Fore.RESET + "Buscando dados. Por favor, aguarde...\n")
        page = wikipedia.page(results[option])
        summary = wikipedia.summary(results[option])
except Exception as error:
    print(Back.RED + "Opção inválida!" + Back.RESET)
    sys.exit()

# ================================================= #
# Show data:					    #
# ================================================= #
print("\n" + Fore.YELLOW + "{0}".format(results[option]) + Fore.RESET)
print(summary)
print("\nPara visualizar a página completa visite " + Fore.YELLOW + page.url + Fore.RESET + "\n")
sys.exit()
