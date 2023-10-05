import subprocess
import json
import sys

def find_phishing_domains(target_domain):
    try:
        # Run dnstwist and capture the output
        result = subprocess.run(['dnstwist', '--json', target_domain], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Check for errors
        if result.returncode != 0:
            print(f"Error running dnstwist: {result.stderr.decode('utf-8')}")
            return None
        
        output = result.stdout.decode('utf-8')
        
        # Parse the JSON output
        domain_data = json.loads(output)
        
    except json.JSONDecodeError:
        print("Error decoding JSON output from dnstwist.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
    
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
    if len(sys.argv) < 2:
        print("Usage: python {0} <target_domain>".format(sys.argv[0]))
        sys.exit(1)
    
    target_domain = sys.argv[1]
    phishing_domains = find_phishing_domains(target_domain)
    
    if phishing_domains:
        print("Potential phishing domains found:")
        for domain in phishing_domains:
            print(f"Domain: {domain['domain']}, IP: {domain['dns-a']}")
    else:
        print("No potential phishing domains found.")
