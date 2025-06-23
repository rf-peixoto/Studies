# pip install selenium webdriver-manager opencv-python-headless geoip2 pyyaml

import socket
import ssl
import csv
import concurrent.futures
import re
import time
import json
import os
import dns.resolver
import dns.zone
import dns.reversename
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
import http.client
import ipwhois
import subprocess

# Enhanced Configuration
INPUT_FILE = 'subdomains.txt'
OUTPUT_FILE = 'domain_report.csv'
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 
                465, 587, 993, 995, 1433, 1521, 2049, 3306, 3389, 5432, 5900, 
                5985, 5986, 6379, 8000, 8008, 8080, 8081, 8443, 8888, 9000, 
                9090, 9200, 9300, 11211]
SSL_PORTS = [443, 8443, 465, 993, 995, 636, 990, 2083, 2087, 2096, 8443]
HTTP_PORTS = [80, 443, 8080, 8081, 8000, 8008, 8443, 8888]
CONTENT_PATHS = ['/', '/robots.txt', '/sitemap.xml', '/.well-known/security.txt']
TIMEOUT = 5
MAX_WORKERS = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
TECH_DB = "tech_db.json"
DNS_SERVERS = ['8.8.8.8', '1.1.1.1']  # Google and Cloudflare DNS

# Security headers to check
SECURITY_HEADERS = [
    'Strict-Transport-Security',
    'Content-Security-Policy',
    'X-Content-Type-Options',
    'X-Frame-Options',
    'X-XSS-Protection',
    'Referrer-Policy',
    'Feature-Policy',
    'Permissions-Policy'
]

# Create enhanced technology database
if not os.path.exists(TECH_DB):
    tech_data = {
        "headers": {
            "server": ["apache", "nginx", "iis", "litespeed", "caddy", "cloudflare", "cloudfront"],
            "x-powered-by": ["php", "asp.net", "express", "servlet"],
            "x-aspnet-version": [".net"],
            "x-aspnetmvc-version": ["asp.net mvc"],
            "x-runtime": ["rails"],
            "x-drupal-cache": ["drupal"],
            "x-generator": ["drupal", "wordpress"],
            "x-backend-server": ["oracle", "weblogic"],
            "cf-ray": ["cloudflare"]
        },
        "html": {
            "<meta name=\"generator\" content=\"(.*?)\"": ["wordpress", "drupal", "joomla", "magento"],
            "wp-content": ["wordpress"],
            "drupal": ["drupal"],
            "joomla": ["joomla"],
            "react-dom": ["react"],
            "ng-app": ["angular"],
            "vue": ["vue.js"],
            "laravel": ["laravel"],
            "shopify": ["shopify"],
            "__NEXT_DATA__": ["next.js"],
            "/_nuxt/": ["nuxt.js"]
        },
        "cookies": {
            "wordpress_logged_in": ["wordpress"],
            "drupal.*": ["drupal"],
            "joomla.*": ["joomla"],
            "laravel_session": ["laravel"],
            "express": ["express"],
            "csrftoken": ["django"],
            "sessionid": ["django"],
            "asp.net_sessionid": ["asp.net"]
        },
        "meta": {
            "generator": ["wordpress", "drupal", "joomla", "magento"],
            "framework": ["rails", "django"],
            "platform": ["shopify", "bigcommerce"]
        }
    }
    with open(TECH_DB, 'w') as f:
        json.dump(tech_data, f)

def load_tech_db():
    with open(TECH_DB, 'r') as f:
        return json.load(f)

def resolve_dns(domain, record_type='A'):
    """Resolve DNS records of specified type"""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = DNS_SERVERS
    try:
        answers = resolver.resolve(domain, record_type)
        return [str(r) for r in answers]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout, dns.resolver.NoNameservers):
        return []

def get_dns_records(domain):
    """Get comprehensive DNS records"""
    records = {}
    for rtype in ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'CAA']:
        records[rtype] = resolve_dns(domain, rtype)
    return records

def get_reverse_dns(ip):
    """Perform reverse DNS lookup"""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror):
        return ""

def get_asn_info(ip):
    """Get ASN information for IP"""
    try:
        obj = ipwhois.IPWhois(ip)
        results = obj.lookup_rdap()
        return {
            'asn': results.get('asn'),
            'asn_description': results.get('asn_description'),
            'network': results.get('network', {}).get('name'),
            'cidr': results.get('asn_cidr')
        }
    except (ipwhois.exceptions.IPDefinedError, ipwhois.exceptions.HTTPLookupError):
        return {}

def check_port(ip, port):
    """Check if port is open with socket"""
    # Implementation remains same as before
    pass

def get_banner(ip, port):
    """Get service banner"""
    # Implementation remains same as before
    pass

