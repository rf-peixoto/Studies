#!/usr/bin/env python3

import os
import csv
import socket
import ssl
import re
import time
import json
import concurrent.futures
from datetime import datetime
from urllib.parse import urlparse
import http.client

import dns.resolver
import ipwhois
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

INPUT_FILE       = 'subdomains.txt'
OUTPUT_FILE      = 'domain_report.csv'
COMMON_PORTS     = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143,
                    443, 445, 465, 587, 993, 995, 1433, 1521, 2049,
                    3306, 3389, 5432, 5900, 5985, 5986, 6379,
                    8000, 8008, 8080, 8081, 8443, 8888, 9000,
                    9090, 9200, 9300, 11211]
SSL_PORTS        = [443, 8443, 465, 993, 995, 636, 990, 2083, 2087, 2096]
HTTP_PORTS       = [80, 443, 8000, 8008, 8080, 8081, 8443, 8888]
CONTENT_PATHS    = ['/', '/robots.txt', '/sitemap.xml', '/.well-known/security.txt']
TIMEOUT          = 5
MAX_WORKERS      = 20
DNS_SERVERS      = ['8.8.8.8', '1.1.1.1']

USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.5790.102 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) "
    "Gecko/20100101 Firefox/115.0",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.62",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.5 Safari/605.1.15"
]

TECH_DB = 'tech_db.json'

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

# ─────────────────────────────────────────────────────────────────────────────
# Initialize technology fingerprint database if missing
# ─────────────────────────────────────────────────────────────────────────────

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
            r'<meta\s+name=["\']generator["\']\s+content=["\'](.*?)["\']': ["wordpress", "drupal", "joomla", "magento"],
            r'wp-content': ["wordpress"],
            r'\bdrupal\b': ["drupal"],
            r'\bjoomla\b': ["joomla"],
            r'react-dom': ["react"],
            r'ng-app': ["angular"],
            r'\bvue\b': ["vue.js"],
            r'\blaravel\b': ["laravel"],
            r'shopify': ["shopify"],
            r'__NEXT_DATA__': ["next.js"],
            r'/_nuxt/': ["nuxt.js"]
        },
        "cookies": {
            r'wordpress_logged_in': ["wordpress"],
            r'drupal.*': ["drupal"],
            r'joomla.*': ["joomla"],
            r'laravel_session': ["laravel"],
            r'express': ["express"],
            r'csrftoken': ["django"],
            r'sessionid': ["django"],
            r'asp.net_sessionid': ["asp.net"]
        },
        "meta": {
            "generator": ["wordpress", "drupal", "joomla", "magento"],
            "framework": ["rails", "django"],
            "platform": ["shopify", "bigcommerce"]
        }
    }
    with open(TECH_DB, 'w', encoding='utf-8') as f:
        json.dump(tech_data, f, indent=2)

def load_tech_db():
    with open(TECH_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

# ─────────────────────────────────────────────────────────────────────────────
# DNS and network utilities
# ─────────────────────────────────────────────────────────────────────────────

def resolve_dns(name, record_type='A'):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = DNS_SERVERS
    try:
        answers = resolver.resolve(name, record_type, lifetime=TIMEOUT)
        return [str(r) for r in answers]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
            dns.resolver.NoNameservers, dns.exception.Timeout):
        return []
    except Exception:
        return []

def get_dns_records(domain):
    records = {}
    for rtype in ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'CAA']:
        records[rtype] = resolve_dns(domain, rtype)
    return records

def get_reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ''

def get_asn_info(ip):
    try:
        obj = ipwhois.IPWhois(ip)
        results = obj.lookup_rdap()
        return {
            'asn': results.get('asn', ''),
            'asn_description': results.get('asn_description', ''),
            'network': results.get('network', {}).get('name', ''),
            'cidr': results.get('asn_cidr', '')
        }
    except Exception:
        return {}

def check_port(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT):
            return True
    except Exception:
        return False

def get_banner(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT) as sock:
            sock.settimeout(TIMEOUT)
            banner = sock.recv(1024)
            return banner.decode('utf-8', errors='replace').strip()
    except Exception:
        return ''

