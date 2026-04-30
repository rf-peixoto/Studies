import platform
import subprocess
import socket
import ipaddress
import re
import json
import math
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, Response, stream_with_context

try:
    import requests as http
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

app = Flask(__name__)
PLATFORM = platform.system()   # 'Linux', 'Darwin', 'Windows'


# ─── IP UTILITIES ─────────────────────────────────────────────────────────────

def parse_addr(ip):
    """Return an ipaddress object or None."""
    try:
        return ipaddress.ip_address(ip)
    except ValueError:
        return None


def ip_version(ip):
    """Return 4, 6, or None."""
    a = parse_addr(ip)
    return a.version if a else None


def is_private(ip):
    a = parse_addr(ip)
    if a is None:
        return False
    return a.is_private or a.is_loopback or a.is_link_local or a.is_unspecified


def resolve_target(target):
    """
    Given a literal IP or domain name, return (resolved_ip, version).
    For literal IPs we just parse them. For domains we do a DNS lookup
    and prefer IPv6 if available (AAAA before A).
    """
    # Already a literal IP?
    a = parse_addr(target)
    if a:
        return str(a), a.version

    # Domain — try to resolve
    for family in (socket.AF_INET6, socket.AF_INET):
        try:
            results = socket.getaddrinfo(target, None, family)
            if results:
                ip = results[0][4][0]
                # strip zone id from link-local IPv6 (fe80::1%eth0)
                ip = ip.split("%")[0]
                a = parse_addr(ip)
                if a:
                    return str(a), a.version
        except Exception:
            pass

    return target, None   # couldn't resolve, pass as-is


def extract_ip_from_line(text):
    """
    Extract the first valid IP address (v4 or v6) from a traceroute hop line.
    Handles IPv6 addresses including :: abbreviations and zone IDs (%eth0).
    """
    # ── IPv4 ──────────────────────────────────────────────────────
    m4 = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", text)
    if m4 and parse_addr(m4.group(1)):
        return m4.group(1)

    # ── IPv6 ──────────────────────────────────────────────────────
    # Walk every whitespace-separated token; strip surrounding parens.
    for raw_token in text.split():
        token = raw_token.strip("()")
        # Strip zone identifier (fe80::1%eth0 → fe80::1)
        token = token.split("%")[0]
        if ":" in token:
            a = parse_addr(token)
            if a and a.version == 6:
                return str(a)   # return in canonical form

    return None


def reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def ip_info(ip):
    if not HAS_REQUESTS or is_private(ip):
        return {}
    try:
        r = http.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,org,isp,as,country,countryCode,city,regionName,proxy,hosting,mobile"},
            timeout=3,
        )
        d = r.json()
        return d if d.get("status") == "success" else {}
    except Exception:
        return {}


def ping_ttl(ip):
    """Single ping to capture TTL/hop-limit for OS fingerprinting."""
    try:
        v6 = (ip_version(ip) == 6)
        if PLATFORM == "Windows":
            cmd = ["ping", "-6" if v6 else "-4", "-n", "1", "-w", "1000", ip]
            out = subprocess.check_output(cmd, text=True, timeout=4, stderr=subprocess.DEVNULL)
            m = re.search(r"TTL=(\d+)", out, re.IGNORECASE)
        else:
            wait_flag = "-W" if PLATFORM == "Linux" else "-t"
            if v6:
                # try ping6 first; some distros use "ping -6"
                for ping_cmd in (["ping6", "-c", "1", wait_flag, "2", ip],
                                  ["ping", "-6", "-c", "1", wait_flag, "2", ip]):
                    try:
                        out = subprocess.check_output(
                            ping_cmd, text=True, timeout=4, stderr=subprocess.DEVNULL
                        )
                        break
                    except FileNotFoundError:
                        continue
                else:
                    return None
            else:
                out = subprocess.check_output(
                    ["ping", "-c", "1", wait_flag, "2", ip],
                    text=True, timeout=4, stderr=subprocess.DEVNULL
                )
            # ICMPv6 shows "hlim=" on macOS, "ttl=" on Linux ping6
            m = re.search(r"(?:ttl|hlim)=(\d+)", out, re.IGNORECASE)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def os_from_ttl(ttl):
    if ttl is None:
        return None, None
    if ttl <= 64:
        return "Linux / BSD / macOS", f"TTL={ttl} (≤64)"
    if ttl <= 128:
        return "Windows NT", f"TTL={ttl} (≤128)"
    return "Cisco IOS / JunOS", f"TTL={ttl} (≤255)"


