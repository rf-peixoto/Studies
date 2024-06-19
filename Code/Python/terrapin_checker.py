# CVE-2023-48795 Terrapin

import subprocess
import sys

# Define the remote server IP address
remote_server_ip = sys.argv[1]

# Run ssh-audit command
result = subprocess.run(['ssh-audit', remote_server_ip], capture_output=True, text=True)

# Output the result
output = result.stdout
print(output)

# Check for vulnerable ciphers and MACs
vulnerable_ciphers = ['chacha20-poly1305@openssh.com']
vulnerable_macs = ['hmac-sha2-256-etm@openssh.com']

# Parse the output to find supported ciphers and MACs
supported_ciphers = []
supported_macs = []

for line in output.splitlines():
    if line.startswith(' (cipher)'):
        supported_ciphers.append(line.split()[1])
    elif line.startswith(' (mac)'):
        supported_macs.append(line.split()[1])

# Check for vulnerabilities
vulnerable_cipher_found = any(cipher in supported_ciphers for cipher in vulnerable_ciphers)
vulnerable_mac_found = any(mac in supported_macs for mac in vulnerable_macs)

if vulnerable_cipher_found:
    print("Vulnerable ciphers detected!")
else:
    print("No vulnerable ciphers detected.")

if vulnerable_mac_found:
    print("Vulnerable MACs detected!")
else:
    print("No vulnerable MACs detected.")
