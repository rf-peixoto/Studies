#!/usr/bin/env python3
"""Bulk DNS resolution and passive HTTP WAF fingerprinting.

Optional --active uses the external wafw00f CLI for additional WAF fingerprints.
Only scan domains for which you have permission to perform active testing.
"""
import argparse
import concurrent.futures
import csv
import ipaddress
import json
from functools import lru_cache
import re
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

import requests
import urllib3

try:
    import dns.resolver
except ImportError:
    dns = None

UA = 'WafAudit/1.0 (passive HTTP fingerprinting)'
# Evidence categories are deliberately conservative: CDN hints are not proof of WAF.
SIGNATURES = [
    ('Cloudflare', 'WAF_INDICATOR', [(r'(?im)^cf-ray:', 'header'), (r'(?im)^server:\s*cloudflare\s*$', 'header')]),
    ('Akamai', 'WAF_INDICATOR', [(r'(?im)^x-akamai-', 'header'), (r'(?im)^akamai-grn:', 'header')]),
    ('Imperva/Incapsula', 'WAF_INDICATOR', [(r'(?im)^x-iinfo:', 'header'), (r'(?i)incap_ses_|visid_incap_', 'cookie')]),
    ('Sucuri', 'WAF_INDICATOR', [(r'(?im)^x-sucuri-', 'header'), (r'(?im)^server:\s*sucuri/cloudproxy', 'header')]),
    ('AWS CloudFront', 'CDN_ONLY', [(r'(?im)^x-amz-cf-id:', 'header'), (r'(?im)^x-amz-cf-pop:', 'header')]),
    ('AWS WAF', 'WAF_INDICATOR', [(r'(?i)awswaf', 'cookie')]),
    ('Fastly', 'CDN_ONLY', [(r'(?im)^x-served-by:.*cache-', 'header'), (r'(?im)^x-fastly-', 'header')]),
    ('Azure Front Door', 'CDN_ONLY', [(r'(?im)^x-azure-ref:', 'header')]),
    ('F5 BIG-IP', 'WAF_INDICATOR', [(r'(?i)bigipserver|ts[a-z0-9]{6,}=', 'cookie')]),
    ('Barracuda', 'WAF_INDICATOR', [(r'(?i)barra_counter_session|bni__barracuda', 'cookie')]),
]
DNS_HINTS = [
    ('Cloudflare', r'cloudflare\.net\.?$'),
    ('Akamai', r'(akamai|edgesuite|edgekey|akamaiedge)\.net\.?$'),
    ('Imperva/Incapsula', r'(incapdns|impervadns)\.net\.?$'),
    ('AWS CloudFront', r'cloudfront\.net\.?$'),
    ('Fastly', r'(fastly\.net|fastlylb\.net)\.?$'),
    ('Azure Front Door', r'azurefd\.net\.?$'),
    ('Sucuri', r'sucuri\.net\.?$'),
]


def normalize(raw):
    raw = raw.strip()
    if not raw or raw.startswith('#'):
        return None
    if '://' not in raw:
        raw = 'https://' + raw
    p = urlsplit(raw)
    if p.scheme not in ('http', 'https') or not p.hostname:
        raise ValueError('invalid HTTP(S) domain or URL')
    host = p.hostname.encode('idna').decode('ascii').lower()
    # Never retain userinfo, fragments, or query secrets in output.
    netloc = f'[{host}]' if ':' in host else host
    if p.port:
        netloc += f':{p.port}'
    return f'{p.scheme}://{netloc}/', host


def lookup(host, timeout):
    ips, aliases, errors = set(), set(), []
    try:
        ipaddress.ip_address(host)
        return [host], [], ''
    except ValueError:
        pass
    if dns is not None:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        for typ in ('A', 'AAAA', 'CNAME'):
            try:
                ans = resolver.resolve(host, typ, raise_on_no_answer=False)
                for r in ans:
                    if typ == 'CNAME':
                        aliases.add(str(r.target).rstrip('.'))
                    else:
                        ips.add(str(r))
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                pass
            except Exception as exc:
                errors.append(f'{typ}:{type(exc).__name__}')
    else:
        try:
            for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
                ips.add(info[4][0])
        except OSError as exc:
            errors.append(str(exc))
    return sorted(ips), sorted(aliases), '; '.join(errors)


