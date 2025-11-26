#!/usr/bin/env python3
"""
HTTP Method Security Scanner
Checks for unsafe HTTP methods and tests their functionality
"""

import requests
import json
import random
import string
import time
from urllib.parse import urljoin, urlparse
from colorama import Fore, Style, init
import argparse
import sys
import os
import csv

# Initialize colorama for cross-platform colored output
init(autoreset=True)

class SecurityScanner:
    def __init__(self, timeout=10, keep_files=False, verbose=False, minimal=False):
        self.timeout = timeout
        self.keep_files = keep_files
        self.verbose = verbose
        self.minimal = minimal
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HTTP Probe 1.0',
            'Content-Type': 'text/plain'
        })
        self.test_results = {}
        self.test_urls = []

    def print_status(self, message, level="info"):
        """Print colored status messages - only use colors for important info"""
        # Always show critical/warning/success, even in minimal mode
        if level not in ["critical", "warning", "success"]:
            # In minimal mode, suppress non-essential info
            if self.minimal and level in ["info", "test"]:
                return
            # In non-verbose mode, suppress test and error messages unless critical
            if not self.verbose and level in ["test", "error"]:
                return

        colors = {
            "critical": Fore.RED + Style.BRIGHT,
            "warning": Fore.YELLOW,
            "success": Fore.GREEN,
            "url": Fore.CYAN,
        }
        # info, test, error get no color by default
        color = colors.get(level, "")
        print(f"{color}{message}")

    def generate_test_filename(self):
        """Generate a random test filename"""
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"security_test_{random_str}.txt"

    def test_options(self, url):
        """Test OPTIONS method and return allowed methods"""
        if self.verbose and not self.minimal:
            print("Testing OPTIONS method...")

        try:
            response = self.session.options(url, timeout=self.timeout)
            allowed_methods = response.headers.get('Allow', '')
            if allowed_methods:
                methods = [m.strip().upper() for m in allowed_methods.split(',')]
                if not self.minimal:
                    print(f"Discovered methods: {', '.join(methods)}")
            else:
                methods = []
                if self.verbose and not self.minimal:
                    print("No Allow header in OPTIONS response")
            return methods, response.status_code
        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"OPTIONS request failed: {e}")
            return [], None

    def test_put(self, base_url):
        """Test PUT method by uploading a file"""
        test_filename = self.generate_test_filename()
        test_content = f"Security test content - {time.time()}"
        test_url = urljoin(base_url, test_filename)

        self.test_urls.append({
            'method': 'PUT',
            'url': test_url,
            'filename': test_filename,
            'content': test_content
        })

        results = {
            'put_allowed': False,
            'file_accessible': False,
            'put_status': None,
            'get_status': None,
            'test_file': test_filename,
            'test_url': test_url,
            'test_content': test_content
        }

        try:
            if self.verbose and not self.minimal:
                print(f"  Testing PUT with file: {test_filename}")
                print(f"  Test URL: {test_url}")

            put_response = self.session.put(test_url, data=test_content, timeout=self.timeout)
            results['put_status'] = put_response.status_code
            results['put_allowed'] = put_response.status_code in [200, 201, 204]

            if results['put_allowed']:
                if self.verbose and not self.minimal:
                    print("  PUT successful, testing accessibility...")

                get_response = self.session.get(test_url, timeout=self.timeout)
                results['get_status'] = get_response.status_code
                results['file_accessible'] = (get_response.status_code == 200 and
                                              test_content in get_response.text)

                if results['file_accessible']:
                    self.print_status(f"VULNERABLE: PUT allows file upload and public access: {test_url}", "critical")
                else:
                    self.print_status("WARNING: PUT allowed but file not accessible", "warning")

                if not self.keep_files:
                    try:
                        self.session.delete(test_url, timeout=self.timeout)
                    except:
                        pass
            else:
                if self.verbose and not self.minimal:
                    print("  PUT method not functional")

        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"  PUT test failed: {e}")

        return results

    def test_post(self, base_url):
        """Test POST method"""
        test_data = {
            "security_test": "test_data",
            "timestamp": time.time(),
            "random": random.randint(1000, 9999)
        }

        results = {
            'post_allowed': False,
            'status_code': None,
            'response_received': False
        }

        try:
            if self.verbose and not self.minimal:
                print("  Testing POST method")

            response = self.session.post(base_url, json=test_data, timeout=self.timeout)
            results['status_code'] = response.status_code
            results['post_allowed'] = response.status_code in [200, 201, 202, 204]
            results['response_received'] = len(response.content) > 0

            if results['post_allowed']:
                self.print_status("WARNING: POST method is functional", "warning")
            else:
                if self.verbose and not self.minimal:
                    print("  POST method not functional")

        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"  POST test failed: {e}")

        return results

    def test_delete(self, base_url):
        """Test DELETE method"""
        test_filename = self.generate_test_filename()
        test_url = urljoin(base_url, test_filename)

        self.test_urls.append({
            'method': 'DELETE',
            'url': test_url,
            'filename': test_filename,
            'action': 'delete'
        })

        results = {
            'delete_allowed': False,
            'file_removed': False,
            'delete_status': None,
            'verify_status': None,
            'test_url': test_url
        }

        try:
            if self.verbose and not self.minimal:
                print(f"  Testing DELETE with file: {test_filename}")
                print(f"  Test URL: {test_url}")

            put_response = self.session.put(test_url, data="test content for deletion", timeout=self.timeout)

            if put_response.status_code in [200, 201, 204]:
                if self.verbose and not self.minimal:
                    print("  Test file created successfully")

                delete_response = self.session.delete(test_url, timeout=self.timeout)
                results['delete_status'] = delete_response.status_code
                results['delete_allowed'] = delete_response.status_code in [200, 202, 204]

                verify_response = self.session.get(test_url, timeout=self.timeout)
                results['verify_status'] = verify_response.status_code
                results['file_removed'] = verify_response.status_code != 200

                if results['file_removed']:
                    self.print_status(f"VULNERABLE: DELETE method allows file removal: {test_url}", "critical")
                else:
                    self.print_status("WARNING: DELETE allowed but file not removed", "warning")

            else:
                if self.verbose and not self.minimal:
                    print("  Could not create test file for DELETE testing")

        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"  DELETE test failed: {e}")

        return results

    def test_trace(self, url):
        """Test TRACE method"""
        results = {
            'trace_allowed': False,
            'echoes_request': False,
            'status_code': None
        }

        try:
            test_header = f"X-Test-Header-{random.randint(1000, 9999)}"
            self.session.headers.update({'X-Test-Header': test_header})

            if self.verbose and not self.minimal:
                print("  Testing TRACE method")

            response = self.session.request('TRACE', url, timeout=self.timeout)
            results['status_code'] = response.status_code
            results['trace_allowed'] = response.status_code == 200

            if results['trace_allowed']:
                response_text = response.text.upper()
                has_echo = any(header in response_text for header in
                               ['USER-AGENT', 'X-TEST-HEADER', 'SECURITY-SCANNER'])
                results['echoes_request'] = has_echo

                if has_echo:
                    self.print_status("VULNERABLE: TRACE method echoes requests (XST vulnerability)", "critical")
                else:
                    self.print_status("WARNING: TRACE allowed but no request echoing", "warning")
            else:
                if self.verbose and not self.minimal:
                    print("  TRACE method not functional")

        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"  TRACE test failed: {e}")

        return results

    def test_patch(self, url):
        """Test PATCH method"""
        results = {
            'patch_allowed': False,
            'status_code': None
        }

        try:
            patch_data = {'op': 'replace', 'path': '/test', 'value': 'security_test'}

            if self.verbose and not self.minimal:
                print("  Testing PATCH method")

            response = self.session.patch(url, json=patch_data, timeout=self.timeout)
            results['status_code'] = response.status_code
            results['patch_allowed'] = response.status_code in [200, 201, 202, 204]

            if results['patch_allowed']:
                self.print_status("WARNING: PATCH method is functional", "warning")
            else:
                if self.verbose and not self.minimal:
                    print("  PATCH method not functional")

        except requests.RequestException as e:
            if self.verbose and not self.minimal:
                print(f"  PATCH test failed: {e}")

        return results

    def scan_domain(self, domain):
        """Perform complete security scan on a domain"""
        if not self.minimal:
            print("\n" + "=" * 60)
            print(f"Scanning: {domain}")
            print("=" * 60)

        results = {
            'domain': domain,
            'allowed_methods': [],
            'unsafe_methods': [],
            'vulnerabilities': [],
            'test_results': {}
        }

        # Test OPTIONS first
        allowed_methods, status_code = self.test_options(domain)
        results['allowed_methods'] = allowed_methods

        unsafe_methods = {
            'PUT': self.test_put,
            'POST': self.test_post,
            'DELETE': self.test_delete,
            'TRACE': self.test_trace,
            'PATCH': self.test_patch
        }

        found_unsafe = [method for method in unsafe_methods.keys() if method in allowed_methods]
        results['unsafe_methods'] = found_unsafe

        if not found_unsafe:
            self.print_status("No unsafe methods detected", "success")
        else:
            if not self.minimal:
                print(f"Testing unsafe methods: {', '.join(found_unsafe)}")

        # Test each unsafe method that was found
        for method in found_unsafe:
            if self.verbose and not self.minimal:
                print(f"  Testing {method}...")

            test_function = unsafe_methods[method]
            test_result = test_function(domain)
            results['test_results'][method] = test_result

            # Check if the method is actually vulnerable based on test results
            if method == 'PUT' and test_result.get('put_allowed') and test_result.get('file_accessible'):
                results['vulnerabilities'].append(
                    f"VULNERABLE: PUT method allows file upload and public access: {test_result.get('test_url')}"
                )
            elif method == 'PUT' and test_result.get('put_allowed'):
                results['vulnerabilities'].append(
                    f"WARNING: PUT method allows file upload: {test_result.get('test_url')}"
                )
            elif method == 'DELETE' and test_result.get('delete_allowed') and test_result.get('file_removed'):
                results['vulnerabilities'].append(
                    f"VULNERABLE: DELETE method allows file removal: {test_result.get('test_url')}"
                )
            elif method == 'TRACE' and test_result.get('trace_allowed') and test_result.get('echoes_request'):
                results['vulnerabilities'].append(
                    "VULNERABLE: TRACE method echoes requests (XST vulnerability)"
                )
            elif method == 'POST' and test_result.get('post_allowed'):
                results['vulnerabilities'].append(
                    "WARNING: POST method is functional"
                )
            elif method == 'PATCH' and test_result.get('patch_allowed'):
                results['vulnerabilities'].append(
                    "WARNING: PATCH method is functional"
                )

        return results

    def print_test_urls(self):
        """Print all test URLs for manual verification"""
        if not self.test_urls:
            return

        if not self.minimal:
            print("\n" + "=" * 60)
            print("TEST URLs FOR MANUAL VERIFICATION")
            print("=" * 60)
        else:
            print("\nTEST URLs FOR MANUAL VERIFICATION")

        for test in self.test_urls:
            print(f"Method: {test['method']}")
            print(f"URL: {test['url']}")
            if 'content' in test:
                print(f"Content: {test['content'][:50]}...")
            print()

    def print_results(self, results):
        """Print formatted results with colors"""
        domain = results['domain']
        vulnerabilities = results['vulnerabilities']

        if self.minimal:
            print(f"Results for {domain}:")
        else:
            print(f"\nScan results for {domain}:")

        # Print vulnerabilities
        if vulnerabilities:
            self.print_status("VULNERABILITIES FOUND:", "critical")
            for vuln in vulnerabilities:
                if 'VULNERABLE:' in vuln or 'XST' in vuln:
                    self.print_status(f"  {vuln}", "critical")
                else:
                    self.print_status(f"  {vuln}", "warning")
        else:
            self.print_status("No vulnerabilities found", "success")

        if not self.minimal:
            print("-" * 40)

