import os

loops = int(input("How many loops? "))
bts = int(input("How many bytes per loop? "))

with open("random.bytes", "wb") as fl:
    for i in range(loops):
        fl.write(os.getrandom(bts))

print("Done.")
