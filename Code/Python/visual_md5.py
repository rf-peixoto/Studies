import hashlib
import os
os.system("clear")
print("-" * 20)
# ============================================================================ #
# Setup:
# ============================================================================ #
from colorama import Fore
import colorama

colorama.init()
# ============================================================================ #
# First File Hash
# ============================================================================ #
data = "Test"
hashed = hashlib.md5(data.encode()).hexdigest()
splited = [hashed[:8], hashed[8:16], hashed[16:24], hashed[24:32]]

print("First file data:\n")
for part in splited:
    print(part)

print("-" * 20)
# ============================================================================ #
# Second File Hash
# ============================================================================ #
data_new = "Tes"
hashed_new = hashlib.md5(data_new.encode()).hexdigest()
splited_new = [hashed_new[:8], hashed_new[8:16], hashed_new[16:24], hashed_new[24:32]]

print("Second file data:\n")

points = 0
counter = 0
line = 0
for row in splited:
    for ch in row:
        if splited_new[line][counter] != splited[line][counter]:
            print(Fore.RED, end="")
            print("{0}".format(splited_new[line][counter]), end="")
            print(Fore.RESET, end="")
        else:
            print(Fore.GREEN, end="")
            print(ch, end="")
            print(Fore.RESET, end="")
            points += 1
        counter += 1
    counter = 0
    line += 1
    print("")

print("-" * 20)
# ============================================================================ #
# End
# ============================================================================ #
def percent(value):
    return round((value / 32) * 100, 2)

percentage = percent(points)
print("{0}/32 match. - {1}% similar.".format(points, percentage))
