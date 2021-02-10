# Cifra de Vernam (Exemplo de XOR)
import sys
import binascii

# Usage:
#xor.py [MODO] [MENSAGEM] [CHAVE]

# Argumentos:
mode = sys.argv[1]
key = sys.argv[3]
key_id = 0
xored = ''

# Checando mensagem:
if mode == "-e":
    msg = sys.argv[2]
elif mode == "-d":
    msg = binascii.unhexlify(sys.argv[2])

# Execução:
for msgchar in msg:
    xored += chr(ord(key[key_id % len(key)]) ^ ord(msgchar))
    key_id += 1

if mode == "-e":
    print(binascii.hexlify(xored.encode()))
elif mode == "-d":
    print(xored)
