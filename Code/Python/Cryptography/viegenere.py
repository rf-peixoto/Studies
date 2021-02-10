# Cifra de Vigenere
import sys
from string import ascii_lowercase as lowercase

# Argumentos:
mode = sys.argv[1] # -e | -d | -b
txt = sys.argv[2].lower() # String
key = sys.argv[3].lower() # String
key_id = 0
result = ""

# Execução:
if mode in "-e-d":
    for c in txt:
        if c in lowercase:
            idx = lowercase.find(c)
            if mode == "-e":
                idx += lowercase.find(key[key_id % len(key)])
            elif mode == "-d":
                idx -= lowercase.find(key[key_id % len(key)])
            result += lowercase[idx % 26]
            key_id += 1
        else:
            result += c
    print(result)
