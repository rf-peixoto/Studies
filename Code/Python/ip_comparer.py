import ipaddress
import os
import sys

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'

def parse_input(arg):
    """Return list of parsed IPs or networks from file or direct input"""
    entries = []
    if os.path.isfile(arg):
        with open(arg, 'r') as f:
            lines = f.readlines()
    else:
        lines = [arg]

    for line in lines:
        line = line.strip().split(":")[0]
        if not line:
            continue
        try:
            if '/' in line:
                entries.append(ipaddress.ip_network(line, strict=False))
            else:
                entries.append(ipaddress.ip_address(line))
        except ValueError:
            continue
    return entries

def match_ips(ips_a, ips_b):
    exact_matches = []
    range_matches = []

    for a in ips_a:
        for b in ips_b:
            if isinstance(a, ipaddress._BaseAddress) and isinstance(b, ipaddress._BaseAddress):
                if a == b:
                    exact_matches.append((str(a), str(b)))
            elif isinstance(a, ipaddress._BaseNetwork) and isinstance(b, ipaddress._BaseAddress):
                if b in a:
                    range_matches.append((str(b), str(a)))
            elif isinstance(a, ipaddress._BaseAddress) and isinstance(b, ipaddress._BaseNetwork):
                if a in b:
                    range_matches.append((str(a), str(b)))
            elif isinstance(a, ipaddress._BaseNetwork) and isinstance(b, ipaddress._BaseNetwork):
                if a.overlaps(b):
                    range_matches.append((str(a), str(b)))
    return exact_matches, range_matches

def main():
    if len(sys.argv) != 3:
        print(f"{RED}Usage: python ip_compare_pretty.py <input_a> <input_b>{RESET}")
        sys.exit(1)

    ips_a = parse_input(sys.argv[1])
    ips_b = parse_input(sys.argv[2])

    exact, ranges = match_ips(ips_a, ips_b)

    print(f"\n{BOLD}{CYAN}=== Exact Matches ==={RESET}")
    if exact:
        for a, b in exact:
            print(f"{GREEN}✅ {a} == {b}{RESET}")
    else:
        print(f"{RED}❌ No exact matches found{RESET}")

    print(f"\n{BOLD}{CYAN}=== Range Matches ==={RESET}")
    if ranges:
        for ip, net in ranges:
            print(f"{YELLOW}🟡 {ip} ∈ {net}{RESET}")
    else:
        print(f"{RED}❌ No range matches found{RESET}")

if __name__ == "__main__":
    main()
