#!/usr/bin/env python3
"""
infra_fingerprint.py — Infrastructure fingerprinting for threat-actor clustering.

Given one or more HTTP(S) targets, this collects every stable, comparable
signal we can pull from the network, TLS, certificate, and HTTP layers, then
emits a single structured JSON record per target. The point is *clustering*:
run it across a set of suspected actor hosts and diff/group the records to
surface shared infrastructure that isn't obvious from IP or domain alone.

Signals collected
------------------
Network : resolved IPs, reverse DNS (PTR)
TLS     : negotiated version/cipher/ALPN, JARM (active), JA4S (ServerHello)
Cert    : full chain — SHA256/SHA1 fingerprints, subject, issuer, SANs,
          serial, validity, public-key SHA256 (SPKI), signature algorithm,
          a JA4X-style issuer/subject RDN hash
HTTP    : status, header *set* hash, header *order* hash, Server/powered-by,
          cookie names, redirect chain, title, meta-generator, favicon mmh3
          hash (Shodan-style), body sha256, normalized-body sha256, HTML
          structural-skeleton hash, a body SimHash for fuzzy near-dup matching,
          and extracted "repeating" signature strings (copyright lines, JS/CSS
          src hosts, tracking IDs, HTML comments, unique server error strings)
Probes  : hash of a random-path 404/default page, and of the root over HTTP

Every collector is defensive: a failure in one layer degrades to null in that
field rather than killing the run. Output is JSON Lines (one object per target).

Usage
-----
    python3 infra_fingerprint.py https://example.com
    python3 infra_fingerprint.py -i targets.txt -o out.jsonl --insecure
    python3 infra_fingerprint.py 1.2.3.4 --port 8443 --json-pretty

This tool only performs standard client-side connections (equivalent to a
browser plus an active TLS probe). It is intended for defensive threat
intelligence on infrastructure you are authorized to investigate.
"""

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

# ---- Optional dependencies (degrade gracefully if missing) ------------------
try:
    import requests
    from requests.adapters import HTTPAdapter
except Exception:
    requests = None

try:
    import mmh3
except Exception:
    mmh3 = None

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except Exception:
    x509 = None

try:
    from OpenSSL import SSL as OSSL
except Exception:
    OSSL = None

try:
    from jarm.scanner.scanner import Scanner as JarmScanner
except Exception:
    JarmScanner = None


USER_AGENT = "Mozilla/5.0 (compatible; InfraFP/1.0; +cti-research)"
GREASE = {0x0a0a, 0x1a1a, 0x2a2a, 0x3a3a, 0x4a4a, 0x5a5a, 0x6a6a, 0x7a7a,
          0x8a8a, 0x9a9a, 0xaaaa, 0xbaba, 0xcaca, 0xdada, 0xeaea, 0xfafa}


# ============================================================================
# Small helpers
# ============================================================================
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Ports we treat as TLS by default when no scheme is given.
HTTPS_PORTS = {443, 4443, 8443, 9443, 10443, 6443}


def is_ipv6(s: str) -> bool:
    try:
        import ipaddress
        return isinstance(ipaddress.ip_address(s), ipaddress.IPv6Address)
    except (ValueError, ImportError):
        return False


def is_ip(s: str) -> bool:
    try:
        import ipaddress
        ipaddress.ip_address(s)
        return True
    except (ValueError, ImportError):
        return False


def _parse_authority(authority: str):
    """Split an authority into (host, port|None). Handles userinfo, bracketed
    IPv6 (`[::1]:8443`), bare IPv6 (`2606:4700::1111`), IPv4, and hostnames."""
    if "@" in authority:                       # drop any user:pass@
        authority = authority.rsplit("@", 1)[1]
    if authority.startswith("["):              # [IPv6](:port)?
        host, _, tail = authority[1:].partition("]")
        port = int(tail[1:]) if tail.startswith(":") and tail[1:] else None
        return host, port
    if is_ipv6(authority):                      # bare IPv6, no port
        return authority, None
    if authority.count(":") == 1:               # host:port (v4/hostname)
        host, p = authority.split(":")
        return host, (int(p) if p else None)
    return authority, None                      # host only