def get_ssl_info(domain, ip, port):
    try:
        context = ssl.create_default_context()
        sock = socket.create_connection((ip, port), timeout=TIMEOUT)
        ssl_sock = context.wrap_socket(sock, server_hostname=domain)
        cert = ssl_sock.getpeercert()

        not_after = cert.get('notAfter', '')
        if not_after:
            # Remove timezone (e.g. "GMT") before parsing
            core = not_after.rsplit(' ', 1)[0]
            expires = datetime.strptime(core, '%b %d %H:%M:%S %Y')
        else:
            expires = None

        version = ssl_sock.version() or ''
        cipher = ssl_sock.cipher()[0] if ssl_sock.cipher() else ''
        alt_names = [n for typ, n in cert.get('subjectAltName', []) if typ == 'DNS']
        subject = cert.get('subject', ())
        issuer = cert.get('issuer', ())
        ssl_sock.close()

        return {
            'version': version,
            'cipher': cipher,
            'subject': subject,
            'issuer': issuer,
            'expires': expires,
            'alt_names': alt_names
        }
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# HTTP fetching with redirect tracking
# ─────────────────────────────────────────────────────────────────────────────

def fetch_url(domain, ip, port, path='/', redirect_chain=None, follow_redirects=True):
    if redirect_chain is None:
        redirect_chain = []

    scheme = 'https' if port in SSL_PORTS else 'http'
    url = f"{scheme}://{domain}{path}"
    try:
        if scheme == 'http':
            conn = http.client.HTTPConnection(ip, port, timeout=TIMEOUT)
        else:
            context = ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(ip, port, timeout=TIMEOUT, context=context)

        headers = {
            'Host': domain,
            'User-Agent': random.choice(USER_AGENTS)
        }
        start = time.time()
        conn.request('GET', path, headers=headers)
        resp = conn.getresponse()
        elapsed = time.time() - start
        status = resp.status

        # Redirect handling
        if follow_redirects and 300 <= status < 400:
            loc = resp.getheader('Location') or ''
            if loc:
                redirect_chain.append(loc)
                parsed = urlparse(loc)
                new_domain = parsed.hostname or domain
                new_ip = socket.gethostbyname(new_domain)
                new_port = parsed.port or (80 if parsed.scheme == 'http' else 443)
                conn.close()
                return fetch_url(new_domain, new_ip, new_port,
                                 parsed.path or '/', redirect_chain, False)

        raw_headers = {k.lower(): v for k, v in resp.getheaders()}
        content_bytes = resp.read(8192)
        text = content_bytes.decode('utf-8', errors='replace')

        title = ''
        ctype = raw_headers.get('content-type', '').lower()
        if 'text/html' in ctype:
            soup = BeautifulSoup(text, 'html.parser')
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

        security = {hdr: raw_headers.get(hdr.lower(), '') for hdr in SECURITY_HEADERS}
        conn.close()

        return {
            'url': url,
            'status': status,
            'headers': raw_headers,
            'title': title[:255],
            'content': text,
            'security_headers': security,
            'redirect_chain': redirect_chain.copy(),
            'load_time': round(elapsed, 3)
        }
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Technology detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_technologies(http_response):
    tech_db = load_tech_db()
    detected = set()
    if not http_response:
        return []

    headers = http_response.get('headers', {})
    # Header-based
    for header, patterns in tech_db['headers'].items():
        val = headers.get(header, '').lower()
        for pat in patterns:
            if pat.lower() in val:
                detected.add(pat)

    content = http_response.get('content', '')
    # HTML pattern-based
    for pattern, techs in tech_db['html'].items():
        try:
            if re.search(pattern, content, flags=re.IGNORECASE):
                detected.update(techs)
        except re.error:
            continue

    # Cookie-based
    cookies = headers.get('set-cookie', '')
    for pattern, techs in tech_db['cookies'].items():
        if re.search(pattern, cookies, flags=re.IGNORECASE):
            detected.update(techs)

    # Meta tag-based
    soup = BeautifulSoup(content, 'html.parser')
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        content_attr = meta.get('content', '').lower()
        for tech in tech_db['meta'].get(name, []):
            if tech.lower() in content_attr:
                detected.add(tech)

    return list(detected)

# ─────────────────────────────────────────────────────────────────────────────
# Content discovery
# ─────────────────────────────────────────────────────────────────────────────

def check_content_discovery(domain, ip, port):
    results = {}
    for path in CONTENT_PATHS:
        resp = fetch_url(domain, ip, port, path, follow_redirects=False)
        results[path] = resp['status'] if resp else 'timeout'
    return results

