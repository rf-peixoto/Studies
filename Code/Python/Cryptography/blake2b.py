import sys
from hashlib import blake2b

if sys.argv[1]:
    print("[+] {0}".format(blake2b(sys.argv[1].encode()).hexdigest()))
else:
    print("Usage: {0} [Content]".format(sys.argv[0]))
