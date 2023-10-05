# Import required modules
import subprocess
import json
import sys

def find_phishing_domains(target_domain):
    # Run dnstwist and capture the output
    result = subprocess.run(['dnstwist', '--json', target_domain], stdout=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    
    # Parse the JSON output
    domain_data = json.loads(output)
    
    # List to store potential phishing domains
    phishing_domains = []
    
    for domain in domain_data:
        # Check if the domain is already registered
        if domain['dns-a']:
            phishing_domains.append({
                'domain': domain['domain-name'],
                'dns-a': domain['dns-a']
            })
    
    return phishing_domains

if __name__ == "__main__":
    target_domain = sys.argv[1]
    phishing_domains = find_phishing_domains(target_domain)
    
    if phishing_domains:
        print("Potential phishing domains found:")
        for domain in phishing_domains:
            print(f"Domain: {domain['domain']}, IP: {domain['dns-a']}")
    else:
        print("No potential phishing domains found.")