def save_csv_results(all_results, csv_path):
    """Save a compact summary of results in CSV format"""
    with open(csv_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "domain",
            "allowed_methods",
            "unsafe_methods",
            "critical_count",
            "warning_count",
            "vulnerabilities"
        ])

        for r in all_results:
            vulns = r.get("vulnerabilities", [])
            crit_count = sum(1 for v in vulns if "VULNERABLE:" in v)
            warn_count = sum(1 for v in vulns if "WARNING:" in v or "functional" in v)

            writer.writerow([
                r.get("domain", ""),
                ";".join(r.get("allowed_methods", [])),
                ";".join(r.get("unsafe_methods", [])),
                crit_count,
                warn_count,
                ";".join(vulns),
            ])

def main():
    parser = argparse.ArgumentParser(description='HTTP Method Security Scanner')
    parser.add_argument('input_file', help='File containing list of domains (one per line)')
    parser.add_argument('-t', '--timeout', type=int, default=10, help='Request timeout in seconds (default: 10)')
    parser.add_argument('-o', '--output', help='Output file for JSON results')
    parser.add_argument('--csv-output', help='Output file for CSV summary')  # NEW
    parser.add_argument('-k', '--keep-files', action='store_true', help='Keep test files for manual verification')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-m', '--minimal', action='store_true',
                        help='Minimal console output (compact, fewer banners)')  # NEW

    args = parser.parse_args()

    # Check if input file exists
    if not os.path.isfile(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found")
        sys.exit(1)

    # Read domains from file
    try:
        with open(args.input_file, 'r') as f:
            domains = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)

    if not domains:
        print("No domains found in input file")
        sys.exit(1)

    if args.minimal:
        print(f"Scanning {len(domains)} domains...")
    else:
        print(f"Starting security scan for {len(domains)} domains...")
        if args.keep_files:
            print("Test files will be kept for manual verification")
        if args.verbose:
            print("Verbose mode enabled")

    scanner = SecurityScanner(
        timeout=args.timeout,
        keep_files=args.keep_files,
        verbose=args.verbose,
        minimal=args.minimal
    )
    all_results = []

    for i, domain in enumerate(domains, 1):
        try:
            # Ensure domain has scheme
            if not domain.startswith(('http://', 'https://')):
                domain = 'https://' + domain

            if args.minimal:
                print(f"[{i}/{len(domains)}] {domain}")
            else:
                print(f"\n[{i}/{len(domains)}] Processing: {domain}")

            results = scanner.scan_domain(domain)
            all_results.append(results)
            scanner.print_results(results)

            # Small delay to be respectful
            time.sleep(1)

        except KeyboardInterrupt:
            print("\nScan interrupted by user")
            break
        except Exception as e:
            if args.verbose and not args.minimal:
                print(f"Failed to scan {domain}: {e}")
            continue

    # Print all test URLs for manual verification
    if args.keep_files:
        scanner.print_test_urls()

    # Save results if output file specified
    if args.output and all_results:
        try:
            with open(args.output, 'w') as f:
                json.dump(all_results, f, indent=2)
            if not args.minimal:
                print(f"Results saved to {args.output}")
        except Exception as e:
            print(f"Failed to save results: {e}")

    # Save CSV results if requested
    if args.csv_output and all_results:
        try:
            save_csv_results(all_results, args.csv_output)
            if not args.minimal:
                print(f"CSV results saved to {args.csv_output}")
        except Exception as e:
            print(f"Failed to save CSV results: {e}")

    # Summary
    vulnerable_domains = [r for r in all_results if r['vulnerabilities']]
    critical_vulns = sum(1 for r in all_results if any('VULNERABLE:' in vuln for vuln in r['vulnerabilities']))

    if not args.minimal:
        print("\n" + "=" * 60)
        print("SCAN SUMMARY")
        print("=" * 60)
    else:
        print("\nSCAN SUMMARY")

    print(f"Scanned domains: {len(all_results)}")

    if vulnerable_domains:
        print(f"Vulnerable domains: {len(vulnerable_domains)}")
        print(f"Critical vulnerabilities: {critical_vulns}")

        print("Vulnerable domains:")
        for result in vulnerable_domains:
            crit_count = sum(1 for vuln in result['vulnerabilities'] if 'VULNERABLE:' in vuln)
            warn_count = sum(1 for vuln in result['vulnerabilities']
                             if 'WARNING:' in vuln or 'functional' in vuln)
            print(f"  - {result['domain']}: {crit_count} critical, {warn_count} warnings")
    else:
        print("No vulnerabilities found across all domains!")

if __name__ == "__main__":
    main()