def fingerprint(resp, aliases):
    header_blob = '\n'.join(f'{k}: {v}' for k, v in resp.headers.items())
    cookies = resp.headers.get('Set-Cookie', '')
    providers, evidence, has_waf_indicator = set(), [], False
    for provider, kind, checks in SIGNATURES:
        for regex, source in checks:
            haystack = cookies if source == 'cookie' else header_blob
            if re.search(regex, haystack):
                providers.add(provider)
                evidence.append(f'{provider}: {source} signature')
                if kind == 'WAF_INDICATOR':
                    has_waf_indicator = True
                break
    for cname in aliases:
        for provider, pattern in DNS_HINTS:
            if re.search(pattern, cname, re.I):
                providers.add(provider)
                evidence.append(f'{provider}: CNAME {cname}')
    # Block pages are more meaningful with a provider signature, but still not proof.
    body = resp.text[:8192].lower()
    blocking = resp.status_code in (403, 406, 429, 503) and any(
        x in body for x in ('access denied', 'request blocked', 'security policy',
                           'attention required', 'web application firewall', 'captcha')
    )
    if blocking:
        evidence.append(f'HTTP {resp.status_code} with possible security challenge')
    if has_waf_indicator and blocking:
        status = 'WAF_LIKELY'
    elif has_waf_indicator:
        status = 'WAF_POSSIBLE'
    elif blocking:
        status = 'SECURITY_BLOCK_POSSIBLE'
    elif providers:
        status = 'CDN_OR_PROXY_ONLY'
    else:
        status = 'NO_WAF_EVIDENCE'
    return status, ', '.join(sorted(providers)), '; '.join(evidence)


def active_detect(url, timeout):
    cmd = ['wafw00f', '--no-colors', '-T', str(timeout), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 8 + 15, check=False)
        out = result.stdout + '\n' + result.stderr
        found = re.findall(r'(?:is behind|behind)\s+(.+?)\s+WAF\.', out, re.I)
        if found:
            return 'WAF_DETECTED_ACTIVE', ', '.join(sorted(set(found))), ''
        if 'No WAF detected' in out or 'No WAF was detected' in out:
            return 'NO_WAF_EVIDENCE', '', ''
        return '', '', f'wafw00f returned code {result.returncode}; inspect standalone output'
    except (OSError, subprocess.TimeoutExpired) as exc:
        return '', '', f'active scan error: {exc}'



# Official provider IP inventories (CDN attribution, NOT evidence of enabled WAF).
# Keep scope explicit: unknown hosting providers are not automatically "unprotected".
IP_SOURCES = {
    'Cloudflare': ('https://www.cloudflare.com/ips-v4', 'https://www.cloudflare.com/ips-v6'),
    'Fastly': ('https://api.fastly.com/public-ip-list',),
}


def load_ip_ranges(timeout):
    networks, warnings = [], []
    for provider, urls in IP_SOURCES.items():
        for url in urls:
            try:
                response = requests.get(url, timeout=timeout, headers={'User-Agent': UA})
                response.raise_for_status()
                if provider == 'Fastly':
                    obj = response.json()
                    prefixes = obj.get('addresses', []) + obj.get('ipv6_addresses', [])
                else:
                    prefixes = response.text.splitlines()
                parsed = [ipaddress.ip_network(x.strip(), strict=False) for x in prefixes if x.strip()]
                if not parsed:
                    raise ValueError('empty prefix list')
                networks.extend((net, provider) for net in parsed)
            except (requests.RequestException, ValueError, KeyError) as exc:
                warnings.append(f'{provider} ranges unavailable ({url}): {exc}')
    return networks, warnings


