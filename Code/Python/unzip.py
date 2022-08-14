from zipfile import ZipFile

zp = input("Filename: ")

with ZipFile(zp, "r") as pack:
      pack.extractall()

print(pack.namelist())
