#!/usr/bin/env python3
"""
Enhanced Tor Exit Node Safety Checker
Features: Concurrent DNSBL checks, Tor DNS resolution, risk assessment, port autodetection
Requires: requests, pysocks, dnspython, colorama
"""

import requests
import socket
import concurrent.futures
import time
import sys
import dns.resolver
from colorama import Fore, Style, init
from socks import PROXY_TYPE_SOCKS5, socksocket
from socks import set_default_proxy

# Initialize colorama
init(autoreset=True)

# Expanded DNS Blocklists
BLOCKLISTS = {
    'tor.dan.me.uk': '127.0.0.2',
    'dnsbl.torproject.org': '127.0.0.2',
    'rbl.efnetrbl.org': '127.0.0.2',
    'bl.spamcop.net': '127.0.0.2',
    'psbl.surriel.com': '127.0.0.2',
    'all.s5h.net': '127.0.0.2'
}

class Spinner:
    """Animated spinner for progress indication"""
    def __init__(self, message):
        self.message = message
        self.chars = ['⣾','⣽','⣻','⢿','⡿','⣟','⣯','⣷']
        self.delay = 0.1
        self.running = False
        
    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self.animate)
        self.thread.start()
        return self
        
    def animate(self):
        index = 0
        while self.running:
            sys.stdout.write(f"\r{Fore.YELLOW}{self.chars[index]} {self.message}")
            sys.stdout.flush()
            index = (index + 1) % len(self.chars)
            time.sleep(self.delay)
            
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.running = False
        self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()

def get_tor_proxy(ports=[9050, 9150]):
    """Detect active Tor proxy port with fallback"""
    for port in ports:
        try:
            test_sock = socksocket()
            test_sock.set_proxy(PROXY_TYPE_SOCKS5, "127.0.0.1", port)
            test_sock.settimeout(2)
            test_sock.connect(("check.torproject.org", 80))
            test_sock.close()
            return port
        except:
            continue
    return None

def get_current_exit_ip(tor_port):
    """Get current exit node IP through Tor with validation"""
    proxies = {
        'http': f'socks5h://127.0.0.1:{tor_port}',
        'https': f'socks5h://127.0.0.1:{tor_port}'
    }
    
    try:
        with Spinner("Identifying Tor exit node"):
            response = requests.get(
                'https://check.torproject.org/api/ip', 
                proxies=proxies,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:102.0) Gecko/20100101 Firefox/102.0'}
            )
        ip_data = response.json()
        return ip_data['IP']
    except Exception as e:
        print(f"\n{Fore.RED}✖ Error getting IP: {e}")
        sys.exit(1)

def check_tor_consensus(ip, tor_port):
    """Check Tor network consensus with detailed node info"""
    try:
        proxies = {'https': f'socks5h://127.0.0.1:{tor_port}'}
        
        with Spinner("Checking Tor network consensus"):
            response = requests.get(
                f"https://onionoo.torproject.org/details?search={ip}",
                proxies=proxies,
                timeout=15
            )
        data = response.json()
        
        if 'relays' in data and data['relays']:
            relay = data['relays'][0]
            return {
                'nickname': relay.get('nickname', 'Unknown'),
                'running': 'Running' in relay.get('flags', []),
                'exit': 'Exit' in relay.get('flags', []),
                'badexit': 'BadExit' in relay.get('flags', []),
                'guard': 'Guard' in relay.get('flags', []),
                'hibernating': 'Hibernating' in relay.get('flags', []),
                'consensus_weight': relay.get('consensus_weight', 0),
                'bandwidth': relay.get('observed_bandwidth', 0),
                'country': relay.get('country', 'XX'),
                'as': relay.get('as', 'Unknown')
            }
    except Exception as e:
        print(f"\n{Fore.RED}Consensus check error: {e}")
    return None

def check_dnsbl(bl, ip, tor_port):
    """Check single DNS blocklist through Tor"""
    reversed_ip = '.'.join(ip.split('.')[::-1])
    query = f"{reversed_ip}.{bl}"
    
    try:
        # Create Tor-aware resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['127.0.0.1']  # Use local Tor proxy
        resolver.port = tor_port
        
        # Set Tor proxy for DNS resolution
        set_default_proxy(PROXY_TYPE_SOCKS5, "127.0.0.1", tor_port)
        dns.resolver.override_system_resolver(resolver)
        
        answers = resolver.resolve(query, 'A')
        return any(str(r) == BLOCKLISTS[bl] for r in answers)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except Exception:
        return None

