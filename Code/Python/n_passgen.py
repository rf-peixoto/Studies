# Usage: python n_passgen.py 4 9999
# Numeric Wordlist Generator
import sys
from time import sleep
from tqdm import tqdm

# Variables:
passlst = []
tmp = 0
digits = int(sys.argv[2])

# Generating:
print("Generating PINS:")

# Generate list:
for i in tqdm(range(int(sys.argv[1]) + 1)):
    passlst.append(str(i).zfill(digits))
    if digits >= 7:
        sleep(0.01)
    i += 1

# Saving:
print("Saving: ")

# Save it:
with open("pins.txt", "w") as fl:
    for i in tqdm(range(len(passlst))):
        fl.write(passlst[i] + '\n')
        if digits >= 7:
            sleep(0.01)
    fl.close()

# Done.
print('Done.')

