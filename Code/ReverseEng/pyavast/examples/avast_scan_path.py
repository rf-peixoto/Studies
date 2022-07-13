import sys
import pprint
from pyavast import CAvastInterface

def main(path):
  avast = CAvastInterface()
  avast.connect()
  pprint.pprint(avast.scan_path(path))

def usage():
  print "Usage:", sys.argv[0], "<path to analyse>"

if __name__ == "__main__":
  if len(sys.argv) == 1:
    usage()
  else:
    main(sys.argv[1])
