# ============================================================================ #
# ================================================ #
#     __  __     _               __      ____      #
#    / / / /__  (_)___ ___  ____/ /___ _/ / /____  #
#   / /_/ / _ \/ / __ `__ \/ __  / __ `/ / / ___/  #
#  / __  /  __/ / / / / / / /_/ / /_/ / / / /      #
# /_/ /_/\___/_/_/ /_/ /_/\__,_/\__,_/_/_/_/       #
#                                v0.1.0            #
# ------------------------------------------------ #

# ============================================================================ #
import os
import secrets
import clipboard
import colorama
from colorama import Fore, Back, Style
from Crypto.Cipher import AES
# ============================================================================ #
# INITIALIZE PROGRAM:
# Clean prompt:
os.system("cls")
# Start colorama module:
colorama.init()
print(Fore.GREEN + Back.BLACK)
title = """# ================================================ #
#     __  __     _               __      ____      #
#    / / / /__  (_)___ ___  ____/ /___ _/ / /____  #
#   / /_/ / _ \/ / __ `__ \/ __  / __ `/ / / ___/  #
#  / __  /  __/ / / / / / / /_/ / /_/ / / / /      #
# /_/ /_/\___/_/_/ /_/ /_/\__,_/\__,_/_/_/_/       #
#                                v0.1.0            #
# ------------------------------------------------ #
"""
print(Style.NORMAL + title)
#print(Style.RESET_ALL)
print("Welcome " + Fore.WHITE + Back.GREEN + "{0}".format(os.getenv("USERNAME").upper() + Fore.GREEN + Back.BLACK + ". Choose your option:"))
print("\n")
# ============================================================================ #
def open_file(filename):
    # Try to open the file:
    try:
        with open(filename, "rb") as fl:
            data = fl.read()
            fl.close()
            return data
    except Exception as error:
    # An error ocurred. Maybe the file does not exists.
        os.system("cls")
        print(Style.NORMAL + title)
        print(Style.RESET_ALL + Back.RED + "{0}".format(error) + Fore.GREEN + Back.BLACK + "\n")
# ============================================================================ #
def encrypt_file():
    filename = input("Select file: ")
    filedata = open_file(filename)
    if not filedata:
        return
    encrypted_data, tag = cipher.encrypt_and_digest(filedata)
    with open(filename, "wb") as fl:
        fl.write(encrypted_data)
        fl.close()
    print(Fore.WHITE + Back.GREEN + "Success!" + Fore.GREEN + Back.BLACK + "\n")
    print("Your key is " + Fore.BLUE + "{0}".format(key.decode()) + Fore.GREEN + ". Copy to clipboard?""")
    print("+ " + Style.DIM + Fore.YELLOW + Back.BLACK + "[y]" + Fore.GREEN + Back.BLACK + "es.")
    print("+ " + Style.DIM + Fore.YELLOW + Back.BLACK + "[n]" + Fore.GREEN + Back.BLACK + "o.")
    option = input(">>> ").lower()
    if option == "y":
        clipboard.copy(key.decode())
    os.system("cls")
    print(Style.NORMAL + title)
# ---------------------------------------------------------------------------- #
def decrypt_file(nonce, tag):
    filename = input("Select file: ")
    filedata = open_file(filename)
    if not filedata:
        return
    key = input("Enter your key: ")
    try:
        cipher = AES.new(key.encode(), AES.MODE_EAX, nonce = nonce)
        decoded_data = cipher.decrypt_and_verify(filedata, tag)
        #cipher.verify(tag)
        input()
        print("\n")
        with open("new." + filename, "wb") as fl:
            fl.write(decoded_data)
            fl.close()
        os.system("cls")
        print(Style.NORMAL + title)
        print(Fore.WHITE + Back.GREEN + "Success!" + Fore.GREEN + Back.BLACK + "\n")
        
    except Exception as error:
        os.system("cls")
        print(Style.NORMAL + title)
        print(Style.RESET_ALL + Back.RED + "{0}".format(error) + Fore.GREEN + Back.BLACK + "\n")
# ============================================================================ #
# MENU
while True:
    # --------------------------------------------------- #
    # RELOAD SETUP
    key = bytes(secrets.token_urlsafe(12).encode("utf-8"))
    cipher = AES.new(key, AES.MODE_EAX)
    nonce = cipher.nonce
    tag = ""
    # --------------------------------------------------- #
    # MENU
    print("+ " + Style.DIM + Fore.YELLOW + Back.BLACK + "[e]" + Fore.GREEN + Back.BLACK + "ncrypt file.")
    print("+ " + Style.DIM + Fore.YELLOW + Back.BLACK + "[d]" + Fore.GREEN + Back.BLACK + "ecrypt file.")
    print("+ " + Style.DIM + Fore.RED + Back.BLACK + "[q]" + Fore.GREEN + Back.BLACK + "uit.")
    option = input(">>> ").lower()
    if option == "e":
        encrypt_file()
    elif option == "d":
        decrypt_file(nonce, tag)
    elif option == "q":
        os.system("cls")
        break
    else:
        # Update screen:
        os.system("cls")
        print(Style.NORMAL + title)
        print(Fore.WHITE + Back.RED + "Invalid input. Choose your option." + Fore.GREEN + Back.BLACK)