def normalize_target(target: str, default_port: int = None):
    """Return (scheme, host, port, url) for any of:

        163.245.205.62                      bare IPv4
        2606:4700:4700::1111                bare IPv6
        [2606:4700::1111]:8443              bracketed IPv6 + port
        example.com  /  example.com:8443    hostname (+ port)
        163.245.205.62:5000                 IPv4:port
        http://163.245.205.62:5000/sessions URL with IP, port and path
        https://example.com/panel?a=1       URL with path + query

    `host` is returned bare (no brackets) for socket/TLS use; `url` is rebuilt
    correctly (IPv6 bracketed, path/query preserved, default port omitted).
    `default_port` fills in only when the target itself specifies no port.
    """
    target = target.strip()

    scheme = None
    rest = target
    if "://" in target:
        scheme, rest = target.split("://", 1)
        scheme = scheme.lower()

    # Separate authority from path/query/fragment.
    if "/" in rest:
        authority, tail = rest.split("/", 1)
        path = "/" + tail
    else:
        authority, path = rest, ""

    host, port = _parse_authority(authority)
    if port is None and default_port:
        port = default_port

    # Infer scheme from port when it wasn't stated explicitly.
    if scheme is None:
        scheme = "https" if (port in HTTPS_PORTS or port is None) else "http"
    if port is None:
        port = 443 if scheme == "https" else 80

    hostpart = f"[{host}]" if is_ipv6(host) else host
    default = 443 if scheme == "https" else 80
    if port == default:
        url = f"{scheme}://{hostpart}{path}"
    else:
        url = f"{scheme}://{hostpart}:{port}{path}"

    return scheme, host, port, url


# ============================================================================
# Network layer
# ============================================================================
def collect_network(host: str) -> dict:
    out = {"host": host, "ips": [], "ptr": {}}
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({i[4][0] for i in infos})
        out["ips"] = ips
        for ip in ips:
            try:
                out["ptr"][ip] = socket.gethostbyaddr(ip)[0]
            except Exception:
                out["ptr"][ip] = None
    except Exception as e:
        out["error"] = str(e)
    return out


# ============================================================================
# TLS / certificate layer
# ============================================================================
def collect_tls_and_certs(host: str, port: int, timeout: int = 10) -> dict:
    """Grab negotiated params and the FULL certificate chain via pyOpenSSL."""
    out = {"negotiated": {}, "chain": [], "error": None}
    if OSSL is None or x509 is None:
        out["error"] = "pyOpenSSL/cryptography not installed"
        return out
    try:
        ctx = OSSL.Context(OSSL.TLS_CLIENT_METHOD)
        ctx.set_verify(OSSL.VERIFY_NONE, lambda *a: True)
        try:
            ctx.set_alpn_protos([b"h2", b"http/1.1"])
        except Exception:
            pass
        raw = socket.create_connection((host, port), timeout=timeout)
        conn = OSSL.Connection(ctx, raw)
        if not is_ip(host):
            conn.set_tlsext_host_name(host.encode())
        conn.set_connect_state()
        conn.setblocking(True)
        conn.do_handshake()

        out["negotiated"] = {
            "version": conn.get_protocol_version_name(),
            "cipher": conn.get_cipher_name(),
            "cipher_bits": conn.get_cipher_bits(),
        }
        try:
            alpn = conn.get_alpn_proto_negotiated()
            out["negotiated"]["alpn"] = alpn.decode() if alpn else None
        except Exception:
            out["negotiated"]["alpn"] = None

        chain = conn.get_peer_cert_chain() or []
        for oc in chain:
            try:
                der = oc.to_cryptography().public_bytes(Encoding.DER)
            except Exception:
                from OpenSSL import crypto as _c
                der = _c.dump_certificate(_c.FILETYPE_ASN1, oc)
            out["chain"].append(parse_certificate(der))

        try:
            conn.shutdown()
        except Exception:
            pass
        raw.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def _name_str(name) -> str:
    try:
        return name.rfc4514_string()
    except Exception:
        return str(name)


