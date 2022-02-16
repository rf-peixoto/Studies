import colorama
from colorama import Fore, Back, Style

class Colorize:
    def __init__(self):
        colorama.init()

    def reset_all(self):
        print(Style.RESET_ALL + Fore.RESET + Back.RESET)

    def reset(self):
        print(Fore.RESET + Back.RESET)

    def green(self, text):
        print(Style.BRIGHT + Fore.GREEN + text)

    def red(self, text):
        print(Style.BRIGHT + Fore.RED + text)

    def blue(self, text):
        print(Style.BRIGHT + Fore.BLUE + text)

    def yellow(self, text):
        print(Style.BRIGHT + Fore.YELLOW + text)

    def error(self, text):
        print(Style.BRIGHT + Fore.WHITE + Back.RED + text)
        
