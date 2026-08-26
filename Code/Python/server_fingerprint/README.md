# Infrastructure Fingerprinting for Threat-Actor Clustering

Two scripts:

- **`infra_fingerprint.py`** — collects every stable, comparable signal from a
  target's network / TLS / certificate / HTTP layers and emits one JSON record
  per host (JSON Lines).
- **`cluster_fingerprints.py`** — reads that output and groups hosts by shared
  fingerprints, surfacing overlapping actor infrastructure.

## Install
```bash
pip install -r requirements.txt
```

## Collect
```bash
# single target
python3 infra_fingerprint.py https://suspect.example

# many targets, self-signed certs allowed, write JSONL
python3 infra_fingerprint.py -i targets.txt --insecure -o run.jsonl -w 16
```
Targets may be given in any of these forms (mixed freely in a file or on the
command line):

```
163.245.205.62                        bare IPv4        -> https:443
163.245.205.62:5000                   IPv4 + port      -> http:5000  (non-TLS port)
2606:4700:4700::1111                  bare IPv6        -> https:443
[2606:4700:4700::1111]:8443           IPv6 + port      -> https:8443
example.com  /  example.com:8443      hostname (+port)
http://163.245.205.62:5000/sessions   URL w/ IP, port and path (path is fetched)
https://example.com/panel?a=1         URL w/ path + query (preserved)
```

Rules: when no scheme is given, the port decides it (443/4443/8443/9443/6443/…
→ https, everything else → http); IPv6 is auto-bracketed in the request URL;
paths and query strings are preserved and fetched; SNI is omitted for raw-IP
targets (invalid for IP literals). Use `--port N` to supply a port for bare
hosts that don't carry one (an explicit port in the target always wins).

## Cluster
```bash
python3 cluster_fingerprints.py run.jsonl --simhash-threshold 6
```

## What gets fingerprinted
| Layer   | Signals |
|---------|---------|
| Network | resolved IPs, reverse DNS (PTR) |
| TLS     | negotiated version/cipher/ALPN, **JARM** (active), **JA4S** (ServerHello) |
| Cert    | full-chain SHA256/SHA1, subject, issuer, SANs, serial, validity, **SPKI SHA256** (survives reissue), signature algorithm, JA4X-style issuer/subject RDN hashes |
| HTTP    | status, **header-order** hash, header-set hash, Server / X-Powered-By, cookie names, redirect chain, title, meta-generator, **favicon mmh3** (Shodan-style), body SHA256, normalized-body SHA256, **HTML structural-skeleton** hash, **body SimHash** (fuzzy near-dup), extracted repeating strings (copyright, external JS/CSS hosts, tracking IDs, HTML comments) |
| Probes  | random-path 404/default-page hash, plaintext-HTTP root behavior |

Each record ends with a compact `cluster_key` — the most stable cross-host
signals bundled for quick diffing.

## Best signals for attribution
- **SPKI SHA256** — same key reused across reissued certs / multiple hosts.
- **JARM + JA4S** — the TLS stack/config; identical across an actor's servers built from the same image.
- **favicon mmh3** + **structural hash** — templated panels / C2 login pages.
- **body SimHash** — near-identical pages even after cosmetic edits (fuzzy match).
- **header-order hash** — the server/framework's header emission order.

## Scope
Performs only standard client connections plus an active TLS probe (JARM/JA4S) —
the same traffic a browser and a TLS scanner produce. Intended for defensive CTI
on infrastructure you're authorized to investigate.
