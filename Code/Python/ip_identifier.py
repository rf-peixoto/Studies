import socket
import csv
import time
from ipwhois import IPWhois
from ipwhois.exceptions import IPDefinedError, HTTPLookupError, HostLookupError

def get_ip_info(ip):
    """Get hostname and organization for an IP address"""
    # Get hostname via reverse DNS
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror):
        hostname = "N/A"
    
    # Get organization via WHOIS
    try:
        obj = IPWhois(ip)
        result = obj.lookup_rdap(depth=1)
        org = result.get('asn_description', result.get('network', {}).get('name', 'N/A'))
    except (IPDefinedError, HTTPLookupError, HostLookupError, ValueError):
        org = "N/A"
    
    return hostname, org

def main():
    # Read IPs from file
    with open('ips.txt', 'r') as f:
        ips = [line.strip() for line in f if line.strip()]
    
    # Process IPs and write results
    with open('ip_report.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['IP Address', 'Hostname', 'Organization'])
        
        for i, ip in enumerate(ips):
            print(f"Processing {i+1}/{len(ips)}: {ip}")
            hostname, org = get_ip_info(ip)
            writer.writerow([ip, hostname, org])
            time.sleep(1)  # Avoid rate limiting

if __name__ == "__main__":
    main()
