# Ref: Antivirus Hacker's Handbook
import os
import sys
import random
from hashlib import md5

# -------------------------------------------------------------------- $
class Fuzzer:
    def __init__(self, input_file, output_path, cmd):
        self.input_file = input_file
        self.output_path = output_path
        self.cmd = cmd

    def mutate(self, buf):
        tmp = bytearray(buf)
        # Calculate total changes to be made:
        total_changes = random.randint(1, len(tmp))
        for i in range(total_changes):
            # Get random position on file:
            pos = random.randint(0, len(tmp) - 1)
            # Define random charactere to replace:
            char = chr(random.randint(0, 255))
            # Replace value on that position:
            tmp[pos] = char
        return str(tmp)

    def fuzz(self):
        orig_buf = open(self.input_file, "rb").read()
        # Create 255 mutations:
        for i in range(255):
            buf = self.mutate(orig_buf)
            md5_hash = md5(buf).hexdigest()
            print("[+] Writing mutate file %s" % repr(md5_hash))
            filename = os.path.join(self.output_path, md5_hash)
            with open(filename, "wb") as f:
                f.write(buf)
        # Run command:
        cmd = "{0} {1}".format(self.cmd, self.output_path)
        os.system(cmd)
# -------------------------------------------------------------------- $
def main(input, output, cmd):
    fuzzer = Fuzzer(input, output, cmd)
    fuzzer.fuzz()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("{0} <input file> <output folder> '<command>'")
    else:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
