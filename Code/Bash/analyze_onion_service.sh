#!/bin/bash

# Start tor:
service tor start

# Prepare socat:
# Onion URL without protocol. Ex:bashdbajshbdasjhdbaifgbsdiyfsdg.onion:80
socat TCP4-LISTEN:8000,reuseaddr,fork SOCKS4A:127.0.0.1:ONIONURL:PORT,socksport=9050

# Use with localhost:80. Ex:
curl 127.0.0.1:80
