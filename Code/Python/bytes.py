# Bytes and Bits in Python:
# Ref: https://www.geeksforgeeks.org/working-with-binary-data-in-python/

x = bytes(b'\x00') # Immutable object.
x = bytearray(b'\x00\x0F') # Bytearray

# ============================================================================ #

# Bitwise Operations:

# Samples:
bytesA = int('11110000', 2) # 240
bytesB = int('00001111', 2) # 15
bytesC = int('10101010', 2) # 85

# Flip:
print(~bytesA)

# AND &&
print(bytesA & bytesB)

# OR |
print(bytesA | bytesB)

# XOR ^
print(bytesA ^bytesB)

# Shifting right (Lose the right-most bit):
print(bytesB >> 3)

# Shifting left (Add a 0 bit to the right side):
print(bytesC << 1)

# See if a single bit is set:
bit_mask = int('00000001', 2) # Bit 1

# Is bit set in bytesA?
print(bit_mask & bytesA)

# Is it in bytesB?
print(bit_mask & bytesB)

# ============================================================================ #

# Comparing files with bitwise operations:
'''
with open('file.txt', 'rb') as fl1, open('file2.txt', 'rb') as fl2:
    data1 = fl1.read()
    data2 = fl2.read()

if data1 != data2:
    print("Files do not match.")
else:
    print("Files match.")
'''

# ============================================================================ #

# Checking file signatures (in this case, JPEG):
'''
import binascii

jpeg_signatures = [binascii.unhexlify(b'FFD8FFD8'),
                   binascii.unhexlify(b'FFD8FFE0'),
                   binascii.unhexlify(b'FFD8FFE1')]

with open('file.jpeg', 'rb') as fl:
    first_four = file.read(4)
    if first_four in jpeg_signatures:
        print("Nice JPEG.")
    else:
        print("Caution, something is wrong.")
'''
