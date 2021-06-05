import platform
import socket
import nmap

# Platform
op_sys = platform.system()
arch = platform.architecture()
user_name = platform.os.getlogin()
network_name = platform.node()

# Network
def scan_local_hosts():
    port_scanner = nmap.PortScanner()
    live_hosts = {'cabled':[], 'wifi':[]}
    # Cabled:
    host_info = port_scanner.scan("192.168.1.0/24", arguments="-p 22 --open")
    for host in host_info['scan']:
        if port_scanner[host].state() == "up":
            live_hosts['cabled'].append(host)
    # Wifi:
    host_info = port_scanner.scan("10.0.0.0/200", arguments="-p 22 --open")
    for host in host_info['scan']:
        if port_scanner[host].state() == "up":
            live_hosts['wifi'].append(host)
    # Return
    return live_hosts

internal_ip = socket.gethostbyname(socket.gethostname())
