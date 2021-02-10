# Implementação da Cifra de César
import sys
from string import ascii_lowercase as lower

# Modo de uso:
if len(sys.argv) <= 0:
    print("Modo de uso: caesar.py [MODO] [TEXTO] [CHAVE]")

# Argumentos:
mode = sys.argv[1] # -e | -d | -b
txt = sys.argv[2].lower() # String
if mode == "-b":
    key = 0
else:
    key = int(sys.argv[3]) # Interger
result = ""

# Checando Texto:
if mode in "-e-d":
    for c in txt:
        if c in lower:
            idx = lower.find(c)
            if mode == "-e":
                idx = (idx + key) % 26
            elif mode == "-d":
                idx = (idx - key) % 26
            result += lower[idx]
        else:
            result += c
    print(result)
elif mode == "-b":
    for key in range(1, 26):
        result = ""
        print("Chave: {0}".format(key))
        for c in txt:
            if c in lower:
                idx = lower.find(c)
                idx = (idx - key) % 26
                result += lower[idx]
            else:
                result += c
        print(result)

