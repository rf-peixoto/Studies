import os
import sys
import time
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama
init()

def clear_screen():
    os.system('clear')

def ascii_clock():
    try:
        while True:
            clear_screen()
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S")
            current_date = now.strftime("%A, %B %d, %Y")
            clock_art = f"""
{Fore.CYAN}{Style.BRIGHT}
     .d8888b.  888      8888888 888b    888      8888888b.   .d88888b.
    d88P  Y88b 888        888   8888b   888      888   Y88b d88P" "Y88b
    Y88b.      888        888   88888b  888      888    888 888     888
     "Y888b.   888        888   888Y88b 888      888   d88P 888     888
        "Y88b. 888        888   888 Y88b888      8888888P"  888     888
          "888 888        888   888  Y88888      888        888     888
    Y88b  d88P 888        888   888   Y8888      888        Y88b. .d88P
     "Y8888P"  88888888 8888888 888    Y888      888         "Y88888P"
{Style.RESET_ALL}
             {Fore.YELLOW}{Style.BRIGHT}{current_time}{Style.RESET_ALL}
            {Fore.GREEN}{current_date}{Style.RESET_ALL}
            """
            print(clock_art)
            time.sleep(1)
    except KeyboardInterrupt:
        clear_screen()
        sys.exit()

if __name__ == "__main__":
    ascii_clock()
