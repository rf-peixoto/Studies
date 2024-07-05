import socket
import sys
import json
import threading
import time
import random
import struct
from scapy.all import *

def create_tcp_socket():
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def save_log(log_data, filename):
    with open(filename, 'a') as log_file:
        json.dump(log_data, log_file)
        log_file.write('\n')

def server_mode(host, port):
    server_socket = create_tcp_socket()
    server_socket.bind((host, port))
    server_socket.listen(5)
    print(f"Server listening on {host}:{port}")
    
    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Connection from {client_address}")
            threading.Thread(target=handle_client, args=(client_socket,)).start()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
        server_socket.close()

def handle_client(client_socket):
    try:
        while True:
            data = client_socket.recv(4096)
            if not data:
                break
            log_data = {
                'timestamp': time.time(),
                'received_data': data.hex(),
                'remote_address': client_socket.getpeername(),
                'status': 'received'
            }
            print(f"Received: {data}")
            save_log(log_data, 'server_log.json')
    except Exception as e:
        log_data = {
            'timestamp': time.time(),
            'error': str(e),
            'remote_address': client_socket.getpeername(),
            'status': 'error'
        }
        save_log(log_data, 'server_log.json')
    finally:
        client_socket.close()

def client_mode(host, port):
    try:
        client_socket = create_tcp_socket()
        client_socket.connect((host, port))
        print(f"Connected to server at {host}:{port}")
        
        while True:
            payload = random.choice([
                generate_payload(),
                fuzz_tcp_packet(),
                corrupt_packet(),
                invalid_header_length_packet(),
                random_flags_packet(),
                syn_flood_packet(),
                malformed_checksum_packet(),
                fragmented_packet(),
                overlap_fragment_packet(),
                invalid_sequence_ack_packet(),
                handshake_test()
            ])
            try:
                client_socket.send(payload)
                log_data = {
                    'timestamp': time.time(),
                    'sent_data': payload.hex(),
                    'remote_address': (host, port),
                    'status': 'sent'
                }
                print(f"Sent: {payload}")
            except Exception as e:
                log_data = {
                    'timestamp': time.time(),
                    'error': str(e),
                    'remote_address': (host, port),
                    'status': 'error'
                }
            save_log(log_data, 'client_log.json')
            time.sleep(random.uniform(0.05, 0.5))
    except KeyboardInterrupt:
        print("\nClient shutting down.")
    finally:
        client_socket.close()

def generate_payload():
    payload_types = [
        b'\x00' * 1024,  # Null bytes
        b'\xff' * 1024,  # All 1s
        b'\x55' * 1024,  # Alternating bits
        b'\xaa' * 1024,  # Alternating bits inverse
        random.randbytes(1024),  # Random data
        struct.pack('!I', random.randint(0, 0xFFFFFFFF)),  # Random integer
        struct.pack('!H', random.randint(0, 0xFFFF)),  # Random short
        struct.pack('!f', random.random()),  # Random float
        bytes(random.getrandbits(8) for _ in range(1024)),  # Random bytes
        bytes.fromhex(''.join(random.choice('0123456789ABCDEF') for _ in range(2048))),  # Random hex
        b'\x00' * random.randint(1, 1024),  # Variable length null bytes
        b'\xff' * random.randint(1, 1024),  # Variable length all 1s
        struct.pack('!d', random.random()),  # Random double
        b'\xAB' * 1024,  # Repeated pattern
        bytes(bytearray(random.choices([0x00, 0xff, 0x55, 0xaa], k=1024))),  # Mixed patterns
        struct.pack('!Q', random.randint(0, 0xFFFFFFFFFFFFFFFF))  # Random long integer
    ]
    return random.choice(payload_types)

def fuzz_tcp_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345)
    options = [
        ("MSS", random.randint(0, 1460)),
        ("SAckOK", b''),
        ("Timestamp", (random.randint(0, 4294967295), random.randint(0, 4294967295))),
        ("NOP", None),
        ("WScale", random.randint(0, 14)),
        ("EOL", None),  # End of Option List
        ("", b'')  # Empty option
    ]
    tcp.options = random.sample(options, k=random.randint(0, len(options)))
    return bytes(ip/tcp)