def classify_hop_type(is_last, private, org, asn, is_hosting, is_proxy):
    """Classify the network role of a hop."""
    if is_last:
        return "TARGET"
    if private:
        return "GATEWAY"

    o = (org or "").lower()

    cdn_kw       = ["cloudflare", "akamai", "fastly", "incapsula", "imperva", "cdn", "edgecast", "limelight", "stackpath"]
    cloud_kw     = ["amazon", "aws", "microsoft azure", "google cloud", "digitalocean", "linode", "vultr", "hetzner", "ovh", "oracle cloud"]
    backbone_kw  = ["level 3", "lumen", "cogent", "ntt ", "telia", "hurricane electric", "zayo", "tata ", "gtts", "gtt ", "limecom", "centurylink", "colt ", "sparkle", "telecom italia", "seabone"]
    isp_kw       = ["telecom", "cable", "comcast", "at&t", "verizon", "charter", "spectrum", "bt ", "telefonica", "vodafone", "orange ", "isp", "broadband", "telstra", "rogers", "shaw", "tim ", "claro", "net ", "oi ", "vivo"]

    for kw in cdn_kw:
        if kw in o: return "CDN"
    for kw in cloud_kw:
        if kw in o: return "CLOUD"
    for kw in backbone_kw:
        if kw in o: return "BACKBONE"
    for kw in isp_kw:
        if kw in o: return "ISP"
    if is_hosting:
        return "HOSTING"
    if is_proxy:
        return "PROXY"
    return "TRANSIT"


