#!/bin/bash

# Restart the daemon after this:
echo "TransPort 127.0.0.1:9040" >> /etc/tor/torrc

# Redirect your stuff to the tor port:
sudo iptables -t nat -A OUTPUT -p TCP -m owner ! --uid-owner tor -j DNAT --to-destination 127.0.0.1:9040 
