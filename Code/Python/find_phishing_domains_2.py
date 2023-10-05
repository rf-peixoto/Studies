import subprocess
import sys
import re

def find_phishing_domains(target_domain):
    try:
        # Run dnstwist and capture the output
        result = subprocess.run(['dnstwist', target_domain], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Check for errors
        if result.returncode != 0:
            print(f"Error running dnstwist: {result.stderr.decode('utf-8')}")
            return None
        
        output = result.stdout.decode('utf-8')
        
        # Regular expression to extract domain and IP address
        regex = re.compile(r'(\S+\.\S+)\s+.*\s+(\d+\.\d+\.\d+\.\d+)')
        matches = regex.findall(output)
        
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
    
    # List to store potential phishing domains
    phishing_domains = []
    
    for match in matches:
        domain, ip_address = match
        if domain != target_domain:  # Exclude the original domain
            phishing_domains.append({
                'domain': domain,
                'dns-a': ip_address
            })
    
    return phishing_domains

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_domains.py <target_domain>")
        sys.exit(1)
    
    target_domain = sys.argv[1]
    phishing_domains = find_phishing_domains(target_domain)
    
    if phishing_domains:
        print("Potential phishing domains found:")
        for domain in phishing_domains:
            print(f"Domain: {domain['domain']}, IP: {domain['dns-a']}")
    else:
        print("No potential phishing domains found.")
