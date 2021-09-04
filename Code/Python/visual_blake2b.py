# ~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#   Blake2b Hash Viewer      #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~ #
import sys
from hashlib import blake2b

def get_hash(content: str) -> str:
    return blake2b(content.encode()).hexdigest()

def ripstr(string: str, part_size=8) -> list:
    return [string[i:i + part_size] for i in range(0, len(string), part_size)]

def print_out(hash_values: list):
    for value in hash_values:
        if hash_values.index(value) in [3, 7, 11, 15]:
            print("{0}".format(value))
        else:
            print("{0} ".format(value), end="")


print(" -----BLAKE2B START-----\n")
print_out(ripstr(get_hash(sys.argv[1])))
print("\n -----END-----\n")
