import sys

tmp = []
for i in sys.argv[1]:
    tmp.append(bin(ord()))

# For use, remove '
for i in tmp:
    print(chr(i))
