import os
import json
import zipfile
import tempfile
import shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB


def parse_scan_zip(zip_path):
    """Parse a scanner zip file and return structured data."""
    result = {}
    extract_dir = tempfile.mkdtemp()

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)

        # Walk to find scan directories (latest/ or history/timestamp/)
        scans = {}
        for root, dirs, files in os.walk(extract_dir):
            if set(['metadata.json']).issubset(set(files)):
                scan_name = os.path.basename(root)
                scan_data = load_scan_dir(root)
                if scan_data:
                    scans[scan_name] = scan_data

        # Determine domain from folder structure
        domain = None
        for item in os.listdir(extract_dir):
            if os.path.isdir(os.path.join(extract_dir, item)):
                domain = item
                break

        result['domain'] = domain
        result['scans'] = scans

        # Get latest scan
        if 'latest' in scans:
            result['latest'] = scans['latest']
        elif scans:
            # Pick the most recent by timestamp name
            sorted_keys = sorted([k for k in scans if k != 'latest'], reverse=True)
            result['latest'] = scans[sorted_keys[0]] if sorted_keys else list(scans.values())[0]

        # Collect history scans
        history_scans = {k: v for k, v in scans.items() if k != 'latest'}
        result['history'] = history_scans

    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    return result


def load_scan_dir(scan_dir):
    """Load all data files from a scan directory."""
    data = {}

    def read_json(filename):
        path = os.path.join(scan_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', errors='replace') as f:
                try:
                    return json.load(f)
                except:
                    return None
        return None

    def read_jsonl(filename):
        path = os.path.join(scan_dir, filename)
        results = []
        if os.path.exists(path):
            with open(path, 'r', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            results.append(json.loads(line))
                        except:
                            pass
        return results

    def read_txt(filename):
        path = os.path.join(scan_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', errors='replace') as f:
                return [l.strip() for l in f if l.strip()]
        return []

    data['metadata'] = read_json('metadata.json')
    data['dns_records'] = read_json('dns_records.json') or {}
    data['asn_records'] = read_json('asn_records.json') or {}
    data['shodan'] = read_json('shodan_internetdb.json') or {}
    data['host_to_ips'] = read_json('host_to_ips.json') or {}
    data['ptr_records'] = read_json('ptr_records.json') or {}
    data['diff'] = read_json('diff.json') or {}
    data['nuclei'] = read_jsonl('nuclei_results.jsonl')
    data['subdomains'] = read_txt('subdomains.txt')
    data['ipv4'] = read_txt('ipv4_addresses.txt')
    data['ipv6'] = read_txt('ipv6_addresses.txt')

    # Enrich: build IP detail map merging shodan + asn
    ip_details = {}
    for ip, shodan_info in data['shodan'].items():
        ip_details[ip] = {
            'ip': ip,
            'ports': shodan_info.get('ports', []),
            'vulns': shodan_info.get('vulns', []),
            'cpes': shodan_info.get('cpes', []),
            'tags': shodan_info.get('tags', []),
            'hostnames': shodan_info.get('hostnames', []),
            'subdomains': shodan_info.get('subdomains', []),
            'asn': data['asn_records'].get(ip, {}),
        }

    # Add IPs that have ASN but not shodan
    for ip, asn_info in data['asn_records'].items():
        if ip not in ip_details and asn_info:
            ip_details[ip] = {
                'ip': ip, 'ports': [], 'vulns': [], 'cpes': [],
                'tags': [], 'hostnames': [], 'subdomains': [], 'asn': asn_info
            }

    data['ip_details'] = ip_details

    # Enrich: map subdomains to IPs and vulnerabilities
    subdomain_details = {}
    for host, ips in data['host_to_ips'].items():
        entry = {
            'host': host,
            'ips': ips,
            'dns': data['dns_records'].get(host, {}),
            'ip_data': [],
            'all_vulns': [],
            'all_ports': [],
            'all_tags': [],
            'all_cpes': [],
        }
        for ip in ips:
            if ip in ip_details:
                entry['ip_data'].append(ip_details[ip])
                entry['all_vulns'].extend(ip_details[ip]['vulns'])
                entry['all_ports'].extend(ip_details[ip]['ports'])
                entry['all_tags'].extend(ip_details[ip]['tags'])
                entry['all_cpes'].extend(ip_details[ip]['cpes'])
        entry['all_vulns'] = list(set(entry['all_vulns']))
        entry['all_ports'] = sorted(set(entry['all_ports']))
        entry['all_tags'] = list(set(entry['all_tags']))
        subdomain_details[host] = entry

    data['subdomain_details'] = subdomain_details

    # Nuclei findings grouped by severity and template
    nuclei_by_severity = {}
    for finding in data['nuclei']:
        sev = finding.get('info', {}).get('severity', 'unknown')
        nuclei_by_severity.setdefault(sev, []).append(finding)
    data['nuclei_by_severity'] = nuclei_by_severity

    return data


# In-memory store for loaded scan data
_scan_store = {}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_zip():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename.endswith('.zip'):
        return jsonify({'error': 'File must be a .zip'}), 400

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    f.save(tmp.name)
    tmp.close()

    try:
        scan_data = parse_scan_zip(tmp.name)
        scan_id = scan_data.get('domain', 'scan')
        _scan_store[scan_id] = scan_data

        # Build summary for response
        latest = scan_data.get('latest', {})
        meta = latest.get('metadata', {})
        stats = meta.get('stats', {}) if meta else {}

        return jsonify({
            'scan_id': scan_id,
            'domain': scan_data.get('domain'),
            'stats': stats,
            'history_count': len(scan_data.get('history', {})),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        os.unlink(tmp.name)


@app.route('/api/scan/<scan_id>/overview')
def overview(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    meta = latest.get('metadata', {}) or {}
    stats = meta.get('stats', {})
    config = meta.get('config', {})
    errors = stats.get('errors', [])

    return jsonify({
        'domain': scan.get('domain'),
        'stats': stats,
        'config': config,
        'errors': errors,
        'diff': latest.get('diff', {}),
        'tools': meta.get('tools', {}),
    })


@app.route('/api/scan/<scan_id>/nuclei')
def nuclei(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    findings = latest.get('nuclei', [])

    # Enrich with classification labels
    severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'info': 4, 'unknown': 5}
    findings_sorted = sorted(findings, key=lambda x: severity_order.get(
        x.get('info', {}).get('severity', 'unknown'), 5))

    return jsonify({'findings': findings_sorted, 'by_severity': latest.get('nuclei_by_severity', {})})


@app.route('/api/scan/<scan_id>/subdomains')
def subdomains(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    return jsonify({
        'subdomains': latest.get('subdomains', []),
        'subdomain_details': latest.get('subdomain_details', {}),
        'host_to_ips': latest.get('host_to_ips', {}),
    })


@app.route('/api/scan/<scan_id>/ips')
def ips(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    return jsonify({
        'ip_details': latest.get('ip_details', {}),
        'ipv4': latest.get('ipv4', []),
        'ipv6': latest.get('ipv6', []),
    })


@app.route('/api/scan/<scan_id>/dns')
def dns(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    return jsonify({'dns_records': latest.get('dns_records', {})})


@app.route('/api/scan/<scan_id>/vulns')
def vulns(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    latest = scan.get('latest', {})
    ip_details = latest.get('ip_details', {})

    vuln_map = {}
    for ip, d in ip_details.items():
        for cve in d.get('vulns', []):
            vuln_map.setdefault(cve, {'cve': cve, 'ips': [], 'subdomains': [], 'cpes': []})
            vuln_map[cve]['ips'].append(ip)
            vuln_map[cve]['subdomains'].extend(d.get('subdomains', []))
            vuln_map[cve]['cpes'].extend(d.get('cpes', []))

    for v in vuln_map.values():
        v['subdomains'] = list(set(v['subdomains']))
        v['cpes'] = list(set(v['cpes']))

    return jsonify({'vulns': list(vuln_map.values()), 'total': len(vuln_map)})


@app.route('/api/scan/<scan_id>/history')
def history(scan_id):
    scan = _scan_store.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found'}), 404
    hist = scan.get('history', {})
    summaries = {}
    for ts, s in hist.items():
        meta = s.get('metadata', {}) or {}
        summaries[ts] = meta.get('stats', {})
    return jsonify({'history': summaries})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
