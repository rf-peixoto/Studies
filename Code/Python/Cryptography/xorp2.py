import sys
import binascii

mode = sys.argv[1]
key = sys.argv[3]
keyidx = 0
xored = ''

if mode == '-e':
    msg = sys.argv[2]
elif mode == '-d':
    msg = binascii.unhexlify(sys.argv[2])

for msgchar in msg:
    xored += chr(ord(key[keyidx % len(key)]) ^ ord(msgchar))
    keyidx += 1

if mode == '-e':
    print binascii.hexlify(xored)
elif mode == '-d':
    print xored
