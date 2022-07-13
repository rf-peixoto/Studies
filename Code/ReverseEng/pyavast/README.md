PyAvast

Original repo: https://github.com/joxeankoret/pyavast
=======

Python bindings for the "new linux Avast server product line for 2014".
See this URL for more details about this version:

   http://forum.avast.com/index.php?topic=145973.0

The bindings require the Linux Avast daemon to be running in the same
machine. They will connect to the local Unix socket /var/run/avast/scan.sock
where the Avast daemon is listening for client connections.

Features
========

The current bindings offer the following features:

 * Scanning files and/or directories.
 * Checking URLs.
 * Get and set the list of enabled or disabled compressors.
 * Set the files or paths to exclude.

Example usages
==============

The Python API to communicate with the Avast server is rather easy. The
following is a complete working example:

```
# File: avast_scan_path.py
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

```

In this example we create a ```CAvastInterface``` object, connect to the local
Unix socket where it's listening and instructs it to scan the given path.
Easy, isn't it? We can also check URLs instead of local directories or 
files using the method call ```check_url()```, as in the following example:

```
# File: avast_url_check.py
import sys
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
```

As you can see, the only real change with the previous example is that we're
calling ```check_url()``` instead of ```scan_path```.

Contact
=======

Copyright (c) 2014 Joxean Koret, &lt;joxeankoret AT yahoo DOT es&gt;
