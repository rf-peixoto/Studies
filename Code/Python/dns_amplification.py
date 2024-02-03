from scapy.all import *
import random
import threading

def random_ipv4():
    """Generate a random IPv4 address."""
    return ".".join(str(random.randint(0, 255)) for _ in range(4))

def send_custom_ping(src_ip, dst_ip, payload):
    """
    Send a custom ICMP ping packet.

    Parameters:
    - src_ip: Source IP address as a string.
    - dst_ip: Destination IP address as a string.
    - payload: Payload data as a string.
    """
    ip_layer = IP(src=src_ip, dst=dst_ip)
    icmp_layer = ICMP(type=8, code=0)  # Type 8, Code 0 for Echo Request
    packet = ip_layer / icmp_layer / payload
    send(packet, verbose=0)  # Set verbose=0 to minimize console output

def ping_thread(src_ip, payload):
    """
    Thread function for sending a single ping with a random destination IP.

    Parameters:
    - src_ip: Source IP address as a string.
    - payload: Payload data as a string.
    """
    dst_ip = random_ipv4()  # Generate a random destination IP address
    send_custom_ping(src_ip, dst_ip, payload)

def main_loop(src_ip, payload, count):
    """
    Send custom ICMP ping packets in a loop with random destination IP using threading.

    Parameters:
    - src_ip: Source IP address as a string.
    - payload: Payload data as a string.
    - count: Number of times to send the ping packet.
    """
    threads = []
    for _ in range(count):
        t = threading.Thread(target=ping_thread, args=(src_ip, payload))
        t.start()
        threads.append(t)
    
    # Wait for all threads to complete
    for t in threads:
        t.join()

# Example usage
if __name__ == "__main__":
    src_ip = "192.168.1.100"  # Example source IP, adjust as needed
    payload = "Custom payload data" * 30000  # Custom payload data
    count = 1000  # Number of ping packets to send

    main_loop(src_ip, payload, count)