def check_all_dnsbls(ip, tor_port):
    """Concurrent DNS blocklist checking"""
    results = {}
    with Spinner("Checking DNS blocklists"), concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_bl = {executor.submit(check_dnsbl, bl, ip, tor_port): bl for bl in BLOCKLISTS}
        for future in concurrent.futures.as_completed(future_to_bl):
            bl = future_to_bl[future]
            results[bl] = future.result()
    return results

def calculate_risk(consensus, dns_results):
    """Comprehensive risk assessment"""
    if not consensus:
        return "UNKNOWN", "Consensus data unavailable"
    
    if consensus.get('badexit'):
        return "HIGH", "BadExit flag detected in Tor consensus"
    
    if any(dns_results.values()):
        return "MEDIUM", "Listed on one or more blocklists"
    
    if consensus.get('hibernating'):
        return "LOW", "Node is hibernating (reduced reliability)"
        
    if consensus.get('exit') and consensus.get('guard'):
        return "LOW", "Trusted Guard+Exit node"
    
    return "LOW", "No significant risk indicators"

def print_summary(ip, consensus, dns_results, risk, reason):
    """Color-coded summary with detailed information"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}✦ TOR EXIT NODE ANALYSIS REPORT")
    print(f"{Fore.CYAN}{'='*60}")
    
    # Risk level display
    risk_color = Fore.GREEN if risk == "LOW" else Fore.YELLOW if risk == "MEDIUM" else Fore.RED
    print(f"\n{risk_color}➤ RISK LEVEL: {risk} - {reason}")
    
    # IP information
    print(f"\n{Fore.WHITE}➤ EXIT NODE: {Fore.CYAN}{ip}")
    
    # Consensus details
    if consensus:
        print(f"\n{Fore.WHITE}➤ TOR NETWORK DATA:")
        status = f"{Fore.GREEN}Active" if consensus['running'] else f"{Fore.RED}Inactive"
        print(f"  Status: {status}{Style.RESET_ALL}")
        print(f"  Nickname: {Fore.CYAN}{consensus['nickname']}")
        print(f"  Flags: {' '.join([f'{Fore.GREEN if f in ["Exit", "Guard"] else Fore.RED}{f}' for f in ['Exit', 'Guard', 'BadExit', 'Hibernating'] if consensus.get(f.lower())])}")
        print(f"  Location: {consensus['country']} (AS{consensus['as']})")
        print(f"  Bandwidth: {consensus['bandwidth']:,} KB/s")
        print(f"  Network Weight: {consensus['consensus_weight']:,} (trust)")
    
    # Blocklist results
    print(f"\n{Fore.WHITE}➤ BLOCKLIST REPUTATION:")
    for bl, result in dns_results.items():
        status = f"{Fore.RED}🚨 LISTED" if result is True else f"{Fore.GREEN}✅ CLEAN" if result is False else f"{Fore.YELLOW}❓ ERROR"
        print(f"  {bl:<25}: {status}")
    
    # Recommendations
    print(f"\n{Fore.WHITE}➤ RECOMMENDATIONS:")
    if risk == "HIGH":
        print(f"  {Fore.RED}• Immediately request new Tor circuit (Ctrl+Shift+L)")
        print(f"  {Fore.RED}• Avoid sensitive activities")
    elif risk == "MEDIUM":
        print(f"  {Fore.YELLOW}• Consider requesting new Tor circuit")
        print(f"  {Fore.YELLOW}• Stick to HTTPS and .onion sites")
    else:
        print(f"  {Fore.GREEN}• Normal Tor usage is safe")
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Style.DIM}Report generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Style.DIM}Always use Tor Browser and .onion services for maximum privacy")

def main():
    print(f"\n{Fore.BLUE}🔍 Starting Tor Exit Node Safety Analysis\n")
    
    # Detect Tor port
    with Spinner("Detecting Tor service"):
        tor_port = get_tor_proxy()
    if not tor_port:
        print(f"\n{Fore.RED}✖ Tor proxy not found! Ensure Tor is running on 9050/9150")
        sys.exit(1)
    print(f"\n{Fore.GREEN}✓ Tor detected on port {tor_port}")
    
    # Get current exit IP
    current_ip = get_current_exit_ip(tor_port)
    print(f"{Fore.GREEN}✓ Current Exit IP: {Fore.CYAN}{current_ip}")
    
    # Get consensus data
    consensus = check_tor_consensus(current_ip, tor_port)
    
    # Check blocklists
    dns_results = check_all_dnsbls(current_ip, tor_port)
    
    # Calculate risk
    risk_level, risk_reason = calculate_risk(consensus, dns_results)
    
    # Print final report
    print_summary(current_ip, consensus, dns_results, risk_level, risk_reason)

if __name__ == "__main__":
    import threading
    main()
