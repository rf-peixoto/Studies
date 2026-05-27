# Own-domain scanner

Small defensive recon pipeline for domains you own or are authorized to assess.

## Install

```bash
chmod +x install.sh scan.sh
./install.sh
```

External tools are optional but recommended:

```bash
go install github.com/tomnomnom/assetfinder@latest
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
```

Make sure your Go bin directory is in `PATH`, usually:

```bash
export PATH="$PATH:$HOME/go/bin"
```

## Usage

Create `domains.txt` with one bare domain per line:

```text
example.com
example.org
```

Run:

```bash
./scan.sh domains.txt
```

Useful options:

```bash
./scan.sh domains.txt --skip-nuclei
./scan.sh domains.txt --skip-httpx
./scan.sh domains.txt --output-dir scan_results
./scan.sh domains.txt --nuclei-severity medium,high,critical
./scan.sh domains.txt --nuclei-rate-limit 10
```

## Output

```text
scan_results/
  last_run_summary.json
  example.com/
    latest/
      subdomains.txt
      ip_addresses.txt
      host_to_ips.json
      dns_records.json
      ptr_records.json
      asn_records.json
      shodan_internetdb.json
      alive_targets.jsonl
      alive_targets.json
      alive_targets.txt
      nuclei_results.jsonl
      diff.json
      metadata.json
      summary.md
    history/
      YYYYMMDD_HHMMSS/
        ...same files...
```

## Notes

- Input accepts only bare domains, not URLs, wildcards, shell syntax, or paths.
- Commands are executed without shell interpretation.
- The scanner keeps a timestamped history and refreshes a `latest/` directory per domain.
- ProjectDiscovery `httpx` is required for live HTTP probing. The unrelated Python `httpx` CLI is intentionally ignored.


## New enrichment and output behavior

This version keeps richer passive and active data:

- Shodan InternetDB output includes ports, CVEs, CPEs, tags, hostnames, and mapped subdomains.
- DNS enrichment writes A, AAAA, MX, TXT, CNAME, NS, and CAA records when `aiodns` is available. Without `aiodns`, it still resolves A/AAAA using the Python resolver.
- IPv6 is preserved instead of silently discarded.
- crt.sh is queried by default and can be disabled with `--skip-crtsh`.
- PTR and ASN/RDAP enrichment are saved as structured JSON.
- ProjectDiscovery httpx runs with JSONL output, status codes, titles, redirects, and technology detection.
- Nuclei runs with JSONL output and per-severity summary counters.
- A lightweight `diff.json` compares the current scan with the previous history entry.

Useful additional options:

```bash
./scan.sh domains.txt --skip-crtsh
./scan.sh domains.txt --skip-shodan
./scan.sh domains.txt --skip-asn
./scan.sh domains.txt --httpx-threads 75
./scan.sh domains.txt --nuclei-tags ssl,misconfig
./scan.sh domains.txt --nuclei-templates ~/nuclei-templates/http
./scan.sh domains.txt --dns-timeout 5
```
