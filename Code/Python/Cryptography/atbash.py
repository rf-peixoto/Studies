# Atbash
import sys
import string

mode = sys.argv[1] # -e | -d
txt = sys.argv[2].upper() # String
tmp = ""

# Alphabet
common = list(string.ascii_uppercase)
coded = sorted(string.ascii_uppercase, reverse=True)

# Execution:
if mode == "-e":
    for c in txt:
        if c in string.ascii_uppercase:
            tmp += coded[common.index(c)]
        else:
            tmp += c
elif mode == "-d":
    for c in txt:
        if c in string.ascii_uppercase:
            tmp += common[coded.index(c)]
        else:
            tmp += c

# End:
print(tmp)

