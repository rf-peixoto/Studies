# pip install requests beautifulsoup4 dnspython schedule builtwith

import requests
import json
import subprocess
import ssl
import socket
from bs4 import BeautifulSoup
import time
import schedule
import builtwith
import logging

# Setup logging
logging.basicConfig(filename='app.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Customizable Variables
DOMAINS_FILE = 'domains.txt'
CHECK_INTERVAL = 86400  # Time in seconds (86400 seconds = 24 hours)
OUTPUT_DIR = './data/'
INVALID_DOMAINS_FILE = 'invalid_domains.json'

# User agent for requests
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

# Function to ensure URL has a scheme
def ensure_scheme(url):
    if not url.startswith(('http://', 'https://')):
        return 'http://' + url
    return url

# Function to get IP address using the `host` command
def get_ip(domain):
    try:
        result = subprocess.run(['host', domain], capture_output=True, text=True)
        if result.returncode == 0:
            output_lines = result.stdout.split()
            ip_address = output_lines[-1]
            if ip_address == '.' or ip_address == '0':
                return None
            return ip_address
        else:
            return None
    except Exception as e:
        logging.error(f"Error resolving IP for domain {domain}: {str(e)}")
        return None

# Function to get SSL certificate details
def get_ssl_info(domain):
    context = ssl.create_default_context()
    try:
        with context.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.connect((domain, 443))
            cert = s.getpeercert()
        return cert
    except Exception as e:
        logging.error(f"Error retrieving SSL info for domain {domain}: {str(e)}")
        return 'SSL info not available'

# Function to get page title
def get_page_title(url):
    headers = {'User-Agent': USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.title.string if soup.title else 'No title found'
    except requests.RequestException as e:
        logging.error(f"Error retrieving page title for URL {url}: {str(e)}")
        return 'Page title not available'

# Function to detect technologies using BuiltWith
def detect_technologies(url):
    try:
        return builtwith.parse(url)
    except Exception as e:
        logging.error(f"Error detecting technologies for URL {url}: {str(e)}")
        return 'Technologies not available'

# Function to gather all details for a domain
def gather_domain_details(url):
    url = ensure_scheme(url)
    domain = url.replace('https://', '').replace('http://', '').split('/')[0]
    ip_address = get_ip(domain)

    if not ip_address:
        logging.info(f"Skipping domain {domain} due to invalid IP")
        return None

    ssl_info = get_ssl_info(domain)
    page_title = get_page_title(url)
    technologies = detect_technologies(url)

    details = {
        'domain': domain,
        'ip_address': ip_address,
        'ssl_info': ssl_info,
        'page_title': page_title,
        'technologies': technologies
    }
    
    print(f"{domain}: IP={ip_address}, SSL={'Available' if ssl_info != 'SSL info not available' else 'Not available'}, Title={page_title}")
    logging.info(f"Processed domain {domain}: IP={ip_address}, SSL={'Available' if ssl_info != 'SSL info not available' else 'Not available'}, Title={page_title}")
    return details

# Function to save details to a JSON file
def save_to_json(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
    logging.info(f"Saved data to {file_path}")

# Function to read domains from file
def read_domains(file_path):
    with open(file_path, 'r') as file:
        domains = [line.strip() for line in file.readlines()]
    logging.info(f"Read {len(domains)} domains from {file_path}")
    return domains

# Function to update all domain details
def update_all_domains():
    domains_list = read_domains(DOMAINS_FILE)
    invalid_domains = []

    for url in domains_list:
        try:
            domain_details = gather_domain_details(url)
            if domain_details:
                save_to_json(domain_details, f"{OUTPUT_DIR}{domain_details['domain']}.json")
            else:
                invalid_domains.append(url)
        except Exception as e:
            logging.error(f"Error processing domain {url}: {str(e)}")

    # Save invalid domains to a single JSON file
    save_to_json(invalid_domains, f"{OUTPUT_DIR}{INVALID_DOMAINS_FILE}")
    print(f"\nUpdated domain details at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("Updated domain details")

# Create output directory if not exists
import os
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logging.info(f"Created output directory {OUTPUT_DIR}")

# Schedule the script to run at the specified interval
schedule.every(CHECK_INTERVAL).seconds.do(update_all_domains)

# Initial run
update_all_domains()

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(1)
