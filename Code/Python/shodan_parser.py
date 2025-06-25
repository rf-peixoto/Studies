#!/usr/bin/env python3
import json
import csv
import argparse
import ipaddress
import sys

def load_records(path):
    """
    Load JSON records from a file. Supports:
      - A single JSON array at top level
      - One JSON object per line
    """
    text = open(path, 'r', encoding='utf-8').read().strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records

def extract_fields(record):
    """
    From one record, return a dict with only:
      ip, asn, org, product,
      city, region_code, country_code, country_name, latitude, longitude
    """
    # IP address: prefer dotted-string, else convert integer
    ip = record.get('ip_str')
    if ip is None and 'ip' in record:
        try:
            ip = str(ipaddress.IPv4Address(record['ip']))
        except Exception:
            ip = record['ip']

    loc = record.get('location', {}) or {}
    return {
        'ip': ip,
        'asn': record.get('asn'),
        'org': record.get('org'),
        'product': record.get('product'),
        'city': loc.get('city'),
        'region_code': loc.get('region_code'),
        'country_code': loc.get('country_code'),
        'country_name': loc.get('country_name'),
        'latitude': loc.get('latitude'),
        'longitude': loc.get('longitude'),
    }

def main():
    parser = argparse.ArgumentParser(
        description="Parse JSON (array or NDJSON) and output a CSV with selected fields."
    )
    parser.add_argument('input', help="Path to input JSON file")
    parser.add_argument('output', help="Path to output CSV file")
    args = parser.parse_args()

    try:
        records = load_records(args.input)
    except Exception as e:
        sys.exit(f"Error loading JSON: {e}")

    # Prepare CSV
    fieldnames = [
        'ip', 'asn', 'org', 'product',
        'city', 'region_code', 'country_code', 'country_name',
        'latitude', 'longitude'
    ]
    try:
        with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records:
                row = extract_fields(rec)
                writer.writerow(row)
    except Exception as e:
        sys.exit(f"Error writing CSV: {e}")

    print(f"Wrote {len(records)} rows to {args.output}")

if __name__ == '__main__':
    main()
