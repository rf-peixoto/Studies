# Own-Domain Scanner

## Standard workflow

The normal workflow is now:

```bash
./install.sh
./scan.sh domains.txt
```

`install.sh` starts Docker when possible, creates/updates the local `.venv`, installs Python requirements into that venv, and builds the Docker image. The Docker image also creates its own internal venv at `/opt/scanner-venv`.

`scan.sh` is intentionally only a thin wrapper: it receives the domains file and forwards it to the Dockerized scanner through `start.sh`.

Example with options:

```bash
./scan.sh domains.txt --skip-nuclei
./scan.sh domains.txt --domains-concurrency 3 --nuclei-severity medium,high,critical
```


Small passive/semi-active scanner for domains you control. This package is Docker-first: `install.sh` builds the image, and `start.sh` runs scans through Docker Compose with the configured resource limits.

## Quick start

```bash
chmod +x install.sh start.sh scan.sh
./install.sh
```

Create a domains file:

```bash
cat > domains.txt << EOF
example.com
example.org
EOF
```

Start a scan:

```bash
./start.sh domains.txt
```

Results are written to:

```text
./scan_results/
```

The compatibility wrapper also works:

```bash
./start.sh domains.txt
```

## Docker resource limits

The Compose service is capped with:

```yaml
cpus: "4.0"
mem_limit: 10g
memswap_limit: 10g
```

## Examples

```bash
./start.sh domains.txt --skip-nuclei
./start.sh domains.txt --skip-httpx
./start.sh domains.txt --domains-concurrency 3
./start.sh domains.txt --nuclei-severity medium,high,critical
./start.sh domains.txt --nuclei-rate-limit 50
./start.sh domains.txt --nuclei-tags ssl,misconfig
./start.sh domains.txt --skip-crtsh --skip-shodan
```

## What `install.sh` does

`install.sh` no longer creates a host Python virtual environment. It checks Docker/Compose, creates the local `data/` and `scan_results/` folders, and runs:

```bash
docker compose build
```

The image installs the required Python packages plus `assetfinder`, `subfinder`, `httpx`, and `nuclei` inside the container.

## What `start.sh` does

`start.sh` copies your chosen domains file to `./data/domains.txt` and runs:

```bash
docker compose run --rm scanner /data/domains.txt --output-dir /output [options]
```

This keeps host paths simple and ensures output is persisted under `./scan_results/`.

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
./start.sh domains.txt --skip-crtsh
./start.sh domains.txt --skip-shodan
./start.sh domains.txt --skip-asn
./start.sh domains.txt --httpx-threads 75
./start.sh domains.txt --nuclei-tags ssl,misconfig
./start.sh domains.txt --nuclei-templates ~/nuclei-templates/http
./start.sh domains.txt --dns-timeout 5
```

## Docker / Docker Compose

This project includes a container build so the scanner can run isolated with fixed resource limits.

### Expected local layout

```text
scanner/
  data/
    domains.txt
  scan_results/
  Dockerfile
  docker-compose.yml
```

Create the input/output directories:

```bash
mkdir -p data scan_results
printf 'example.com\n' > data/domains.txt
```

Build and run with Docker Compose:

```bash
docker compose build
docker compose run --rm scanner
```

The Compose file limits the scanner container to:

```yaml
cpus: "4.0"
mem_limit: 10g
memswap_limit: 10g
```

Results are written to `./scan_results` on the host, mounted as `/output` inside the container. The input file is mounted read-only from `./data/domains.txt` to `/data/domains.txt`.

To pass scanner flags, override the command:

```bash
docker compose run --rm scanner /data/domains.txt --output-dir /output --skip-nuclei
```

Or edit `docker-compose.yml`:

```yaml
command: ["/data/domains.txt", "--output-dir", "/output", "--skip-nuclei"]
```

### Docker without Compose

```bash
docker build -t own-domain-scanner .
docker run --rm \
  --cpus="4.0" \
  --memory="10g" \
  --memory-swap="10g" \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/scan_results:/output" \
  own-domain-scanner /data/domains.txt --output-dir /output
```


### Docker install/start behavior

`./install.sh` now does three things:

1. Checks whether Docker is installed.
2. Tries to start the Docker daemon using `systemctl` or `service` when it is not reachable.
3. Builds the scanner image with Docker Compose.

Then run scans with:

```bash
./start.sh domains.txt
```

The container is limited by Compose to 4 CPUs and 10 GB RAM.

If Docker still does not start, run:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Then log out and back in before running `./install.sh` again.