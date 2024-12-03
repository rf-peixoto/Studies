# Border Gateway Protocol (BGP) checker

import sys
from scapy.all import *
from scapy.contrib.bgp import *

# Create a TCP SYN packet to port 179
syn = IP(dst=sys.argv[1]) / TCP(dport=179, flags="S")
synack = sr1(syn, timeout=2)  # Send and wait for a SYN-ACK

if synack and synack[TCP].flags == "SA":
    print("TCP port 179 is open. Crafting BGP OPEN message.")
    # Build a BGP OPEN message
    open_msg = BGPHeader(type=1) / BGPOpen(version=4, asn=65000, hold_time=180, bgp_id="192.0.2.1")
    bgp_pkt = IP(dst=sys.argv[1]) / TCP(dport=179, sport=synack[TCP].sport, seq=synack[TCP].ack, ack=synack[TCP].seq + 1, flags="PA") / open_msg
    send(bgp_pkt)
else:
    print("TCP port 179 is not responsive.")
