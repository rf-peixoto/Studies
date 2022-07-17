# Ref: The Antivirus Hacker's Handbook
# This script reaks the file into parts incrementally.
# It creates many smaller files, with a size incremented
# by N bytes for each file.

import os, sys, time

def log(msg):
    print("[%s] %s" % (time.asciitime(), msg))

class CSplitter:
    def __init__(self, filename: str, block_size: int):
        self.buffer = open(filename, "rb").read()
        self.block = block_size

    def split(self, path):
        blocks = len(self.buffer) / self.block
        for i in xrange(1, blocks):
            buf = self.buffer[:i * self.block]
            out_path = os.path.join(path, "block_%d" % i)
            log("Writing file %s for %d (until offset 0x%x)" % \ (path, i, self.block_size * i))
            f = open(out_path, "wb")
            f.write(buf)
            f.close()

def main(in_path, out_path, block_size):
    splitter = CSplitter(in_path, block_size)
    splitter.split(out_path)

def usage():
    print("Usage: {0} <input file> <output path> <block size>".format(sys.argv[0]))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        usage()
    else:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
