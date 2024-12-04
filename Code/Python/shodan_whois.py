import json
import subprocess
import argparse
import signal
import sys
import gzip
from tqdm import tqdm
from ipaddress import ip_address, ip_network
from time import sleep

# Global variables for storing progress
results = {}
failed_ips = {}

# Reserved and private networks
RESERVED_IP_RANGES = [
    ip_network("0.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("172.16.0.0/12"),
    ip_network("192.0.0.0/24"),
    ip_network("192.0.2.0/24"),
    ip_network("192.168.0.0/16"),
    ip_network("198.18.0.0/15"),
    ip_network("198.51.100.0/24"),
    ip_network("203.0.113.0/24"),
    ip_network("224.0.0.0/4"),
    ip_network("240.0.0.0/4"),
    ip_network("255.255.255.255/32"),
]

def is_valid_ip(ip):
    """
    Validate whether the given IP address is public and not reserved.
    """
    try:
        addr = ip_address(ip)
        return not any(addr in net for net in RESERVED_IP_RANGES)
    except ValueError:
        return False

def run_whois(ip):
    """
    Run the `whois` command for the given IP and extract domains from the response.
    """
    try:
        result = subprocess.run(["whois", ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if result.returncode != 0:
            raise Exception(result.stderr)

        domains = set()
        for line in result.stdout.splitlines():
            # Look for domain-related fields in the WHOIS output
            if "domain" in line.lower() or "nserver" in line.lower():
                parts = line.split(":")
                if len(parts) > 1:
                    domains.add(parts[1].strip())
        return list(domains)
    except Exception as e:
        print(f"Error retrieving WHOIS for IP {ip}: {e}")
        raise e

def save_progress(output_file, failed_file, compress):
    """
    Save the current progress to the specified output files.
    """
    if compress:
        with gzip.open(output_file + ".gz", 'wt', encoding='utf-8') as outfile:
            json.dump(results, outfile, indent=4)
        with gzip.open(failed_file + ".gz", 'wt', encoding='utf-8') as failfile:
            json.dump(failed_ips, failfile, indent=4)
    else:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            json.dump(results, outfile, indent=4)
        with open(failed_file, 'w', encoding='utf-8') as failfile:
            json.dump(failed_ips, failfile, indent=4)
    print(f"Progress saved to {output_file} and failed IPs to {failed_file}.")

def process_large_json(input_file, output_file, failed_file, increment_save, retry_attempts, retry_delay, compress):
    """
    Process a large JSON file line by line to extract IPs, perform WHOIS lookups,
    and save the results and failed IPs.
    """
    global results, failed_ips

    def signal_handler(sig, frame):
        print("\nInterrupt received. Saving progress...")
        save_progress(output_file, failed_file, compress)
        sys.exit(0)

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    with open(input_file, 'r', encoding='utf-8') as infile:
        lines = infile.readlines()
        for i, line in enumerate(tqdm(lines, desc="Processing lines")):
            try:
                data = json.loads(line.strip())
                ip = data.get("ip_str")
                port = data.get("port")
                existing_domains = data.get("domains", [])

                if ip and port:
                    # Validate IP
                    if not is_valid_ip(ip):
                        print(f"Skipping invalid or private IP: {ip}")
                        continue

                    if existing_domains:
                        # Use existing domains if available
                        if ip not in results:
                            results[ip] = {}
                        results[ip][str(port)] = existing_domains
                    else:
                        # Perform WHOIS lookup with retries
                        for attempt in range(retry_attempts):
                            try:
                                domains = run_whois(ip)
                                if domains:
                                    if ip not in results:
                                        results[ip] = {}
                                    results[ip][str(port)] = domains
                                    break
                                else:
                                    raise ValueError("No domains found")
                            except Exception:
                                if attempt + 1 == retry_attempts:
                                    # Mark as failed after exhausting retries
                                    if ip not in failed_ips:
                                        failed_ips[ip] = {}
                                    failed_ips[ip][str(port)] = []
                                else:
                                    sleep(retry_delay)
            except json.JSONDecodeError:
                print("Invalid JSON structure in line. Skipping.")
            except Exception as e:
                print(f"Error processing line: {e}")

            # Save progress incrementally
            if (i + 1) % increment_save == 0:
                save_progress(output_file, failed_file, compress)

    # Final save
    save_progress(output_file, failed_file, compress)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a large JSON file for IP and port WHOIS lookups using the Linux 'whois' command.")
    parser.add_argument("--input", type=str, required=True, help="Path to the input JSON file.")
    parser.add_argument("--output", type=str, default="output.json", help="Path to the output JSON file for successful lookups (default: output.json).")
    parser.add_argument("--failed", type=str, default="failed_ips.json", help="Path to the output JSON file for failed lookups (default: failed_ips.json).")
    parser.add_argument("--increment-save", type=int, default=100, help="Save progress after every N lines (default: 100).")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for WHOIS lookups (default: 3).")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="Delay between retries in seconds (default: 2.0).")
    parser.add_argument("--compress", action="store_true", help="Compress output files with gzip.")
    args = parser.parse_args()

    process_large_json(args.input, args.output, args.failed, args.increment_save, args.retry_attempts, args.retry_delay, args.compress)
