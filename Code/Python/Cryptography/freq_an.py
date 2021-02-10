# Análise de Frequência
import sys
from string import ascii_uppercase as ups

# Argumentos:
language = sys.argv[1] # en | pt | es
txt = sys.argv[2].upper() # String
# Linguagem
if language == "en":
    freq = "ETAOINSHRDLCUMWFGYPBVKJXQZ"
elif language == "pt":
    freq = ""
elif language == "es":
    freq = ""
# Contador:
letters = {"A":0, "B":0, "C":0, "D":0, "E":0, "F":0, "G":0, "H":0, "I":0,
           "J":0, "K":0, "L":0, "M":0, "N":0, "O":0, "P":0, "Q":0, "R":0,
           "S":0, "T":0, "U":0, "V":0, "W":0, "X":0, "Y":0, "Z":0}

# Verificar letras:
for c in txt:
    if c in ups:
        letters[c] += 1

# Definir pontuação:
order = []
score = 0 # Min: 0 | Max: 12

for i in sorted(letters, key=letters.get, reverse=True):
    print("{0} : {1}".format(i, letters[i]))
    order.append(i)

order = ''.join(order)

# Checar Pontuação:
for c in freq[:6]:
    if c in order[:6]:
        score += 1
for c in freq[-6:]:
    if c in order[-6:]:
        score += 1

print("Score: {0}/12".format(score))
