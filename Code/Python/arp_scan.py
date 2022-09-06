from scapy.all import Ether, ARP, srp

ether_layer = Ether(dst="FF:FF:FF:FF:FF:FF") # broadcast
ip_range = "192.168.0.1/24"
arp_layer = ARP(pdst=ip_range)

packet = ether_layer / arp_layer

ans, unans = srp(packet, iface="eth0", timeout=2)

for snd, rcv in ans:
    ip = rcv[ARP].psrc
    mac = rcv[Ether].src
    print("IP: {0}\tMAC: {1}".format(ip, mac))
