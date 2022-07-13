#!/usr/bin/python
# -*- coding: utf-8 -*-

#-----------------------------------------------------------------------
# PyAvast, Avast bindings for Python 0.0.1
# Copyright (c) 2014, Joxean Koret
#
# Python bindings for the "new linux Avast server product line for 2014"
# See this URL for more details about this version:
#
#   http://forum.avast.com/index.php?topic=145973.0
#
# License:
#
# PyAvast is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser Public License as published by the 
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
# 
# PyAvast is distributed in the hope that it will be  useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#-----------------------------------------------------------------------

import re
import sys
import socket
import StringIO

#-----------------------------------------------------------------------
class CAvastInterface:
  def __init__(self):
    self.s = None
    self.banner = None

  def connect(self, sock_name="/var/run/avast/scan.sock"):
    """ Connect to the Unix socket. """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_name)
    self.s = s
    return s.recv(1024)

  def to_dict(self, buf):
    """ Convert the returned buffer for a malware scan to a python dict.
    """
    sio = StringIO.StringIO(buf)
    d = {}
    for line in sio.readlines():
      if line.startswith("210 SCAN DATA"):
        continue
      elif line.startswith("200 SCAN OK"):
        continue

      line = line.strip("\n").strip("\r")
      args = line.split("\t")
      malware_name = None

      if len(args) > 2:
        # Is the file excluded?
        if args[1].startswith("[E]"):
          continue

        new_args = line[line.find("\t")+1:]
        new_args = new_args.split(" ")
        if len(new_args) > 0:
          if new_args[-1].startswith("["):
            malware_name = new_args[len(new_args)-2]
          else:
            malware_name = new_args[-1]
          if malware_name.endswith("\\"):
            malware_name = malware_name.strip("\\")

      filename = args[0][5:]
      d[filename] = malware_name
    return d

  def read_answer(self):
    """ Read the whole answer from the Unix socket. """
    ret = []
    while 1:
      buf = self.s.recv(1024)
      ret.append(buf)
      if buf.endswith("200 SCAN OK\r\n"):
        break
    return self.to_dict("".join(ret))

  def scan_path(self, path):
    """ Scan a given path or file. """
    line = "SCAN %s\n" % path
    self.s.send(line)
    return self.read_answer()

  def check_url(self, url):
    """ Check if the URL is blocked or not. """
    line = "CHECKURL %s\n" % url
    self.s.send(line)
    ret = self.s.recv(1024)
    if ret.startswith("200"):
      return True
    elif ret.startswith("520"):
      return False
    else:
      raise Exception("Unknown error code: %s" % ret)

  def get_pack(self):
    """ Retrieve the list of supported compressors and their state. """
    self.s.send("PACK\n")
    sio = StringIO.StringIO(self.s.recv(1024))
    for line in sio.readlines():
      if line.startswith("210"):
        continue
      elif line.startswith("200"):
        continue
      line = line.strip("\n").strip("\r")
      packers = line[5:].split(" ")
      d = {}
      for packer in packers:
        d[packer[1:]] = packer[0] == "+"
      break
    return d
  
  def set_pack(self, packers):
    """ Set the enabled/disabled list of compressors. """
    line = ""
    for packer in packers:
      if packers[packer]:
        char = "+"
      else:
        char = "-"
      line += "%s%s " % (char, packer)
    self.s.send("PACK %s\n" % line)
    ret = self.s.recv(1024)
    return
  
  def exclude(self, what):
    """ Exclude a file or a path from a malware scan. """
    self.s.send("EXCLUDE %s\n" % what)
    ret = self.s.recv(1024)
    return

#-----------------------------------------------------------------------
def usage():
  print "Usage:", sys.argv[0], "<path>"

#-----------------------------------------------------------------------
def main(args):
  avast = CAvastInterface()
  avast.connect()

  # Get the list of supported compressors and their state
  l = avast.get_pack()
  print l
  # Disable OLE
  l["ole"] = False
  avast.set_pack(l)
  # Check the list again
  print avast.get_pack()
  
  # Testing with malwares
  print "GOODWARE", avast.scan_path("/etc/hosts")
  print "GIVEN", avast.scan_path(args)
  
  # Exclude now /etc/hosts and scan it again
  avast.exclude("/etc/hosts")
  print "EXCLUDED GOODWARE?", avast.scan_path("/etc/hosts")

  # Testing with malware URLs
  import urllib2
  r = urllib2.urlopen("http://malwareurls.joxeankoret.com/normal.txt")
  for url in r.readlines():
    if url.startswith("#"):
      continue
    url = url.strip("\n").strip("\n")
    try:
      ret = avast.check_url(url)
    except:
      print "URL", repr(url)
      raise

    if not ret:
      print "BLOCKED", url, ret

  print "GOOGLE.COM is good?", avast.check_url("http://www.google.com")

if __name__ == "__main__":
  if len(sys.argv) == 1:
    usage()
  else:
    main(sys.argv[1])