def match_ip_providers(ips, networks):
    providers = set()
    for text in ips:
        address = ipaddress.ip_address(text)
        for net, provider in networks:
            if address in net:
                providers.add(provider)
    return sorted(providers)


def classify_focus(row):
    status = row.get('classification', '')
    # Conservative triage. Only DNS+HTTP completed with no recognizable signal
    # can be candidates. This is never definitive proof of no WAF/CDN.
    if (status == 'NO_WAF_EVIDENCE' and row.get('ip_lookup_status') == 'ok'
            and (row.get('ipv4') or row.get('ipv6')) and not row.get('error')):
        return 'CANDIDATE_NO_WAF_CDN'
    if status in ('WAF_LIKELY', 'WAF_POSSIBLE', 'WAF_DETECTED_ACTIVE',
                  'CDN_OR_PROXY_ONLY', 'DNS_CDN_HINT_ONLY', 'IP_CDN_DETECTED'):
        return 'PROTECTED_OR_CDN_INDICATED'
    return 'INCONCLUSIVE'

def inspect(item, timeout, verify, active, networks=None, ip_lookup_status="disabled"):
    raw, url, host = item
    row = dict(input=raw, url=url, hostname=host, ipv4='', ipv6='', cname='',
               http_status='', final_url='', classification='', provider='', evidence='', error='',
               ip_provider='', ip_lookup_status=ip_lookup_status, focus_status='')
    ips, aliases, err = lookup(host, timeout)
    row['ipv4'] = ';'.join(x for x in ips if ':' not in x)
    row['ipv6'] = ';'.join(x for x in ips if ':' in x)
    row['cname'] = ';'.join(aliases)
    if networks is not None:
        ip_providers = match_ip_providers(ips, networks)
        row['ip_provider'] = '; '.join(ip_providers)
        if ip_providers:
            row['evidence'] = 'IP matches published provider range: ' + ', '.join(ip_providers)
    if err and not ips:
        row['error'] = err
    try:
        with requests.Session() as session:
            session.trust_env = False  # Do not silently route target requests through env proxies.
            resp = session.get(url, headers={'User-Agent': UA}, timeout=timeout,
                               verify=verify, allow_redirects=True, stream=True)
            row['http_status'] = resp.status_code
            row['final_url'] = resp.url
            # Bound memory and wire reads (up to 8 KiB response content).
            resp._content = next(resp.iter_content(chunk_size=8192), b'')
            row['classification'], row['provider'], http_evidence = fingerprint(resp, aliases)
            row['evidence'] = '; '.join(filter(None, [row['evidence'], http_evidence]))
            resp.close()
    except requests.RequestException as exc:
        row['classification'] = 'HTTP_ERROR'
        row['error'] = f'{row["error"]}; {exc}' if row['error'] else str(exc)
        # DNS alone can identify a CDN, but not prove that a WAF is deployed.
        for cname in aliases:
            for provider, pattern in DNS_HINTS:
                if re.search(pattern, cname, re.I):
                    row['classification'] = 'DNS_CDN_HINT_ONLY'
                    row['provider'] = provider
                    row['evidence'] = '; '.join(filter(None, [row['evidence'], f'CNAME {cname}']))
                    break
    if active:
        status, provider, error = active_detect(url, timeout)
        if status == 'WAF_DETECTED_ACTIVE':
            row['classification'] = status
            row['provider'] = provider or row['provider']
            row['evidence'] = (row['evidence'] + '; wafw00f signature').strip('; ')
        if error:
            row['error'] = (row['error'] + '; ' + error).strip('; ')
    if row['ip_provider']:
        existing = set(filter(None, (x.strip() for x in row['provider'].split(','))))
        existing.update(x.strip() for x in row['ip_provider'].split(';'))
        row['provider'] = ', '.join(sorted(existing))
        if row['classification'] in ('NO_WAF_EVIDENCE', 'HTTP_ERROR', 'SECURITY_BLOCK_POSSIBLE'):
            row['classification'] = 'IP_CDN_DETECTED'
    row['focus_status'] = classify_focus(row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('targets', help='Text file with one domain or HTTP(S) URL per line')
    parser.add_argument('-o', '--output', default='waf_results.csv')
    parser.add_argument('-w', '--workers', type=int, default=10)
    parser.add_argument('-t', '--timeout', type=float, default=8)
    parser.add_argument('--active', action='store_true', help='Run wafw00f probes (authorized targets only)')
    parser.add_argument('--insecure', action='store_true', help='Disable TLS certificate validation')
    parser.add_argument('--ip-check', action='store_true', help='Match resolved IPs against published Cloudflare/Fastly CDN ranges')
    parser.add_argument('--focus-unprotected', action='store_true', help='Also export likely non-WAF/non-CDN candidates, and inconclusive targets, to separate files; implies --ip-check')
    args = parser.parse_args()
    if args.workers < 1 or args.timeout <= 0:
        parser.error('workers and timeout must be positive')
    if args.active and not shutil.which('wafw00f'):
        parser.error('--active requires wafw00f installed and in PATH')
    if args.insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    items, invalid, seen = [], [], set()
    with open(args.targets, encoding='utf-8-sig') as f:
        for n, line in enumerate(f, 1):
            raw = line.strip()
            try:
                normalized = normalize(raw)
                if normalized and normalized[0] not in seen:
                    seen.add(normalized[0])
                    items.append((raw, *normalized))
            except (ValueError, UnicodeError) as exc:
                invalid.append((n, raw, str(exc)))
    networks = None
    ip_lookup_status = 'disabled'
    if args.ip_check or args.focus_unprotected:
        networks, warnings = load_ip_ranges(args.timeout)
        for warning in warnings:
            print('WARNING:', warning, file=sys.stderr)
        ip_lookup_status = 'ok' if not warnings else 'partial'
        if not networks:
            ip_lookup_status = 'failed'
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, args.timeout, not args.insecure, args.active, networks, ip_lookup_status): item for item in items}
        for fut in concurrent.futures.as_completed(futures):
            item = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:
                row = {'input': item[0], 'url': item[1], 'hostname': item[2],
                       'classification': 'ERROR', 'error': str(exc)}
            rows.append(row)
            print(f'[{len(rows)}/{len(items)}] {row["hostname"]}: {row["classification"]} {row.get("provider", "")}', flush=True)
    columns = ['input', 'url', 'hostname', 'ipv4', 'ipv6', 'cname', 'http_status',
               'final_url', 'classification', 'provider', 'ip_provider', 'ip_lookup_status', 'focus_status', 'evidence', 'error']
    with open(args.output, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda x: x['hostname']))
    print(f'\nSaved {len(rows)} results to {args.output}; skipped {len(invalid)} invalid lines.')
    if args.focus_unprotected:
        from pathlib import Path
        output = Path(args.output)
        candidates = sorted((r for r in rows if r.get('focus_status') == 'CANDIDATE_NO_WAF_CDN'), key=lambda r: r['hostname'])
        uncertain = sorted((r for r in rows if r.get('focus_status') == 'INCONCLUSIVE'), key=lambda r: r['hostname'])
        for path, selected in ((output.with_name(output.stem + '_candidates.csv'), candidates),
                               (output.with_name(output.stem + '_inconclusive.csv'), uncertain)):
            with path.open('w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(selected)
            print(f'Saved {len(selected)} entries to {path}')
        # Ready-to-reuse URLs for further review, preserving original target scheme.
        path = output.with_name(output.stem + '_candidates.txt')
        path.write_text(''.join(r['url'] + '\n' for r in candidates), encoding='utf-8')
        print(f'Saved candidate URL list to {path}')
    for line, raw, reason in invalid:
        print(f'Invalid line {line}: {raw!r} ({reason})', file=sys.stderr)


if __name__ == '__main__':
    main()
