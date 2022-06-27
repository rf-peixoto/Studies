import os

for folder_name, subfolders, filenames in os.walk(os.getcwd()):
    print("{0}".format(folder_name))
    for subf in subfolders:
        print("-{0}".format(subf))
    for fname in filenames:
        print("-{0}".format(fname))
