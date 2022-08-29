import sys

# e: encode / d: decode
if sys.argv[1].lower() == "e":
    tmp = []
    for c in sys.argv[2]:
        tmp.append(ord(c))
    print(tmp)
elif sys.argv[1].lower() == "d":
    tmp = ""
    for i in sys.argv[2][1:-1].split(","):
        tmp += chr(int(i))
    print(tmp)