def parse_certificate(der: bytes) -> dict:
    """Parse one DER cert into a rich, comparable dict of fingerprints."""
    info = {
        "sha256": sha256_hex(der),
        "sha1": sha1_hex(der),
    }
    try:
        cert = x509.load_der_x509_certificate(der)
        info["subject"] = _name_str(cert.subject)
        info["issuer"] = _name_str(cert.issuer)
        info["serial"] = format(cert.serial_number, "x")
        info["not_before"] = cert.not_valid_before_utc.isoformat()
        info["not_after"] = cert.not_valid_after_utc.isoformat()
        info["signature_algorithm"] = cert.signature_algorithm_oid._name
        # SPKI (public key) fingerprint — very stable across cert reissues
        try:
            spki = cert.public_key().public_bytes(
                Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
            info["spki_sha256"] = sha256_hex(spki)
        except Exception:
            info["spki_sha256"] = None
        # SANs
        try:
            ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName)
            info["san"] = sorted(ext.value.get_values_for_type(x509.DNSName))
        except Exception:
            info["san"] = []
        # JA4X-style RDN hashes (issuer / subject attribute-OID sequences)
        info["issuer_hash"] = _rdn_hash(cert.issuer)
        info["subject_hash"] = _rdn_hash(cert.subject)
    except Exception as e:
        info["parse_error"] = str(e)
    return info


def _rdn_hash(name) -> str:
    try:
        oids = ",".join(attr.oid.dotted_string for attr in name)
        return sha256_hex(oids.encode())[:12]
    except Exception:
        return None


# ============================================================================
# JARM (active TLS fingerprint)
# ============================================================================
def collect_jarm(host: str, port: int, timeout: int = 15) -> str:
    if JarmScanner is None:
        return None
    try:
        result = JarmScanner.scan(host, port, timeout=timeout)
        jarm_hash = result[0] if isinstance(result, (list, tuple)) else result
        if jarm_hash and set(jarm_hash) != {"0"}:
            return jarm_hash
    except Exception:
        pass
    return None


# ============================================================================
# JA4S (ServerHello fingerprint) — raw TLS
# ============================================================================
def _build_client_hello(server_name: str) -> bytes:
    rand = os.urandom(32)
    sid = os.urandom(32)
    ciphers = bytes.fromhex(
        "130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035")
    body = b"\x03\x03" + rand + bytes([len(sid)]) + sid
    body += struct.pack(">H", len(ciphers)) + ciphers
    body += b"\x01\x00"  # null compression
    ext = b""
    if server_name and not is_ip(server_name):   # SNI is invalid for IP literals
        sni = server_name.encode()
        sni_list = b"\x00" + struct.pack(">H", len(sni)) + sni
        sni_block = struct.pack(">H", len(sni_list)) + sni_list
        ext += b"\x00\x00" + struct.pack(">H", len(sni_block)) + sni_block
    alpn_protos = b"\x02h2\x08http/1.1"
    alpn_block = struct.pack(">H", len(alpn_protos)) + alpn_protos
    ext += b"\x00\x10" + struct.pack(">H", len(alpn_block)) + alpn_block
    groups = b"\x00\x1d\x00\x17\x00\x18"
    ext += b"\x00\x0a" + struct.pack(">H", len(groups) + 2) + \
        struct.pack(">H", len(groups)) + groups
    ext += b"\x00\x0b\x00\x02\x01\x00"  # ec_point_formats
    sigalgs = bytes.fromhex("0403080407080805080604010503060102010202")
    ext += b"\x00\x0d" + struct.pack(">H", len(sigalgs) + 2) + \
        struct.pack(">H", len(sigalgs)) + sigalgs
    sv = b"\x03\x04\x03\x03"  # supported_versions TLS1.3,1.2
    ext += b"\x00\x2b" + struct.pack(">H", len(sv) + 1) + bytes([len(sv)]) + sv
    kx = os.urandom(32)
    ks_entry = b"\x00\x1d" + struct.pack(">H", 32) + kx  # x25519 key_share
    ks_list = struct.pack(">H", len(ks_entry)) + ks_entry
    ext += b"\x00\x33" + struct.pack(">H", len(ks_list)) + ks_list
    ext += b"\x00\x2d\x00\x02\x01\x01"  # psk_key_exchange_modes
    body += struct.pack(">H", len(ext)) + ext
    hs = b"\x01" + struct.pack(">I", len(body))[1:] + body
    return b"\x16\x03\x01" + struct.pack(">H", len(hs)) + hs


