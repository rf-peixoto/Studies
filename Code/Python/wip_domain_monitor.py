import os
import json
import time
import socket
import logging
import requests
import dns.resolver
import subprocess
import re
import ssl
import datetime
from urllib.parse import urlparse
from logging.handlers import RotatingFileHandler
from bs4 import BeautifulSoup
import builtwith
import schedule

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Setup logging with rotation
handler = RotatingFileHandler(config["log_file"], maxBytes=config["log_file_max_size"], backupCount=config["log_file_backup_count"])
logging.basicConfig(handlers=[handler], level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Utility function to ensure URL has a scheme
def ensure_scheme(url):
    if not url.startswith(('http://', 'https://')):
        return 'http://' + url
    return url

# Utility function to get IP address using socket library
def get_ip(domain, retries=3, delay=2):
    for attempt in range(retries):
        try:
            addr_info = socket.getaddrinfo(domain, None)
            for result in addr_info:
                ip_address = result[4][0]
                if ip_address:
                    return ip_address
        except Exception as e:
            logging.error(f"Error resolving IP for domain {domain}: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None

# Function to get DNS records
def get_dns_records(domain):
    try:
        resolver = dns.resolver.Resolver()
        records = {
            'A': [x.to_text() for x in resolver.resolve(domain, 'A')],
            'AAAA': [x.to_text() for x in resolver.resolve(domain, 'AAAA')],
            'MX': [x.exchange.to_text() for x in resolver.resolve(domain, 'MX')],
            'NS': [x.to_text() for x in resolver.resolve(domain, 'NS')],
            'TXT': [x.to_text() for x in resolver.resolve(domain, 'TXT')],
            'CAA': [x.to_text() for x in resolver.resolve(domain, 'CAA')],
            'CNAME': [x.to_text() for x in resolver.resolve(domain, 'CNAME')],
            'SOA': [x.to_text() for x in resolver.resolve(domain, 'SOA')]
        }
        return records
    except Exception as e:
        logging.error(f"Error retrieving DNS records for domain {domain}: {str(e)}")
        return {}

# Function to get SSL certificate details
def get_ssl_info(domain):
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        # Convert any datetime objects in cert to strings
        cert_serializable = {}
        for key, value in cert.items():
            if isinstance(value, tuple):
                cert_serializable[key] = tuple(str(v) if isinstance(v, (datetime.datetime, datetime.date)) else v for v in value)
            elif isinstance(value, (datetime.datetime, datetime.date)):
                cert_serializable[key] = str(value)
            else:
                cert_serializable[key] = value
        return {'cert': cert_serializable}
    except Exception as e:
        logging.error(f"Error retrieving SSL info for domain {domain}: {str(e)}")
        return {'cert': None}

# Function to get WHOIS information using the native Linux whois command
def get_whois_info(domain):
    try:
        result = subprocess.run(['whois', domain], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout
        else:
            logging.error(f"Error retrieving WHOIS info for domain {domain}: {result.stderr}")
            return 'WHOIS info not available'
    except Exception as e:
        logging.error(f"Error running WHOIS for domain {domain}: {str(e)}")
        return 'WHOIS info not available'

# Function to get page title with retries and detect redirection
def get_page_title_and_redirection(url, retries=config['retry_attempts'], domain_list=None):
    headers = {'User-Agent': config['user_agent']}
    redirections = []
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=False)
            if response.status_code in [301, 302, 303, 307, 308]:
                location = response.headers.get('Location')
                if location:
                    redirect_target = urlparse(location).netloc
                    if redirect_target in domain_list:
                        redirections.append(redirect_target)
                    url = ensure_scheme(location)
                    continue  # Follow the redirection
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup.title.string if soup.title else 'No title found', redirections, dict(response.headers)
        except requests.RequestException as e:
            logging.error(f"Error retrieving page title for URL {url}: {str(e)}")
            return 'Page title not available', redirections, {}

# Function to detect technologies using BuiltWith
def detect_technologies(url):
    try:
        return builtwith.parse(url)
    except Exception as e:
        logging.error(f"Error detecting technologies for URL {url}: {str(e)}")
        return 'Technologies not available'

# Function to run AssetFinder for subdomain enumeration
def get_subdomains(domain):
    try:
        result = subprocess.run(
            ["assetfinder", domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        if result.stderr:
            logging.error(f"AssetFinder error for domain {domain}: {result.stderr}")
        subdomains = result.stdout.strip().split('\n')
        return sorted(set(subdomains))
    except Exception as e:
        logging.error(f"Error running AssetFinder for domain {domain}: {str(e)}")
        return 'Subdomain enumeration not available'

# Function to run Shodan info collection
def get_shodan_info(ip):
    try:
        response = requests.get(f"https://internetdb.shodan.io/{ip}")
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        logging.error(f"HTTP error retrieving Shodan info for IP {ip}: {str(e)}")
        return {"detail": "No information available"}
    except Exception as e:
        logging.error(f"Error retrieving Shodan info for IP {ip}: {str(e)}")
        return {"detail": "No information available"}

# Function to perform banner grabbing
def banner_grab(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((ip, port))
        sock.sendall(b'HEAD / HTTP/1.0\r\n\r\n')
        banner = sock.recv(1024).decode()
        sock.close()
        return banner
    except Exception as e:
        logging.error(f"Error banner grabbing on {ip}:{port}: {str(e)}")
        return 'Banner grabbing not available'

# Function to run Nuclei scan
def run_nuclei_scan(domain):
    try:
        result = subprocess.run(
            ["nuclei", "-silent", "-target", domain, "-json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        nuclei_data = [json.loads(line) for line in result.stdout.strip().split('\n') if line.strip()]
        return nuclei_data
    except Exception as e:
        logging.error(f"Error running Nuclei scan for domain {domain}: {str(e)}")
        return 'Nuclei scan not available'

# Function to gather all details for a domain
def gather_domain_details(url, domain_list):
    url = ensure_scheme(url)
    domain = url.replace('https://', '').replace('http://', '').split('/')[0]
    ip_address = get_ip(domain)

    if not ip_address:
        logging.info(f"Skipping domain {domain} due to invalid IP")
        return None

    # Gathering details with error handling
    page_title, redirections, headers = get_page_title_and_redirection(url, domain_list=domain_list)
    details = {
        'domain': domain,
        'network': {
            'ip_address': ip_address,
            'dns_records': get_dns_records(domain),
            'ssl_info': get_ssl_info(domain),
            'whois_info': get_whois_info(domain),
            'shodan_info': get_shodan_info(ip_address)
        },
        'web': {
            'page_title': page_title,
            'technologies': detect_technologies(url),
            'security_headers': headers  # headers is already converted to dict
        },
        'subdomains': get_subdomains(domain),
        'nuclei_data': run_nuclei_scan(domain),
        'banners': {}
    }

    # Adding banners from Shodan data if available
    if 'ports' in details['network']['shodan_info']:
        for port in details['network']['shodan_info']['ports']:
            details['banners'][port] = banner_grab(ip_address, port)

    logging.info(f"Processed domain {domain}: IP={ip_address}")
    return details

# Function to save details to a JSON file
def save_to_json(data, file_path):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        logging.info(f"Saved data to {file_path}")
    except TypeError as e:
        logging.error(f"TypeError when saving data to {file_path}: {str(e)}")
    except Exception as e:
        logging.error(f"Error saving data to {file_path}: {str(e)}")

# Function to read domains from file
def read_domains(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            domains = [line.strip() for line in file if line.strip()]
        return domains
    else:
        logging.error(f"Domains file {file_path} not found")
        return []

# Function to process a single domain
def process_domain(url, domain_list, index, total_domains, invalid_domains_count):
    try:
        print(f"Processing domain: {url} ({index + 1}/{total_domains}) | Invalid domains: {invalid_domains_count}")
        domain_details = gather_domain_details(url, domain_list)
        if domain_details:
            output_file_path = os.path.join(config['output_dir'], f"{domain_details['domain']}.json")
            save_to_json(domain_details, output_file_path)
            return None
        else:
            return url
    except Exception as e:
        logging.error(f"Error processing domain {url}: {str(e)}")
        return url

# Function to update all domain details
def update_all_domains():
    domains_list = read_domains(config['domains_file'])
    invalid_domains = read_domains(os.path.join(os.path.dirname(os.path.abspath(__file__)), config['invalid_domains_file']))

    all_domains = domains_list + invalid_domains
    remaining_invalid_domains = []

    total_domains = len(all_domains)
    invalid_domains_count = 0

    for index, url in enumerate(all_domains):
        result = process_domain(url, domains_list, index, total_domains, invalid_domains_count)
        if result:
            remaining_invalid_domains.append(result)
            invalid_domains_count += 1

    # Save remaining invalid domains to a single JSON file in the same folder as the script
    invalid_domains_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config['invalid_domains_file'])
    save_to_json(remaining_invalid_domains, invalid_domains_file_path)
    logging.info("Updated domain details")

# Function to generate overall statistics report
def generate_statistics_report():
    stats = {
        "total_domains_processed": 0,
        "total_valid_domains": 0,
        "total_invalid_domains": 0
    }

    for root, dirs, files in os.walk(config['output_dir']):
        for file in files:
            if file.endswith(".json") and file != config['invalid_domains_file']:
                stats["total_domains_processed"] += 1
                with open(os.path.join(root, file), 'r') as f:
                    data = json.load(f)
                    if "network" in data and "ip_address" in data["network"] and data["network"]["ip_address"]:
                        stats["total_valid_domains"] += 1

    invalid_domains_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config['invalid_domains_file'])
    with open(invalid_domains_file_path, 'r') as f:
        invalid_domains = json.load(f)
        stats["total_invalid_domains"] = len(invalid_domains)

    stats_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statistics_report.json")
    save_to_json(stats, stats_file_path)
    print("The script is done.")

# Create output directory if not exists
if not os.path.exists(config['output_dir']):
    os.makedirs(config['output_dir'])
    logging.info(f"Created output directory {config['output_dir']}")

# Schedule the script to run at the specified interval
def schedule_tasks():
    if config.get('run_once', False):
        update_all_domains()
        generate_statistics_report()
    else:
        schedule.every(config['check_interval']).seconds.do(update_all_domains)
        schedule.every(config['check_interval']).seconds.do(generate_statistics_report)

# Initial run or scheduled execution
schedule_tasks()

# Keep the script running if it's not a one-time run
if not config.get('run_once', False):
    while True:
        schedule.run_pending()
        time.sleep(1)
