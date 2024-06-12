# pip install requests beautifulsoup4 dnspython whois schedule builtwith

import requests
import json
import socket
import ssl
import whois
from bs4 import BeautifulSoup
import time
import schedule
import builtwith

# Customizable Variables
DOMAINS_FILE = 'domains.txt'
CHECK_INTERVAL = 86400  # Time in seconds (86400 seconds = 24 hours)
OUTPUT_DIR = './data/'

# Function to get IP address
def get_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except socket.error as e:
        return str(e)

# Function to get SSL certificate details
def get_ssl_info(domain):
    context = ssl.create_default_context()
    try:
        with context.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.connect((domain, 443))
            cert = s.getpeercert()
        return cert
    except Exception as e:
        return str(e)

# Function to get page title
def get_page_title(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.title.string if soup.title else 'No title found'
    except Exception as e:
        return str(e)

# Function to get WHOIS information
def get_whois_info(domain):
    try:
        whois_info = whois.whois(domain)
        return whois_info
    except Exception as e:
        return str(e)

# Function to detect technologies using BuiltWith
def detect_technologies(url):
    try:
        return builtwith.parse(url)
    except Exception as e:
        return str(e)

# Function to gather all details for a domain
def gather_domain_details(url):
    domain = url.replace('https://', '').replace('http://', '').split('/')[0]
    print(f"Processing domain: {domain}")
    details = {
        'domain': domain,
        'url': url,
        'ip_address': get_ip(domain),
        'ssl_info': get_ssl_info(domain),
        'page_title': get_page_title(url),
        'whois_info': get_whois_info(domain),
        'technologies': detect_technologies(url)
    }
    return details

# Function to save details to a JSON file
def save_to_json(domain_details, output_dir):
    domain = domain_details['domain']
    with open(f'{output_dir}{domain}.json', 'w') as f:
        json.dump(domain_details, f, indent=4)

# Function to read domains from file
def read_domains(file_path):
    with open(file_path, 'r') as file:
        domains = [line.strip() for line in file.readlines()]
    return domains

# Function to update all domain details
def update_all_domains():
    domains_list = read_domains(DOMAINS_FILE)
    for url in domains_list:
        try:
            domain_details = gather_domain_details(url)
            save_to_json(domain_details, OUTPUT_DIR)
            print(f"Successfully processed domain: {domain_details['domain']}")
        except Exception as e:
            print(f"Error processing domain {url}: {e}")
    print(f"Updated domain details at {time.strftime('%Y-%m-%d %H:%M:%S')}")

# Create output directory if not exists
import os
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Schedule the script to run at the specified interval
schedule.every(CHECK_INTERVAL).seconds.do(update_all_domains)

# Initial run
update_all_domains()

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(1)
