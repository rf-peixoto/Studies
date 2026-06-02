# Recon Scanner Dashboard

A Flask web app to visualize reconnaissance scanner output ZIP files.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.

## Usage

1. Drop or browse a scanner output `.zip` on the upload screen
2. The app parses and visualizes all scan data across six tabs:

| Tab | Contents |
|-----|----------|
| **Overview** | Stats summary, nuclei findings by template, errors, scan config |
| **Nuclei** | All nuclei findings — filter by severity, search, star/flag findings |
| **Subdomains** | All resolved subdomains with IPs, ports, CVE counts, tags |
| **IPs** | All IP addresses with ASN info, open ports, CVEs, CPEs |
| **CVEs** | CVEs from Shodan InternetDB, grouped by CVE ID, linked to NVD |
| **DNS** | All DNS records filterable by type (A, AAAA, MX, TXT, NS, CNAME) |

## Features

- **Star (★)** — mark findings for follow-up
- **Flag (⚑)** — mark high-priority items (highlighted in amber)
- **→** — open detail drawer with full finding info
- **Analyst notes** — add notes per nuclei finding in the drawer
- **Export CSV / TXT** — export filtered results
- **Click any CVE** — opens NVD for that CVE in a new tab
- **Filter + search** — combine severity/type filters with free-text search

## Expected ZIP Structure

```
domain.com/
  latest/
    metadata.json
    nuclei_results.jsonl
    shodan_internetdb.json
    dns_records.json
    asn_records.json
    host_to_ips.json
    ptr_records.json
    subdomains.txt
    ipv4_addresses.txt
    ipv6_addresses.txt
    diff.json
  history/
    YYYYMMDD_HHMMSS/
      (same files)
```
