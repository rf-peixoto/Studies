import sys

data = sys.argv[1]
tmp = ""
for c in data[::-1]:
    if sys.argv[2] == "x":
        tmp += "\\x" + str(c.encode("utf-8").hex())
    else:
        tmp += str(c.encode("utf-8").hex())
print(tmp)
