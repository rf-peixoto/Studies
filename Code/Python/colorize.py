import colorama
from colorama import Fore, Back, Style

class Colorize:
    def __init__(self):
        colorama.init()

    def reset_all(self):
        print(Style.RESET_ALL + Fore.RESET + Back.RESET)

    def reset(self):
        print(Fore.RESET + Back.RESET)

    def green(self):
        print(Style.BRIGHT + Fore.GREEN)

    def red(self):
        print(Style.BRIGHT + Fore.RED)

    def blue(self):
        print(Style.BRIGHT + Fore.BLUE)

    def yellow(self):
        print(Style.BRIGHT + Fore.YELLOW)

    def error(self):
        print(Style.BRIGHT + Fore.WHITE + Back.RED)