def jitter(values):
    """Standard deviation of latency values = jitter."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return round(math.sqrt(variance), 2)


# ─── TRACEROUTE PARSING ───────────────────────────────────────────────────────

def parse_hop(line):
    line = line.strip()
    m = re.match(r"^\s*(\d+)\s+(.+)$", line)
    if not m:
        return None

    n, rest = int(m.group(1)), m.group(2).strip()

    # All-timeout line
    if re.match(r"^(\*\s*){1,3}$", rest) or "timed out" in rest.lower():
        return {"hop": n, "ip": None, "timeout": True, "latency_ms": [], "raw_probes": 3}

    ip = extract_ip_from_line(rest)
    if not ip:
        return None

    lats = [round(float(x), 2) for x in re.findall(r"(\d+\.?\d*)\s*ms", rest)]

    # Count asterisks for partial packet loss
    star_count   = len(re.findall(r"\*", rest))
    total_probes = len(lats) + star_count

    return {
        "hop":        n,
        "ip":         ip,
        "ip_version": ip_version(ip),
        "timeout":    False,
        "latency_ms": lats,
        "raw_probes": total_probes if total_probes > 0 else 3,
    }


def enrich(ip):
    """Parallel DNS + ip-api + ping-TTL."""
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_dns  = ex.submit(reverse_dns, ip)
        f_info = ex.submit(ip_info, ip)
        f_ttl  = ex.submit(ping_ttl, ip) if not is_private(ip) else None

        dns_val  = _safe(f_dns, 5)
        info_val = _safe(f_info, 5) or {}
        ttl_val  = _safe(f_ttl, 5) if f_ttl else None

    org = (
        info_val.get("org")
        or info_val.get("isp")
        or ("Private Network" if is_private(ip) else None)
    )
    os_name, os_basis = os_from_ttl(ttl_val)

    return {
        "rdns":       dns_val,
        "org":        org,
        "asn":        info_val.get("as"),
        "country":    info_val.get("country"),
        "country_code": info_val.get("countryCode"),
        "city":       info_val.get("city"),
        "region":     info_val.get("regionName"),
        "ttl":        ttl_val,
        "os":         os_name,
        "os_basis":   os_basis,
        "private":    is_private(ip),
        "is_hosting": bool(info_val.get("hosting")),
        "is_proxy":   bool(info_val.get("proxy")),
        "is_mobile":  bool(info_val.get("mobile")),
    }


def _safe(future, timeout):
    try:
        return future.result(timeout=timeout)
    except Exception:
        return None


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/trace")
def trace():
    target = request.args.get("t", "").strip()

    def err(msg):
        yield f"data: {json.dumps({'type': 'error', 'msg': msg})}\n\n"

    if not target:
        return Response(err("no target specified"), mimetype="text/event-stream")

    def generate():
        # ── Resolve target ─────────────────────────────────────────
        resolved_ip, ver = resolve_target(target)
        is_v6 = (ver == 6)

        yield f"data: {json.dumps({'type': 'start', 'target': target, 'resolved': resolved_ip, 'ip_version': ver})}\n\n"

        # ── Build traceroute command ────────────────────────────────
        if PLATFORM == "Windows":
            # tracert handles v4/v6 automatically
            cmd = ["tracert", "-d", "-h", "30", "-w", "2000", target]
        elif is_v6:
            # Prefer traceroute6; fall back to traceroute -6
            import shutil
            if shutil.which("traceroute6"):
                cmd = ["traceroute6", "-n", "-q", "3", "-w", "3", "-m", "30", target]
            else:
                cmd = ["traceroute", "-6", "-n", "-q", "3", "-w", "3", "-m", "30", target]
        else:
            cmd = ["traceroute", "-n", "-q", "3", "-w", "3", "-m", "30", target]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            hop_count = 0
            all_hops  = []

            for raw in proc.stdout:
                raw = raw.rstrip()
                if not raw or not re.match(r"^\s*\d", raw):
                    continue

                hop = parse_hop(raw)
                if hop is None:
                    continue

                hop_count += 1

                if hop["ip"]:
                    extra = enrich(hop["ip"])
                    hop.update(extra)

                    lats         = hop["latency_ms"]
                    total_probes = hop["raw_probes"]
                    lost         = total_probes - len(lats)

                    if lats:
                        avg = sum(lats) / len(lats)
                        hop["avg"]       = round(avg, 1)
                        hop["min_ms"]    = min(lats)
                        hop["max_ms"]    = max(lats)
                        hop["jitter"]    = jitter(lats)
                        hop["lat_class"] = "fast" if avg < 20 else ("med" if avg < 80 else "slow")
                    else:
                        hop["avg"] = hop["min_ms"] = hop["max_ms"] = hop["jitter"] = None
                        hop["lat_class"] = "none"

                    hop["packet_loss"] = round((lost / total_probes) * 100) if total_probes else 0
                    hop["hop_type"]    = classify_hop_type(
                        False,
                        hop["private"],
                        hop.get("org"),
                        hop.get("asn"),
                        hop.get("is_hosting", False),
                        hop.get("is_proxy", False),
                    )
                else:
                    hop.update({
                        "avg": None, "min_ms": None, "max_ms": None, "jitter": None,
                        "lat_class": "none", "packet_loss": 100,
                        "hop_type": "TIMEOUT", "private": False,
                        "rdns": None, "org": None, "asn": None,
                        "country": None, "country_code": None, "city": None, "region": None,
                        "ttl": None, "os": None, "os_basis": None,
                        "is_hosting": False, "is_proxy": False, "is_mobile": False,
                        "ip_version": None,
                    })

                all_hops.append(hop)
                yield f"data: {json.dumps({'type': 'hop', 'data': hop})}\n\n"

            proc.wait()

            # Retroactively tag last responding hop as TARGET
            for h in reversed(all_hops):
                if not h["timeout"] and h["ip"]:
                    h["hop_type"] = "TARGET"
                    yield f"data: {json.dumps({'type': 'retag', 'hop': h['hop'], 'hop_type': 'TARGET'})}\n\n"
                    break

            yield f"data: {json.dumps({'type': 'done', 'hops': hop_count})}\n\n"

        except FileNotFoundError:
            tool = "tracert" if PLATFORM == "Windows" else ("traceroute6" if is_v6 else "traceroute")
            yield f"data: {json.dumps({'type': 'error', 'msg': f'{tool} not found — sudo apt install traceroute'})}\n\n"
        except PermissionError:
            yield f"data: {json.dumps({'type': 'error', 'msg': 'permission denied — try: sudo python app.py'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'msg': str(exc)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