def _parse_server_hello(data: bytes):
    if not data or data[0] != 0x16 or len(data) < 5:
        return None
    rec_len = struct.unpack(">H", data[3:5])[0]
    hs = data[5:5 + rec_len]
    if not hs or hs[0] != 0x02:
        return None
    sh_len = struct.unpack(">I", b"\x00" + hs[1:4])[0]
    p = hs[4:4 + sh_len]
    off = 0
    legacy = struct.unpack(">H", p[off:off + 2])[0]; off += 2
    off += 32
    sid_len = p[off]; off += 1; off += sid_len
    cipher = struct.unpack(">H", p[off:off + 2])[0]; off += 2
    off += 1
    if off + 2 > len(p):
        return {"tls_version": legacy, "cipher": cipher, "extensions": [], "alpn": ""}
    ext_total = struct.unpack(">H", p[off:off + 2])[0]; off += 2
    exts, alpn, tls_ver = [], "", legacy
    end = off + ext_total
    while off + 4 <= end:
        et = struct.unpack(">H", p[off:off + 2])[0]; off += 2
        el = struct.unpack(">H", p[off:off + 2])[0]; off += 2
        ev = p[off:off + el]; off += el
        exts.append(et)
        if et == 0x2b and len(ev) >= 2:
            tls_ver = struct.unpack(">H", ev[0:2])[0]
        if et == 0x10 and len(ev) >= 3:
            alpn = ev[3:].decode(errors="ignore")
    return {"tls_version": tls_ver, "cipher": cipher, "extensions": exts, "alpn": alpn}


def collect_ja4s(host: str, port: int, timeout: int = 8) -> dict:
    out = {"ja4s": None, "server_hello": None}
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(_build_client_hello(host))
        data = b""
        while len(data) < 5:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        # read a bit more to be sure we have the whole record
        try:
            data += s.recv(8192)
        except Exception:
            pass
        s.close()
        sh = _parse_server_hello(data)
        if not sh:
            return out
        out["server_hello"] = {
            "cipher": f"0x{sh['cipher']:04x}",
            "tls_version": f"0x{sh['tls_version']:04x}",
            "alpn": sh["alpn"] or None,
        }
        ver_map = {0x0304: "13", 0x0303: "12", 0x0302: "11", 0x0301: "10"}
        v = ver_map.get(sh["tls_version"], "00")
        exts = [e for e in sh["extensions"] if e not in GREASE]
        a = sh["alpn"]
        alpn2 = (a[0] + a[-1]) if a else "00"
        ja4s_a = f"t{v}{len(exts):02d}{alpn2}"
        ja4s_b = f"{sh['cipher']:04x}"
        ext_hex = ",".join(f"{e:04x}" for e in exts)
        ja4s_c = sha256_hex(ext_hex.encode())[:12] if exts else "000000000000"
        out["ja4s"] = f"{ja4s_a}_{ja4s_b}_{ja4s_c}"
    except Exception:
        pass
    return out


# ============================================================================
# HTTP layer
# ============================================================================
def _session(insecure: bool, timeout: int):
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    s.verify = not insecure
    s.max_redirects = 10
    return s


def favicon_hash(session, base_url: str, timeout: int):
    """Shodan-style favicon hash: mmh3 of base64(favicon) with newlines."""
    if mmh3 is None:
        return None
    try:
        fav = urljoin(base_url, "/favicon.ico")
        r = session.get(fav, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and r.content:
            b64 = base64.encodebytes(r.content)
            return mmh3.hash(b64)
    except Exception:
        pass
    return None


def _extract_signatures(body_text: str) -> dict:
    """Pull out strings that tend to repeat across an actor's servers."""
    sig = {}
    t = body_text

    m = re.search(r"<title[^>]*>(.*?)</title>", t, re.I | re.S)
    sig["title"] = m.group(1).strip()[:200] if m else None

    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)',
                  t, re.I)
    sig["generator"] = m.group(1).strip() if m else None

    # copyright / footer strings
    cps = re.findall(r"(?:©|&copy;|Copyright)\s*[^<\n\r]{0,80}", t, re.I)
    sig["copyright"] = sorted({c.strip()[:100] for c in cps})[:5]

    # script/link src hosts (external infra reuse is a strong clustering signal)
    srcs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', t, re.I)
    hosts = set()
    for s in srcs:
        m = re.match(r"https?://([^/]+)/?", s)
        if m:
            hosts.add(m.group(1).lower())
    sig["external_hosts"] = sorted(hosts)[:25]

    # tracking / analytics IDs
    ids = set()
    for pat in (r"UA-\d{4,}-\d+", r"G-[A-Z0-9]{6,}", r"GTM-[A-Z0-9]{4,}",
                r"AW-\d{6,}", r"fbq\(['\"]init['\"],\s*['\"](\d{5,})"):
        ids.update(re.findall(pat, t))
    sig["tracking_ids"] = sorted(ids)[:10]

    # HTML comments (devs leave the same ones on staging/prod/actor clones)
    comments = re.findall(r"<!--(.*?)-->", t, re.S)
    sig["comments"] = sorted({c.strip()[:120] for c in comments if c.strip()})[:8]

    return sig