def get_ssl_info(domain, ip, port):
    """Get SSL/TLS certificate details with vulnerability checks"""
    # Implementation remains same as before
    pass

def fetch_url(domain, ip, port, path='/', follow_redirects=True):
    """Fetch URL with full HTTP handling"""
    scheme = "https" if port in SSL_PORTS else "http"
    url = f"{scheme}://{ip}:{port}{path}"
    
    try:
        # Handle IPv6 addresses
        if ':' in ip:
            ip = f"[{ip}]"
            
        conn = http.client.HTTPConnection(ip, port, timeout=TIMEOUT) if scheme == "http" \
              else http.client.HTTPSConnection(ip, port, timeout=TIMEOUT, context=ssl._create_unverified_context())
        
        headers = {'Host': domain, 'User-Agent': USER_AGENT}
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        
        # Handle redirects
        location = response.getheader('Location', '')
        if follow_redirects and 300 <= response.status < 400 and location:
            parsed = urlparse(location)
            if parsed.netloc:
                return fetch_url(parsed.netloc, 
                                socket.gethostbyname(parsed.netloc), 
                                80 if parsed.scheme == 'http' else 443, 
                                parsed.path, 
                                follow_redirects=False)
        
        headers = {k.lower(): v for k, v in response.getheaders()}
        content = response.read(8192)  # Read first 8KB
        
        # Extract title
        title = ""
        if 'text/html' in headers.get('content-type', '').lower():
            soup = BeautifulSoup(content, 'html.parser')
            title = soup.title.string if soup.title else ""
        
        # Check security headers
        security_headers = {}
        for header in SECURITY_HEADERS:
            security_headers[header] = headers.get(header.lower(), '')
        
        return {
            'url': url,
            'status': response.status,
            'headers': headers,
            'title': title[:255] if title else "",
            'content': content.decode('utf-8', errors='replace')[:2048],
            'security_headers': security_headers,
            'redirect_chain': location,
            'load_time': time.time()  # Placeholder for actual timing
        }
    except Exception as e:
        return None

def detect_technologies(http_response):
    """Enhanced technology detection"""
    if not http_response:
        return []
    
    tech_db = load_tech_db()
    detected = set()
    
    # Check headers
    headers = http_response.get('headers', {})
    for header, patterns in tech_db['headers'].items():
        if header in headers:
            value = headers[header].lower()
            for tech in patterns:
                if tech in value:
                    detected.add(tech)
    
    # Check HTML content
    html = http_response.get('content', '').lower()
    for pattern, techs in tech_db['html'].items():
        try:
            if re.search(pattern, html, re.IGNORECASE):
                for tech in techs:
                    detected.add(tech)
        except re.error:
            continue
    
    # Check cookies
    cookies = headers.get('set-cookie', '')
    for pattern, techs in tech_db['cookies'].items():
        if re.search(pattern, cookies, re.IGNORECASE):
            for tech in techs:
                detected.add(tech)
    
    # Check meta tags
    if 'content' in http_response:
        soup = BeautifulSoup(http_response['content'], 'html.parser')
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            content = meta.get('content', '').lower()
            for tech in tech_db['meta'].get(name, []):
                if tech in content:
                    detected.add(tech)
    
    return list(detected)

def check_content_discovery(domain, ip, port):
    """Check for common content paths"""
    results = {}
    for path in CONTENT_PATHS:
        response = fetch_url(domain, ip, port, path, follow_redirects=False)
        if response:
            results[path] = response['status']
        else:
            results[path] = 'timeout'
    return results

def perform_subdomain_enumeration(domain):
    """Perform subdomain enumeration"""
    # This would be implemented with common wordlists
    # For now return empty list - to be implemented
    return []

