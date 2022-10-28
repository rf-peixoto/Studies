import sys

data = sys.argv[1]
tmp = ""
for c in data[::-1]:
    tmp += "\\x" + str(c.encode("utf-8").hex())
print(tmp)
