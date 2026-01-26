#!/usr/bin/env python3

import ipaddress
import sys


def normalize_ipv6(ip_str: str) -> dict:
    try:
        ip = ipaddress.IPv6Address(ip_str)
    except ipaddress.AddressValueError:
        raise ValueError(f"Invalid IPv6 address: {ip_str}")

    full = ip.exploded          # Fully expanded
    compressed = ip.compressed  # RFC 5952 compressed form

    is_abbreviated = ip_str.lower() != full.lower()

    return {
        "input": ip_str,
        "is_abbreviated": is_abbreviated,
        "full": full,
        "abbreviated": compressed
    }


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <ipv6_address>")
        sys.exit(1)

    ip_str = sys.argv[1]

    try:
        result = normalize_ipv6(ip_str)
    except ValueError as e:
        print(e)
        sys.exit(2)

    print(f"Input IPv6       : {result['input']}")
    print(f"Is abbreviated?  : {result['is_abbreviated']}")
    print(f"Full (expanded)  : {result['full']}")
    print(f"Abbreviated (::) : {result['abbreviated']}")


if __name__ == "__main__":
    main()
