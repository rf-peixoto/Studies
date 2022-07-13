# File: avast_url_check.py
import sys
import pprint
from pyavast import CAvastInterface

def main(path):
  avast = CAvastInterface()
  avast.connect()
  if avast.check_url(path):
    print "Good"
  else:
    print "Blocked"

def usage():
  print "Usage:", sys.argv[0], "<URL to check>"

if __name__ == "__main__":
  if len(sys.argv) == 1:
    usage()
  else:
    main(sys.argv[1])
