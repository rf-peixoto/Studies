import hashlib
import os
from colorama import Fore
import colorama
os.system("clear")
print("# ============================================================================ #")
print(Fore.YELLOW + "[*] " + Fore.RESET + "Files in this dir:")
print("\n")
os.system("ls")
print("\n")
print("# ============================================================================ #")
# ============================================================================ #
# Setup:
# ============================================================================ #
colorama.init()
# ============================================================================ #
# First File Hash
# ============================================================================ #
file_a = input(Fore.YELLOW + "[*]" + Fore.RESET + " First file: ")
with open(file_a, "rb") as fl:
    data = fl.read()
hashed = hashlib.md5(data).hexdigest()
splited = [hashed[:8], hashed[8:16], hashed[16:24], hashed[24:32]]

for part in splited:
    for c in part:
        print(c + " ", end="")
    print("")
#print("\n")
# ============================================================================ #
# Second File Hash
# ============================================================================ #
file_b = input(Fore.YELLOW + "[*]" + Fore.RESET + " Second file: ")
with open(file_b, "rb") as fl:
    data_new = fl.read()
hashed_new = hashlib.md5(data_new).hexdigest()
splited_new = [hashed_new[:8], hashed_new[8:16], hashed_new[16:24], hashed_new[24:32]]

points = 0
counter = 0
line = 0
# To do: change this sh** to https://github.com/rf-peixoto/Studies/blob/main/Code/Python/ripstr.py
for row in splited:
    for ch in row:
        if splited_new[line][counter] != splited[line][counter]:
            print(Fore.RED, end="")
            print("{0} ".format(splited_new[line][counter]), end="")
            print(Fore.RESET, end="")
        else:
            print(Fore.GREEN, end="")
            print(ch + " ", end="")
            print(Fore.RESET, end="")
            points += 1
        counter += 1
    counter = 0
    line += 1
    print("")

print("# ---------------------------------------------------------------------------- #")
# ============================================================================ #
# End
# ============================================================================ #
def percent(value):
    return round((value / 32) * 100, 2)

percentage = percent(points)
print(Fore.YELLOW + "[*]" + Fore.RESET + " {0}/32 match. - {1}% similar.".format(points, percentage))
print("# ============================================================================ #")