# ─────────────────────────────────────────────────────────────────────────────
# Subdomain enumeration (optional)
# ─────────────────────────────────────────────────────────────────────────────

def perform_subdomain_enumeration(domain):
    prefixes = ['www', 'mail', 'ftp', 'api', 'dev', 'test',
                'stage', 'portal', 'admin', 'ns1', 'ns2', 'blog', 'm', 'smtp']
    found = []
    for prefix in prefixes:
        sub = f"{prefix}.{domain}"
        if resolve_dns(sub, 'A') or resolve_dns(sub, 'AAAA'):
            found.append(sub)
    return found

# ─────────────────────────────────────────────────────────────────────────────
# Main scanning logic
# ─────────────────────────────────────────────────────────────────────────────

def scan_domain(domain):
    dns_records = get_dns_records(domain)
    ips = dns_records.get('A', []) + dns_records.get('AAAA', [])
    if not ips:
        return [{
            **{
                'domain': domain,
                'ip': '',
                'port': '',
                'accessible': False,
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
        }]

    results = []
    for ip in ips:
        asn_info = get_asn_info(ip)
        reverse = get_reverse_dns(ip)

        for port in COMMON_PORTS:
            if not check_port(ip, port):
                continue

            ssl_details = get_ssl_info(domain, ip, port) if port in SSL_PORTS else {}
            banner = get_banner(ip, port)

            http_resp = None
            techs = []
            sec_hdrs = {}
            content_disc = {}

            if port in HTTP_PORTS:
                http_resp = fetch_url(domain, ip, port)
                if http_resp:
                    techs = detect_technologies(http_resp)
                    sec_hdrs = http_resp.get('security_headers', {})
                    content_disc = check_content_discovery(domain, ip, port)

            record = {
                'domain': domain,
                'ip': ip,
                'ip_version': 'IPv6' if ':' in ip else 'IPv4',
                'port': port,
                'accessible': True,
                'banner': banner[:500],
                'ssl': port in SSL_PORTS,
                'ssl_version': ssl_details.get('version', ''),
                'ssl_cipher': ssl_details.get('cipher', ''),
                'cert_subject': str(ssl_details.get('subject', '')),
                'cert_issuer': str(ssl_details.get('issuer', '')),
                'cert_expiry': ssl_details.get('expires').strftime('%Y-%m-%d') if ssl_details.get('expires') else '',
                'cert_alt_names': ', '.join(ssl_details.get('alt_names', [])),
                'http_status': http_resp.get('status', '') if http_resp else '',
                'server_header': http_resp['headers'].get('server', '') if http_resp else '',
                'x_powered_by': http_resp['headers'].get('x-powered-by', '') if http_resp else '',
                'content_type': http_resp['headers'].get('content-type', '') if http_resp else '',
                'page_title': http_resp.get('title', '') if http_resp else '',
                'technologies': ', '.join(techs),
                'security_headers': json.dumps(sec_hdrs),
                'content_discovery': json.dumps(content_disc),
                'dns_a': ', '.join(dns_records.get('A', [])),
                'dns_aaaa': ', '.join(dns_records.get('AAAA', [])),
                'dns_mx': ', '.join(dns_records.get('MX', [])),
                'dns_txt': ', '.join(dns_records.get('TXT', [])),
                'dns_ns': ', '.join(dns_records.get('NS', [])),
                'reverse_dns': reverse,
                'asn': asn_info.get('asn', ''),
                'asn_description': asn_info.get('asn_description', ''),
                'load_time': http_resp.get('load_time', '') if http_resp else ''
            }

            results.append(record)

    return results

def main():
    # Read and dedupe domains
    all_domains = set()
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            d = line.strip()
            if d:
                all_domains.add(d)
                # To enable brute sub-enumeration, uncomment:
                # all_domains.update(perform_subdomain_enumeration(d))

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(scan_domain, dom): dom for dom in all_domains}
        for future in concurrent.futures.as_completed(future_map):
            domain = future_map[future]
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"[!] Error scanning {domain}: {e}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE) or '.', exist_ok=True)

    # Write CSV with minimal quoting (inner quotes will be escaped)
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
        writer = csv.DictWriter(csvfile,
                                fieldnames=fieldnames,
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(results)

    print(f"Scan complete: {len(all_domains)} domains, {len(results)} records")
    print(f"Results written to {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
