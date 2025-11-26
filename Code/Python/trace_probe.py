#!/usr/bin/env python3
"""
TRACE Method Security Tester
Tests for TRACE method and XST (Cross-Site Tracing) vulnerability
"""

import requests
import sys
import random
import argparse
from colorama import Fore, Style, init

# Initialize colorama for cross-platform colored output
init(autoreset=True)

def print_status(message, level="info"):
    """Print colored status messages"""
    colors = {
        "critical": Fore.RED + Style.BRIGHT,
        "warning": Fore.YELLOW,
        "success": Fore.GREEN,
        "info": Fore.BLUE,
        "url": Fore.CYAN,
    }
    color = colors.get(level, "")
    print(f"{color}{message}")

def test_trace_method(domain):
    """Test TRACE method on a single domain"""
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*60}")
    print(f"TRACE Method Test for: {domain}")
    print(f"{'='*60}")
    
    # Ensure domain has scheme
    if not domain.startswith(('http://', 'https://')):
        domain = 'https://' + domain
        print_status(f"Added https:// prefix: {domain}", "info")

    # Generate unique test values
    test_header = f"X-Test-Header-{random.randint(1000, 9999)}"
    test_cookie = f"test-cookie-{random.randint(1000, 9999)}"
    test_body = f"TRACE-Body-Test-{random.randint(1000, 9999)}"

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'TRACE-Tester/1.0',
        'X-Custom-Test': test_header,
        'Accept': 'text/plain'
    })

    results = {
        'trace_allowed': False,
        'status_code': None,
        'echoes_headers': False,
        'echoes_cookies': False,
        'echoes_body': False,
        'vulnerable_headers': [],
        'response_length': 0,
        'xst_vulnerable': False
    }

    try:
        print_status("Sending TRACE request with test headers...", "info")
        
        # Test 1: Basic TRACE with custom headers
        response = session.request(
            'TRACE', 
            domain,
            timeout=10
        )
        
        results['status_code'] = response.status_code
        results['trace_allowed'] = response.status_code == 200
        results['response_length'] = len(response.content)

        print_status(f"Response Status Code: {response.status_code}", "info")
        
        if results['trace_allowed']:
            print_status("✓ TRACE method is ENABLED", "warning")
            print_status(f"Response length: {len(response.content)} bytes", "info")
            
            response_text = response.text
            print(f"\n{Fore.CYAN}Response Headers:{Style.RESET_ALL}")
            for header, value in response.headers.items():
                print(f"  {header}: {value}")
            
            print(f"\n{Fore.CYAN}Response Body (first 1000 chars):{Style.RESET_ALL}")
            print(response_text[:1000])
            
            # Analyze what gets echoed back
            print(f"\n{Fore.CYAN}Analysis:{Style.RESET_ALL}")
            
            # Check headers
            if test_header in response_text:
                results['echoes_headers'] = True
                results['vulnerable_headers'].append('X-Custom-Test')
                print_status("✓ Custom headers are echoed back", "critical")
            else:
                print_status("✗ Custom headers not echoed", "info")
                
            if 'TRACE-Tester' in response_text:
                results['echoes_headers'] = True
                results['vulnerable_headers'].append('User-Agent')
                print_status("✓ User-Agent header is echoed back", "critical")
            else:
                print_status("✗ User-Agent not echoed", "info")
                
            # Test 2: TRACE with cookies
            print_status("\nTesting TRACE with cookies...", "info")
            response_with_cookies = session.request(
                'TRACE',
                domain,
                cookies={'test_cookie': test_cookie},
                timeout=10
            )
            
            if response_with_cookies.status_code == 200 and test_cookie in response_with_cookies.text:
                results['echoes_cookies'] = True
                results['vulnerable_headers'].append('Cookies')
                print_status("✓ Cookies are echoed back", "critical")
            else:
                print_status("✗ Cookies not echoed", "info")
                
            # Test 3: TRACE with request body
            print_status("\nTesting TRACE with request body...", "info")
            response_with_body = session.request(
                'TRACE',
                domain,
                data=test_body,
                timeout=10
            )
            
            if response_with_body.status_code == 200 and test_body in response_with_body.text:
                results['echoes_body'] = True
                print_status("✓ Request body is echoed back", "critical")
            else:
                print_status("✗ Request body not echoed", "info")
                
            # Determine XST vulnerability
            results['xst_vulnerable'] = (results['echoes_headers'] or 
                                       results['echoes_cookies'] or 
                                       results['echoes_body'])
                                       
            print(f"\n{Fore.CYAN}{'='*60}")
            if results['xst_vulnerable']:
                print_status("✗ XST VULNERABILITY CONFIRMED!", "critical")
                print_status("The server reflects request data in TRACE responses", "critical")
                print_status("This can be exploited to steal cookies via XSS", "critical")
                
                if results['vulnerable_headers']:
                    print_status(f"Vulnerable elements: {', '.join(results['vulnerable_headers'])}", "critical")
                    
                print(f"\n{Fore.YELLOW}Remediation:{Style.RESET_ALL}")
                print("  - Disable TRACE method on the server")
                print("  - Configure web server to return 405 for TRACE requests")
                print("  - Use security headers to restrict HTTP methods")
            else:
                print_status("✓ No XST vulnerability detected", "success")
                print_status("TRACE is enabled but doesn't reflect sensitive data", "info")
                
        else:
            print_status("✓ TRACE method is NOT enabled or returns error", "success")
            if response.status_code == 405:
                print_status("Server correctly returns '405 Method Not Allowed'", "success")
            elif response.status_code == 403:
                print_status("Server returns '403 Forbidden' for TRACE", "info")
            else:
                print_status(f"Server returns: {response.status_code} {response.reason}", "info")

    except requests.ConnectionError:
        print_status("✗ Connection failed - domain may be unreachable", "critical")
    except requests.Timeout:
        print_status("✗ Request timed out", "critical")
    except requests.RequestException as e:
        print_status(f"✗ Request failed: {e}", "critical")
    except KeyboardInterrupt:
        print_status("\nTest interrupted by user", "warning")
        sys.exit(1)
    
    print(f"{Fore.CYAN}{'='*60}")
    return results

def manual_verification_commands(domain):
    """Print commands for manual verification"""
    print(f"\n{Fore.CYAN}Manual Verification Commands:{Style.RESET_ALL}")
    print(f"curl -X TRACE {domain} -v")
    print(f"curl -X TRACE -H 'X-Test-Header: test123' {domain}")
    print(f"curl -X TRACE -H 'Cookie: test=value' {domain}")
    print(f"curl -X TRACE -d 'test=body' {domain}")

def main():
    parser = argparse.ArgumentParser(description='Test TRACE method for XST vulnerability')
    parser.add_argument('domain', help='Domain to test (with or without http://)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show more detailed output')
    
    args = parser.parse_args()
    
    if not args.domain:
        print("Error: Please provide a domain to test")
        print("Usage: python trace_test.py example.com")
        sys.exit(1)
    
    try:
        results = test_trace_method(args.domain)
        manual_verification_commands(args.domain)
        
        # Exit code based on results
        if results.get('xst_vulnerable'):
            sys.exit(2)  # Vulnerable
        elif results.get('trace_allowed'):
            sys.exit(1)  # TRACE enabled but not vulnerable
        else:
            sys.exit(0)  # TRACE not enabled - safe
            
    except Exception as e:
        print_status(f"Unexpected error: {e}", "critical")
        sys.exit(3)

if __name__ == "__main__":
    main()
