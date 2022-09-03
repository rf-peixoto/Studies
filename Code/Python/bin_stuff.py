import sys

tmp = []
for i in sys.argv[1]:
    tmp.append(bin(ord()))

# For use, remove '
for i in tmp:
    print(chr(i))

# Example:
string = [0b1001000, 0b1100101, 0b1101100, 0b1101100, 0b1101111, 0b101100, 0b100000, 0b1110111, 0b1101111, 0b1110010, 0b1101100, 0b1100100]
decoded = ""
for i in string:
    decoded += chr(i)
print(decoded)