def corrupt_packet():
    ip = IP(dst="127.0.0.1", ttl=random.randint(0, 255))
    tcp = TCP(dport=12345, flags=random.choice(['S', 'A', 'R', 'F', 'P', 'U', 'E', 'C']))
    corrupt_data = bytes(random.getrandbits(8) for _ in range(random.randint(1, 1024)))
    return bytes(ip/tcp/corrupt_data)

def invalid_header_length_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345, dataofs=random.randint(0, 15))
    return bytes(ip/tcp)

def random_flags_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345, flags=random.getrandbits(8))
    return bytes(ip/tcp)

def syn_flood_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345, flags='S', seq=random.randint(0, 0xFFFFFFFF))
    return bytes(ip/tcp)

def malformed_checksum_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345, chksum=random.randint(0, 0xFFFF))
    return bytes(ip/tcp)

def fragmented_packet():
    ip = IP(dst="127.0.0.1", flags='MF', frag=0)
    tcp = TCP(dport=12345)
    fragment1 = bytes(ip/tcp)
    ip = IP(dst="127.0.0.1", flags=0, frag=1)
    tcp = TCP(dport=12345)
    fragment2 = bytes(ip/tcp)
    return fragment1 + fragment2

def overlap_fragment_packet():
    ip = IP(dst="127.0.0.1", flags='MF', frag=0)
    tcp = TCP(dport=12345)
    fragment1 = bytes(ip/tcp)
    ip = IP(dst="127.0.0.1", flags='MF', frag=0)
    tcp = TCP(dport=12345)
    fragment2 = bytes(ip/tcp)
    return fragment1 + fragment2

def invalid_sequence_ack_packet():
    ip = IP(dst="127.0.0.1")
    tcp = TCP(dport=12345, seq=random.randint(0, 0xFFFFFFFF), ack=random.randint(0, 0xFFFFFFFF))
    return bytes(ip/tcp)

def handshake_test():
    ip = IP(dst="127.0.0.1")
    tcp_syn = TCP(dport=12345, flags='S', seq=random.randint(0, 0xFFFFFFFF))
    syn_packet = bytes(ip/tcp_syn)

    tcp_ack = TCP(dport=12345, flags='A', seq=random.randint(0, 0xFFFFFFFF), ack=random.randint(0, 0xFFFFFFFF))
    ack_packet = bytes(ip/tcp_ack)
    
    return syn_packet + ack_packet

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <server|client> <host> <port>")
        sys.exit(1)

    mode = sys.argv[1]
    host = sys.argv[2]
    port = int(sys.argv[3])

    if mode == 'server':
        server_mode(host, port)
    elif mode == 'client':
        try:
            client_socket = create_tcp_socket()
            client_socket.connect((host, port))
            print(f"Connected to server at {host}:{port}")

            while True:
                payload = random.choice([
                    generate_payload(),
                    fuzz_tcp_packet(),
                    corrupt_packet(),
                    invalid_header_length_packet(),
                    random_flags_packet(),
                    syn_flood_packet(),
                    malformed_checksum_packet(),
                    fragmented_packet(),
                    overlap_fragment_packet(),
                    invalid_sequence_ack_packet(),
                    handshake_test()
                ])
                try:
                    client_socket.send(payload)
                    log_data = {
                        'timestamp': time.time(),
                        'sent_data': payload.hex(),
                        'remote_address': (host, port),
                        'status': 'sent'
                    }
                    print(f"Sent: {payload}")
                except Exception as e:
                    log_data = {
                        'timestamp': time.time(),
                        'error': str(e),
                        'remote_address': (host, port),
                        'status': 'error'
                    }
                save_log(log_data, 'client_log.json')
                time.sleep(random.uniform(0.05, 0.5))
        except KeyboardInterrupt:
            print("\nClient shutting down.")
        finally:
            client_socket.close()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
