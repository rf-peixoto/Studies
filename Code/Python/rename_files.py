import os

files = os.listdir()

for f in files:
    try:
        os.rename(f, f.lower())
    except Exception as error:
        print(error)