def _structural_skeleton(body_text: str) -> str:
    """Hash of the ordered tag skeleton — resists text/content changes."""
    tags = re.findall(r"<\s*(/?[a-zA-Z][a-zA-Z0-9]*)", body_text)
    skel = ">".join(t.lower() for t in tags)
    return sha256_hex(skel.encode())


def _normalize_body(body_text: str) -> str:
    """Strip volatile tokens so near-identical pages hash the same."""
    t = body_text
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[0-9a-f]{32,64}", "", t, flags=re.I)   # nonces / hashes
    t = re.sub(r"csrf[-_]?token[^\"'>]{0,80}", "", t, flags=re.I)
    t = re.sub(r"nonce=[\"'][^\"']+[\"']", "", t, flags=re.I)
    t = re.sub(r"\d{10,}", "", t)                        # timestamps / ids
    return t.strip()


def simhash64(text: str) -> str:
    """64-bit SimHash over token shingles for fuzzy near-dup body matching.

    Hamming distance between two SimHashes ~ how similar two pages are, even
    when content differs slightly. Great for clustering templated actor pages.
    """
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    if not tokens:
        return "0" * 16
    shingles = [" ".join(tokens[i:i + 3]) for i in range(len(tokens))] or tokens
    v = [0] * 64
    for sh in shingles:
        h = int(hashlib.md5(sh.encode()).hexdigest(), 16) & ((1 << 64) - 1)
        for b in range(64):
            v[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(64):
        if v[b] > 0:
            out |= (1 << b)
    return f"{out:016x}"


def collect_http(session, url: str, timeout: int) -> dict:
    out = {"error": None}
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
    except Exception as e:
        out["error"] = str(e)
        return out

    out["final_url"] = r.url
    out["status"] = r.status_code
    out["redirect_chain"] = [{"url": h.url, "status": h.status_code}
                             for h in r.history]

    # Header fingerprints
    header_items = list(r.raw.headers.items()) if getattr(r, "raw", None) \
        and getattr(r.raw, "headers", None) else list(r.headers.items())
    names_in_order = [k for k, _ in header_items]
    out["header_order"] = names_in_order
    out["header_order_hash"] = sha256_hex(",".join(
        n.lower() for n in names_in_order).encode())[:16]
    out["header_set_hash"] = sha256_hex(",".join(
        sorted({n.lower() for n in names_in_order})).encode())[:16]
    out["server"] = r.headers.get("Server")
    out["powered_by"] = r.headers.get("X-Powered-By")
    out["via"] = r.headers.get("Via")
    try:
        out["set_cookie_names"] = sorted({c.name for c in r.cookies})
    except Exception:
        out["set_cookie_names"] = []
    out["content_type"] = r.headers.get("Content-Type")
    out["content_length"] = r.headers.get("Content-Length")

    # Body fingerprints
    raw_body = r.content or b""
    out["body_sha256"] = sha256_hex(raw_body)
    out["body_length"] = len(raw_body)
    text = r.text or ""
    out["body_normalized_sha256"] = sha256_hex(_normalize_body(text).encode())
    out["body_simhash"] = simhash64(_normalize_body(text))
    out["structural_hash"] = _structural_skeleton(text)
    out["signatures"] = _extract_signatures(text)

    # Favicon
    out["favicon_mmh3"] = favicon_hash(session, r.url, timeout)
    return out


def collect_probes(session, base_url: str, timeout: int) -> dict:
    """Default/404 page fingerprint + plaintext HTTP root fingerprint."""
    out = {}
    try:
        rp = "/" + hashlib.md5(os.urandom(8)).hexdigest()[:12] + "-fp-probe"
        r = session.get(urljoin(base_url, rp), timeout=timeout,
                        allow_redirects=False)
        out["notfound_status"] = r.status_code
        out["notfound_body_sha256"] = sha256_hex(r.content or b"")
        out["notfound_server"] = r.headers.get("Server")
    except Exception as e:
        out["notfound_error"] = str(e)

    try:
        u = urlparse(base_url)
        http_url = f"http://{u.hostname}:80/"
        r = session.get(http_url, timeout=timeout, allow_redirects=False)
        out["http_status"] = r.status_code
        out["http_location"] = r.headers.get("Location")
        out["http_server"] = r.headers.get("Server")
        out["http_body_sha256"] = sha256_hex(r.content or b"")
    except Exception as e:
        out["http_error"] = str(e)
    return out


# ============================================================================
# Orchestration
# ============================================================================
def fingerprint_target(target: str, timeout: int = 10, insecure: bool = False,
                       do_probes: bool = True, default_port: int = None) -> dict:
    scheme, host, port, url = normalize_target(target, default_port=default_port)
    rec = {
        "target": target,
        "scheme": scheme,
        "host": host,
        "port": port,
        "collected_at": now_iso(),
    }

    rec["network"] = collect_network(host)

    if scheme == "https":
        rec["tls"] = collect_tls_and_certs(host, port, timeout)
        rec["jarm"] = collect_jarm(host, port, timeout + 5)
        rec["ja4s"] = collect_ja4s(host, port, timeout)
    else:
        rec["tls"] = None
        rec["jarm"] = None
        rec["ja4s"] = None

    if requests is not None:
        sess = _session(insecure, timeout)
        rec["http"] = collect_http(sess, url, timeout)
        if do_probes:
            rec["probes"] = collect_probes(sess, url, timeout)
    else:
        rec["http"] = {"error": "requests not installed"}

    rec["cluster_key"] = build_cluster_key(rec)
    return rec


def build_cluster_key(rec: dict) -> dict:
    """A compact bundle of the most stable cross-host signals. Two hosts that
    share several of these are very likely the same actor/tooling/build."""
    tls = rec.get("tls") or {}
    chain = tls.get("chain") or []
    leaf = chain[0] if chain else {}
    http = rec.get("http") or {}
    ja4s = (rec.get("ja4s") or {}).get("ja4s") if isinstance(rec.get("ja4s"), dict) else rec.get("ja4s")
    return {
        "jarm": rec.get("jarm"),
        "ja4s": ja4s,
        "cert_spki_sha256": leaf.get("spki_sha256"),
        "cert_issuer_hash": leaf.get("issuer_hash"),
        "favicon_mmh3": http.get("favicon_mmh3"),
        "header_order_hash": http.get("header_order_hash"),
        "structural_hash": http.get("structural_hash"),
        "body_simhash": http.get("body_simhash"),
        "server": http.get("server"),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Infrastructure fingerprinting for threat-actor clustering.")
    ap.add_argument("targets", nargs="*", help="URLs or host[:port] values")
    ap.add_argument("-i", "--input", help="File with one target per line")
    ap.add_argument("-o", "--output", help="Write JSONL here (default: stdout)")
    ap.add_argument("-t", "--timeout", type=int, default=10)
    ap.add_argument("-w", "--workers", type=int, default=8,
                    help="Concurrent targets")
    ap.add_argument("--port", type=int, help="Override port for bare hosts")
    ap.add_argument("--insecure", action="store_true",
                    help="Skip TLS cert verification for HTTP fetches")
    ap.add_argument("--no-probes", action="store_true",
                    help="Skip 404/plaintext-HTTP probes")
    ap.add_argument("--json-pretty", action="store_true",
                    help="Pretty-print each record")
    args = ap.parse_args()

    targets = list(args.targets)
    if args.input:
        with open(args.input) as f:
            targets += [ln.strip() for ln in f if ln.strip()
                        and not ln.startswith("#")]
    if not targets:
        ap.error("no targets given (positional, or -i FILE)")

    out_fh = open(args.output, "w") if args.output else sys.stdout
    results = []

    def work(t):
        try:
            return fingerprint_target(t, args.timeout, args.insecure,
                                      not args.no_probes, default_port=args.port)
        except Exception as e:
            return {"target": t, "fatal_error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(work, targets):
            results.append(rec)
            line = json.dumps(rec, indent=2 if args.json_pretty else None,
                              default=str)
            out_fh.write(line + "\n")
            out_fh.flush()

    if args.output:
        out_fh.close()
        sys.stderr.write(f"[+] wrote {len(results)} record(s) to {args.output}\n")


if __name__ == "__main__":
    main()
