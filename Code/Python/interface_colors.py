# ---------------------------------------- #
#  Interface Colors                        #
# ---------------------------------------- #
import colorama
from colorama import Fore, Back, Style

# Success
def success():
    print(Style.BRIGHT + Fore.GREEN + "Success!" + Fore.RESET + Style.RESET_ALL, end="")
def plus():
    print(Style.BRIGHT + Fore.GREEN + "[+]" + Fore.RESET + Style.RESET_ALL, end="")
# Alert!
def alert():
    print(Style.BRIGHT + Fore.YELLOW + "Attention!" + Fore.RESET + Style.RESET_ALL, end="")
def exclamation():
    print(Style.BRIGHT + Fore.YELLOW + "[!]" + Fore.RESET + Style.RESET_ALL, end="")
# Fail!
def fail():
    print(Style.BRIGHT + Fore.RED + "Failed!" + Fore.RESET + Style.RESET_ALL, end="")
def minus():
    print(Style.BRIGHT + Fore.RED + "[-]" + Fore.RESET + Style.RESET_ALL, end="")
# Information:
def info():
    print(Style.BRIGHT + Fore.BLUE + "[*]" + Fore.RESET + Style.RESET_ALL, end="")
def question():
    print(Style.BRIGHT + Fore.BLUE + "[?]" + Fore.RESET + Style.RESET_ALL, end="")
def input_icon():
    print(Style.BRIGHT + Fore.BLUE + ">>> " + Fore.RESET + Style.RESET_ALL, end="")