def scan_domain(domain):
    """Comprehensive domain scan"""
    results = []
    
    # DNS records
    dns_records = get_dns_records(domain)
    
    # IP addresses
    ips = dns_records.get('A', []) + dns_records.get('AAAA', [])
    
    if not ips:
        return [create_result_record(domain, accessible=False, dns_records=dns_records)]
    
    for ip in ips:
        # ASN and geolocation
        asn_info = get_asn_info(ip)
        reverse_dns = get_reverse_dns(ip)
        
        for port in COMMON_PORTS:
            if not check_port(ip, port):
                continue
                
            ssl_info = get_ssl_info(domain, ip, port) if port in SSL_PORTS else None
            banner = get_banner(ip, port)
            
            # HTTP content
            http_response = None
            content_discovery = {}
            technologies = []
            security_headers = {}
            
            if port in HTTP_PORTS:
                http_response = fetch_url(domain, ip, port)
                if http_response:
                    technologies = detect_technologies(http_response)
                    security_headers = http_response.get('security_headers', {})
                    content_discovery = check_content_discovery(domain, ip, port)
            
            # Build result
            result = {
                'domain': domain,
                'ip': ip,
                'port': port,
                'accessible': True,
                'banner': banner[:500] if banner else '',
                'ssl': port in SSL_PORTS,
                'ssl_version': ssl_info.get('version', '') if ssl_info else '',
                'ssl_cipher': ssl_info.get('cipher', '') if ssl_info else '',
                'cert_subject': str(ssl_info.get('subject', '')) if ssl_info else '',
                'cert_issuer': str(ssl_info.get('issuer', '')) if ssl_info else '',
                'cert_expiry': ssl_info['expires'].strftime('%Y-%m-%d') if ssl_info and ssl_info.get('expires') else '',
                'cert_alt_names': ', '.join(ssl_info.get('alt_names', [])) if ssl_info else '',
                'http_status': http_response.get('status', '') if http_response else '',
                'server_header': http_response['headers'].get('server', '') if http_response else '',
                'x_powered_by': http_response['headers'].get('x-powered-by', '') if http_response else '',
                'content_type': http_response['headers'].get('content-type', '') if http_response else '',
                'page_title': http_response.get('title', '') if http_response else '',
                'technologies': ', '.join(technologies) if technologies else '',
                'security_headers': json.dumps(security_headers) if security_headers else '',
                'content_discovery': json.dumps(content_discovery) if content_discovery else '',
                'dns_a': ', '.join(dns_records.get('A', [])),
                'dns_aaaa': ', '.join(dns_records.get('AAAA', [])),
                'dns_mx': ', '.join(dns_records.get('MX', [])),
                'dns_txt': ', '.join(dns_records.get('TXT', [])),
                'dns_ns': ', '.join(dns_records.get('NS', [])),
                'reverse_dns': reverse_dns,
                'asn': asn_info.get('asn', ''),
                'asn_description': asn_info.get('asn_description', ''),
                'ip_version': 'IPv6' if ':' in ip else 'IPv4',
                'load_time': http_response.get('load_time', '') if http_response else ''
            }
            results.append(result)
    
    if not results:
        results.append(create_result_record(domain, accessible=False, dns_records=dns_records))
    
    return results

def create_result_record(domain, accessible=False, dns_records=None):
    """Create result record with DNS data"""
    if not dns_records:
        dns_records = get_dns_records(domain)
    
    return {
        'domain': domain,
        'ip': '',
        'port': '',
        'accessible': accessible,
        'banner': '',
        'ssl': False,
        'ssl_version': '',
        'ssl_cipher': '',
        'cert_subject': '',
        'cert_issuer': '',
        'cert_expiry': '',
        'cert_alt_names': '',
        'http_status': '',
        'server_header': '',
        'x_powered_by': '',
        'content_type': '',
        'page_title': '',
        'technologies': '',
        'security_headers': '',
        'content_discovery': '',
        'dns_a': ', '.join(dns_records.get('A', [])),
        'dns_aaaa': ', '.join(dns_records.get('AAAA', [])),
        'dns_mx': ', '.join(dns_records.get('MX', [])),
        'dns_txt': ', '.join(dns_records.get('TXT', [])),
        'dns_ns': ', '.join(dns_records.get('NS', [])),
        'reverse_dns': '',
        'asn': '',
        'asn_description': '',
        'ip_version': '',
        'load_time': ''
    }

def main():
    # Read domains and perform subdomain enumeration
    all_domains = set()
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            domain = line.strip()
            if domain:
                all_domains.add(domain)
                # Uncomment to enable subdomain enumeration
                # all_domains.update(perform_subdomain_enumeration(domain))
    
    # Process domains
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_domain = {executor.submit(scan_domain, domain): domain for domain in all_domains}
        for future in concurrent.futures.as_completed(future_to_domain):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"Error processing domain: {e}")
    
    # Write results
    fieldnames = [
        'domain', 'ip', 'ip_version', 'port', 'accessible', 'banner', 
        'ssl', 'ssl_version', 'ssl_cipher', 'cert_subject', 'cert_issuer', 
        'cert_expiry', 'cert_alt_names', 'http_status', 'server_header', 
        'x_powered_by', 'content_type', 'page_title', 'technologies',
        'security_headers', 'content_discovery', 'dns_a', 'dns_aaaa',
        'dns_mx', 'dns_txt', 'dns_ns', 'reverse_dns', 'asn', 'asn_description',
        'load_time'
    ]
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Scan complete. Results saved to {OUTPUT_FILE}")
    print(f"Scanned {len(all_domains)} domains with {len(results)} services found")

if __name__ == "__main__":
    main()
