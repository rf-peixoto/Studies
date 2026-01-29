#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Website certificate auditor (overhauled)

Capabilities
- Fetches leaf + presented chain using: openssl s_client -showcerts (SNI enabled)
- Saves artifacts: leaf.pem, chain.pem, fullchain.pem, openssl_s_client.txt, openssl_verify*.txt, report.json
- Verifies:
  - Hostname binding (SAN-first, conservative wildcards; CN fallback only if SAN absent)
  - Trust/path validation (openssl verify against CA bundle, with -purpose sslserver)
  - Optional OpenSSL hostname verification (openssl verify -verify_hostname) and divergence detection
  - Key strength policy (RSA: <2048 FAIL; <4096 WARN; >=4096 INFO)
  - Signature hash policy (MD5/SHA1 FAIL)
  - Leaf semantics (BasicConstraints CA must be false; EKU serverAuth must exist)
  - Intermediate semantics (BasicConstraints CA must be true)

Exit codes:
  0 OK
  1 WARN
  2 FAIL

Dependencies:
  pip install cryptography certifi colorama (optional)
System:
  openssl in PATH
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID, NameOID

# Optional colors
try:
    from colorama import Fore, Style, init as colorama_init  # type: ignore
    colorama_init()
    HAS_COLOR = True
except Exception:
    HAS_COLOR = False


# More tolerant than \s+ (some outputs have no newline immediately after BEGIN)
PEM_BLOCK_RE = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s*.*?\s*-----END CERTIFICATE-----\s*",
    re.DOTALL
)

COMMON_CA_BUNDLES = [
    "/etc/ssl/certs/ca-certificates.crt",     # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",       # RHEL/CentOS/Fedora
    "/etc/ssl/ca-bundle.pem",                 # OpenSUSE
    "/etc/ssl/cert.pem",                      # macOS (varies)
]


# ----------------------------- Model -----------------------------

@dataclass
class Finding:
    severity: str  # INFO/WARN/FAIL
    area: str
    title: str
    evidence: Dict[str, Any]


# ----------------------------- Utilities -----------------------------

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p

def write_bytes(path: str, data: bytes) -> None:
    ensure_dir(os.path.dirname(os.path.abspath(path)) or ".")
    with open(path, "wb") as f:
        f.write(data)

def write_text(path: str, data: str) -> None:
    ensure_dir(os.path.dirname(os.path.abspath(path)) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)

def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def run_cmd(cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr

def find_ca_bundle() -> Optional[str]:
    # Prefer certifi if available.
    try:
        import certifi  # type: ignore
        ca = certifi.where()
        if os.path.exists(ca):
            return ca
    except Exception:
        pass
    for p in COMMON_CA_BUNDLES:
        if os.path.exists(p):
            return p
    return None

def parse_pem_certs(pem: bytes) -> List[x509.Certificate]:
    blocks = PEM_BLOCK_RE.findall(pem)
    return [x509.load_pem_x509_certificate(b) for b in blocks]

def cert_to_pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)

def fingerprint_sha256(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()

def dn(name: x509.Name) -> str:
    return name.rfc4514_string()

def get_ext(cert: x509.Certificate, oid: x509.ObjectIdentifier):
    try:
        return cert.extensions.get_extension_for_oid(oid)
    except x509.ExtensionNotFound:
        return None

def add_finding(findings: List[Finding], severity: str, area: str, title: str, evidence: Dict[str, Any]) -> None:
    findings.append(Finding(severity=severity, area=area, title=title, evidence=evidence))

def severity_rank(sev: str) -> int:
    return {"FAIL": 3, "WARN": 2, "INFO": 1}.get(sev, 0)

def color(text: str, sev: str, enable: bool) -> str:
    if not enable or not HAS_COLOR:
        return text
    col = Fore.GREEN
    if sev == "WARN":
        col = Fore.YELLOW
    elif sev == "FAIL":
        col = Fore.RED
    return f"{col}{text}{Style.RESET_ALL}"

def normalize_bool(v: Any) -> str:
    return "YES" if v else "NO"


# ----------------------------- Hostname validation (internal) -----------------------------

def hostname_matches(cert: x509.Certificate, hostname: str) -> Tuple[bool, str]:
    """
    Conservative hostname verification:
    - Uses SAN dNSName if present.
    - Falls back to CN only if SAN absent.
    - Wildcard: only left-most label may be '*', matches exactly one label.
    """
    host = hostname.lower().strip(".")
    san_ext = get_ext(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    patterns: List[str] = []

    if san_ext is not None:
        patterns = [n.lower().strip(".") for n in san_ext.value.get_values_for_type(x509.DNSName)]

    reason_prefix = ""
    if not patterns:
        cn = None
        for attr in cert.subject:
            if attr.oid == NameOID.COMMON_NAME:
                cn = str(attr.value)
                break
        if cn:
            patterns = [cn.lower().strip(".")]
            reason_prefix = "SAN absent; fell back to CN. "
        else:
            return False, "No SAN dNSName entries and no CN present."

    def match(pattern: str, h: str) -> bool:
        if "*" not in pattern:
            return pattern == h
        if not pattern.startswith("*."):
            return False
        suffix = pattern[2:]
        if h == suffix:
            return False
        # Exactly one additional label
        return h.endswith("." + suffix) and h.count(".") == suffix.count(".") + 1

    for p in patterns:
        if match(p, host):
            return True, reason_prefix + f"Matched: {p}"

    return False, f"Hostname {hostname} did not match SAN/CN patterns: {patterns}"


# ----------------------------- OpenSSL chain fetch -----------------------------

def fetch_chain_openssl(host: str, port: int, timeout: int = 30) -> Tuple[bytes, str]:
    """
    Returns (pem_bytes, openssl_text) containing all certs shown by -showcerts.
    Note: do NOT use -brief; it can suppress PEM blocks in many builds.
    """
    cmd = [
        "openssl", "s_client",
        "-connect", f"{host}:{port}",
        "-servername", host,
        "-showcerts",
        "-verify_return_error",
    ]
    try:
        p = subprocess.run(
            cmd,
            input="",  # avoid interactive hang
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=timeout
        )
    except FileNotFoundError:
        raise RuntimeError("OpenSSL not found in PATH. Install OpenSSL or fix PATH.")

    blob = p.stdout + p.stderr
    pem_blocks = PEM_BLOCK_RE.findall(blob)
    text = blob.decode(errors="replace")

    if not pem_blocks:
        snippet = text[:4000]
        raise RuntimeError(
            "Could not extract certificates from OpenSSL output. "
            "This typically means OpenSSL did not print PEM blocks. "
            "Output starts with:\n" + snippet
        )

    return b"".join(pem_blocks), text

def split_leaf_chain(certs: List[x509.Certificate]) -> Tuple[x509.Certificate, List[x509.Certificate]]:
    leaf = certs[0]
    chain = certs[1:]
    return leaf, chain

def filter_self_issued(chain: List[x509.Certificate]) -> Tuple[List[x509.Certificate], List[x509.Certificate]]:
    """
    Filters out self-issued certs (subject == issuer) from the 'untrusted' list.
    Returns (filtered, removed).
    """
    filtered: List[x509.Certificate] = []
    removed: List[x509.Certificate] = []
    for c in chain:
        if c.subject == c.issuer:
            removed.append(c)
        else:
            filtered.append(c)
    return filtered, removed


# ----------------------------- Trust validation (OpenSSL verify) -----------------------------

_MISSING_ISSUER_HINTS = (
    "unable to get local issuer certificate",
    "unable to get issuer certificate",
    "unable to get local issuer",
    "unable to verify the first certificate",
    "depth lookup: unable to get issuer",
)

def openssl_verify_chain(leaf_pem_path: str,
                         chain_pem_path: str,
                         ca_bundle: str,
                         hostname: Optional[str] = None) -> Tuple[Optional[bool], str, Optional[bool], Optional[str]]:
    """
    Runs OpenSSL verify with:
      -CAfile <bundle>
      -untrusted chain.pem (if non-empty)
      -purpose sslserver
    Optionally also runs:
      -verify_hostname <hostname>

    Returns:
      trust_ok (bool|None), trust_output (str),
      openssl_hostname_ok (bool|None), openssl_hostname_output (str|None)
    """
    base = ["openssl", "verify", "-CAfile", ca_bundle, "-purpose", "sslserver"]
    if os.path.exists(chain_pem_path) and os.path.getsize(chain_pem_path) > 0:
        base += ["-untrusted", chain_pem_path]
    base += [leaf_pem_path]

    rc, out, err = run_cmd(base, timeout=30)
    trust_output = (out.strip() + ("\n" + err.strip() if err.strip() else "")).strip()
    trust_ok = (rc == 0)

    openssl_hostname_ok: Optional[bool] = None
    openssl_hostname_output: Optional[str] = None

    if hostname:
        cmd_h = ["openssl", "verify", "-CAfile", ca_bundle, "-purpose", "sslserver", "-verify_hostname", hostname]
        if os.path.exists(chain_pem_path) and os.path.getsize(chain_pem_path) > 0:
            cmd_h += ["-untrusted", chain_pem_path]
        cmd_h += [leaf_pem_path]
        rc2, out2, err2 = run_cmd(cmd_h, timeout=30)
        openssl_hostname_output = (out2.strip() + ("\n" + err2.strip() if err2.strip() else "")).strip()
        openssl_hostname_ok = (rc2 == 0)

    return trust_ok, trust_output, openssl_hostname_ok, openssl_hostname_output

def classify_trust_failure_as_warn(trust_output: str) -> bool:
    lo = trust_output.lower()
    return any(h in lo for h in _MISSING_ISSUER_HINTS)


# ----------------------------- Auditing checks -----------------------------

def audit(hostname: Optional[str],
          leaf: x509.Certificate,
          chain: List[x509.Certificate],
          removed_self_issued: List[x509.Certificate],
          ca_bundle_used: Optional[str],
          trust_ok: Optional[bool],
          trust_output: Optional[str],
          ossl_hn_ok: Optional[bool],
          ossl_hn_output: Optional[str]) -> List[Finding]:
    findings: List[Finding] = []
    now = utcnow()

    # ---- Collection summary
    add_finding(findings, "INFO", "Collection", "Presented certificates (leaf + intermediates)", {
        "presented_total": 1 + len(chain) + len(removed_self_issued),
        "intermediates_used": len(chain),
        "self_issued_removed": len(removed_self_issued),
    })
    if removed_self_issued:
        add_finding(findings, "WARN", "Collection", "Server sent self-issued/root in chain; removed from untrusted set", {
            "removed_subjects": [dn(c.subject) for c in removed_self_issued],
        })

    # ---- Validity (leaf)
    # Ignore deprecation warnings as requested; keep current properties.
    nvb = leaf.not_valid_before.replace(tzinfo=dt.timezone.utc)
    nva = leaf.not_valid_after.replace(tzinfo=dt.timezone.utc)

    if nvb > now:
        add_finding(findings, "FAIL", "Validity", "Leaf certificate is not yet valid", {
            "not_valid_before": str(leaf.not_valid_before),
            "now": str(now),
        })
    if nva < now:
        add_finding(findings, "FAIL", "Validity", "Leaf certificate is expired", {
            "not_valid_after": str(leaf.not_valid_after),
            "now": str(now),
        })
    days_left = (nva - now).days
    add_finding(findings, "INFO", "Validity", "Leaf validity window", {
        "not_before": str(leaf.not_valid_before),
        "not_after": str(leaf.not_valid_after),
        "days_remaining": days_left,
    })

    # ---- Hostname binding (internal)
    if hostname:
        ok, detail = hostname_matches(leaf, hostname)
        add_finding(findings, "INFO" if ok else "FAIL", "Identity", "Hostname verification (internal rules)", {
            "hostname": hostname,
            "result": "PASS" if ok else "FAIL",
            "detail": detail,
        })

    # ---- Trust/path validation (OpenSSL)
    if ca_bundle_used is None:
        add_finding(findings, "WARN", "Trust", "No CA bundle available; trust validation skipped", {})
    elif trust_ok is True:
        add_finding(findings, "INFO", "Trust", "Path validation succeeded (OpenSSL)", {
            "ca_bundle": ca_bundle_used,
            "openssl_output": (trust_output or "").strip(),
        })
    elif trust_ok is False:
        # Scenario #2: missing intermediate / issuer typically means server chain is incomplete;
        # many clients AIA-fetch. Treat as WARN with explicit evidence.
        sev = "WARN" if trust_output and classify_trust_failure_as_warn(trust_output) else "FAIL"
        add_finding(findings, sev, "Trust", "Path validation failed (OpenSSL)", {
            "ca_bundle": ca_bundle_used,
            "classification": "INCOMPLETE_CHAIN_OR_MISSING_ISSUER" if sev == "WARN" else "VALIDATION_FAILURE",
            "openssl_output": (trust_output or "").strip(),
        })

    # ---- OpenSSL hostname verification (secondary reference) + divergence detection
    if hostname and ca_bundle_used and ossl_hn_ok is not None:
        add_finding(findings, "INFO" if ossl_hn_ok else "FAIL", "Identity", "Hostname verification (OpenSSL verify_hostname)", {
            "hostname": hostname,
            "result": "PASS" if ossl_hn_ok else "FAIL",
            "openssl_output": (ossl_hn_output or "").strip(),
        })

        # Compare internal vs OpenSSL
        internal_ok, _ = hostname_matches(leaf, hostname)
        if internal_ok != ossl_hn_ok:
            add_finding(findings, "WARN", "Identity", "Divergence: internal hostname rules differ from OpenSSL", {
                "internal_result": "PASS" if internal_ok else "FAIL",
                "openssl_result": "PASS" if ossl_hn_ok else "FAIL",
                "note": "This indicates a ruleset mismatch; review wildcard/SAN/CN edge cases.",
            })

    # ---- Cryptographic strength (leaf)
    pub = leaf.public_key()
    if isinstance(pub, rsa.RSAPublicKey):
        bits = pub.key_size
        if bits < 2048:
            sev = "FAIL"
        elif bits < 4096:
            sev = "WARN"
        else:
            sev = "INFO"
        add_finding(findings, sev, "Crypto", "RSA key size policy", {
            "rsa_bits": bits,
            "policy": "<2048 FAIL; 2048–4095 WARN; >=4096 INFO",
        })

        e = pub.public_numbers().e
        if e % 2 == 0 or e <= 1:
            add_finding(findings, "FAIL", "Crypto", "Invalid RSA public exponent", {"e": e})
        elif e < 65537:
            add_finding(findings, "WARN", "Crypto", "Unusual RSA public exponent", {"e": e})
        else:
            add_finding(findings, "INFO", "Crypto", "RSA public exponent", {"e": e})

    elif isinstance(pub, ec.EllipticCurvePublicKey):
        curve = pub.curve.name
        allowed = {"secp256r1", "prime256v1", "secp384r1", "secp521r1"}
        sev = "INFO" if curve.lower() in allowed else "WARN"
        add_finding(findings, sev, "Crypto", "EC curve", {"curve": curve, "allowlist": sorted(list(allowed))})
    else:
        add_finding(findings, "WARN", "Crypto", "Unsupported public key type", {"type": type(pub).__name__})

    sig_hash = getattr(leaf.signature_hash_algorithm, "name", None)
    if sig_hash is None:
        add_finding(findings, "WARN", "Crypto", "Could not determine signature hash algorithm", {})
    else:
        if sig_hash.lower() in {"md5", "sha1"}:
            add_finding(findings, "FAIL", "Crypto", "Weak signature hash algorithm", {"signature_hash": sig_hash})
        else:
            add_finding(findings, "INFO", "Crypto", "Signature hash algorithm", {"signature_hash": sig_hash})

    # ---- Leaf semantics
    bc_leaf = get_ext(leaf, ExtensionOID.BASIC_CONSTRAINTS)
    if bc_leaf is not None and bc_leaf.value.ca:
        add_finding(findings, "FAIL", "Semantics", "Leaf certificate is marked as a CA", {
            "basic_constraints": str(bc_leaf.value),
        })

    eku = get_ext(leaf, ExtensionOID.EXTENDED_KEY_USAGE)
    if eku is None:
        add_finding(findings, "WARN", "Semantics", "Missing EKU extension (policy-dependent)", {})
    else:
        eku_oids = set(eku.value)
        if ExtendedKeyUsageOID.SERVER_AUTH not in eku_oids:
            add_finding(findings, "FAIL", "Semantics", "EKU does not include serverAuth", {
                "eku_oids": [o.dotted_string for o in eku_oids],
            })
        else:
            add_finding(findings, "INFO", "Semantics", "EKU includes serverAuth", {
                "eku_oids": [o.dotted_string for o in eku_oids],
            })

    # ---- Intermediate semantics: must be CA=true
    for idx, icert in enumerate(chain, start=1):
        bc = get_ext(icert, ExtensionOID.BASIC_CONSTRAINTS)
        if bc is None:
            add_finding(findings, "FAIL", "Semantics", "Intermediate missing BasicConstraints", {
                "position_in_chain": idx,
                "subject": dn(icert.subject),
                "issuer": dn(icert.issuer),
            })
        else:
            if not bc.value.ca:
                add_finding(findings, "FAIL", "Semantics", "Intermediate is not a CA (BasicConstraints CA=FALSE)", {
                    "position_in_chain": idx,
                    "subject": dn(icert.subject),
                    "issuer": dn(icert.issuer),
                    "basic_constraints": str(bc.value),
                })

    return findings


# ----------------------------- Reporting -----------------------------

def summarize(findings: List[Finding]) -> Tuple[str, int, Dict[str, int]]:
    counts = {"FAIL": 0, "WARN": 0, "INFO": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    if counts["FAIL"] > 0:
        return "FAIL", 2, counts
    if counts["WARN"] > 0:
        return "WARN", 1, counts
    return "OK", 0, counts

def print_report(target: str,
                 port: int,
                 leaf: x509.Certificate,
                 chain: List[x509.Certificate],
                 findings: List[Finding],
                 outdir: str,
                 use_colors: bool,
                 verbose: bool) -> int:
    status, code, counts = summarize(findings)

    print("=" * 92)
    print(f"Target: {target}:{port}")
    print(f"Analysis time (UTC): {utcnow().isoformat()}")
    print("-" * 92)
    print("Leaf:")
    print(f"  Subject : {dn(leaf.subject)}")
    print(f"  Issuer  : {dn(leaf.issuer)}")
    print(f"  Serial  : {hex(leaf.serial_number)}")
    print(f"  SHA-256 : {fingerprint_sha256(leaf)}")
    print(f"Presented intermediates used: {len(chain)}")
    print("-" * 92)

    status_col = "INFO" if status == "OK" else ("WARN" if status == "WARN" else "FAIL")
    print(f"Overall result: {color(status, status_col, use_colors)}    "
          f"FAIL={counts['FAIL']} WARN={counts['WARN']} INFO={counts['INFO']}")
    print(f"Artifacts: {os.path.abspath(outdir)}")
    print("-" * 92)

    # Group findings by severity then area
    findings_sorted = sorted(findings, key=lambda f: (-severity_rank(f.severity), f.area, f.title))

    current_area = None
    for f in findings_sorted:
        if f.area != current_area:
            current_area = f.area
            print(f"\n[{current_area}]")

        sev_label = color(f.severity, f.severity, use_colors)
        print(f"  - {sev_label}: {f.title}")

        if verbose or f.severity != "INFO":
            for k, v in f.evidence.items():
                print(f"      {k}: {v}")

    print("\n" + "=" * 92)
    return code


# ----------------------------- Main -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Certificate auditor (OpenSSL chain fetch + hostname + trust validation)")
    ap.add_argument("hostname", nargs="?", help="Hostname to analyze (e.g., alelo.com.br)")
    ap.add_argument("-p", "--port", type=int, default=443, help="Port (default: 443)")
    ap.add_argument("-o", "--outdir", default="./cert_audit_out", help="Output directory")
    ap.add_argument("--pem", help="Analyze a local PEM file containing leaf and optionally chain")
    ap.add_argument("--hostname-verify", dest="hostname_verify", help="Hostname to verify against (defaults to hostname)")
    ap.add_argument("--no-trust-verify", action="store_true", help="Skip trust/path validation")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    ap.add_argument("--verbose", action="store_true", help="Show INFO evidence too")
    args = ap.parse_args()

    use_colors = not args.no_color
    outdir = ensure_dir(args.outdir)

    if not args.pem and not args.hostname:
        print("Error: provide a hostname or --pem.", file=sys.stderr)
        return 2

    openssl_text = ""
    leaf: x509.Certificate
    chain: List[x509.Certificate]

    # ---- Acquire certs
    if args.pem:
        pem_bytes = read_bytes(args.pem)
        certs = parse_pem_certs(pem_bytes)
        if not certs:
            print("Error: no certificates found in provided PEM file.", file=sys.stderr)
            return 2
        leaf, chain = certs[0], certs[1:]
    else:
        host = args.hostname
        try:
            pem_bytes, openssl_text = fetch_chain_openssl(host, args.port)
        except Exception as e:
            print(color("FAIL", "FAIL", use_colors) + f": OpenSSL chain fetch failed: {e}", file=sys.stderr)
            return 2

        certs = parse_pem_certs(pem_bytes)
        leaf, chain = split_leaf_chain(certs)

    # Filter self-issued from untrusted chain file
    chain_filtered, removed_self_issued = filter_self_issued(chain)

    # ---- Save artifacts (leaf/chain/fullchain)
    leaf_path = os.path.join(outdir, "leaf.pem")
    chain_path = os.path.join(outdir, "chain.pem")
    fullchain_path = os.path.join(outdir, "fullchain.pem")

    write_bytes(leaf_path, cert_to_pem(leaf))
    write_bytes(chain_path, b"".join(cert_to_pem(c) for c in chain_filtered))
    write_bytes(fullchain_path, cert_to_pem(leaf) + b"".join(cert_to_pem(c) for c in chain_filtered))

    if openssl_text:
        write_text(os.path.join(outdir, "openssl_s_client.txt"), openssl_text)

    # ---- Trust validation
    hostname_for_check = args.hostname_verify or args.hostname
    ca_bundle = find_ca_bundle()

    trust_ok: Optional[bool] = None
    trust_out: Optional[str] = None
    ossl_hn_ok: Optional[bool] = None
    ossl_hn_out: Optional[str] = None

    if not args.no_trust_verify and ca_bundle:
        trust_ok, trust_out, ossl_hn_ok, ossl_hn_out = openssl_verify_chain(
            leaf_pem_path=leaf_path,
            chain_pem_path=chain_path,
            ca_bundle=ca_bundle,
            hostname=hostname_for_check
        )
        write_text(os.path.join(outdir, "openssl_verify.txt"),
                   f"Command: openssl verify -CAfile {ca_bundle} -purpose sslserver "
                   f"{'-untrusted chain.pem ' if os.path.getsize(chain_path) > 0 else ''}leaf.pem\n\n"
                   f"{(trust_out or '').strip()}\n")
        if hostname_for_check is not None and ossl_hn_out is not None:
            write_text(os.path.join(outdir, "openssl_verify_hostname.txt"),
                       f"Command: openssl verify -CAfile {ca_bundle} -purpose sslserver -verify_hostname {hostname_for_check} "
                       f"{'-untrusted chain.pem ' if os.path.getsize(chain_path) > 0 else ''}leaf.pem\n\n"
                       f"{ossl_hn_out.strip()}\n")
    elif not args.no_trust_verify and not ca_bundle:
        trust_ok = None
        trust_out = "No CA bundle found (install certifi or ensure system CA bundle exists)."

    # ---- Audit
    findings = audit(
        hostname=hostname_for_check,
        leaf=leaf,
        chain=chain_filtered,
        removed_self_issued=removed_self_issued,
        ca_bundle_used=ca_bundle if (not args.no_trust_verify) else None,
        trust_ok=trust_ok,
        trust_output=trust_out,
        ossl_hn_ok=ossl_hn_ok,
        ossl_hn_output=ossl_hn_out
    )

    # ---- Save JSON report
    status, exit_code, counts = summarize(findings)
    report = {
        "target": {
            "hostname": args.hostname,
            "port": args.port,
            "hostname_verify": hostname_for_check,
            "timestamp_utc": utcnow().isoformat(),
        },
        "leaf": {
            "subject": dn(leaf.subject),
            "issuer": dn(leaf.issuer),
            "serial": hex(leaf.serial_number),
            "not_before": str(leaf.not_valid_before),
            "not_after": str(leaf.not_valid_after),
            "sha256_fingerprint": fingerprint_sha256(leaf),
        },
        "presented_chain": {
            "presented_intermediates_total": len(chain),
            "intermediates_used": len(chain_filtered),
            "self_issued_removed": len(removed_self_issued),
            "intermediates_used_list": [
                {"subject": dn(c.subject), "issuer": dn(c.issuer), "sha256": fingerprint_sha256(c)}
                for c in chain_filtered
            ],
            "self_issued_removed_list": [
                {"subject": dn(c.subject), "issuer": dn(c.issuer), "sha256": fingerprint_sha256(c)}
                for c in removed_self_issued
            ],
        },
        "summary": {
            "status": status,
            "counts": counts,
            "exit_code": exit_code,
        },
        "trust": {
            "ca_bundle": ca_bundle,
            "trust_ok": trust_ok,
            "trust_output": trust_out,
            "openssl_hostname_ok": ossl_hn_ok,
            "openssl_hostname_output": ossl_hn_out,
        },
        "findings": [asdict(f) for f in findings],
        "artifacts": {
            "leaf_pem": os.path.abspath(leaf_path),
            "chain_pem": os.path.abspath(chain_path),
            "fullchain_pem": os.path.abspath(fullchain_path),
            "openssl_s_client_txt": os.path.abspath(os.path.join(outdir, "openssl_s_client.txt")) if openssl_text else None,
            "openssl_verify_txt": os.path.abspath(os.path.join(outdir, "openssl_verify.txt")) if trust_out else None,
            "openssl_verify_hostname_txt": os.path.abspath(os.path.join(outdir, "openssl_verify_hostname.txt")) if ossl_hn_out else None,
        },
    }
    write_text(os.path.join(outdir, "report.json"), json.dumps(report, indent=2, default=str))

    # ---- Print report
    print_code = print_report(
        target=hostname_for_check or "(unknown)",
        port=args.port,
        leaf=leaf,
        chain=chain_filtered,
        findings=findings,
        outdir=outdir,
        use_colors=use_colors,
        verbose=args.verbose
    )
    return print_code


if __name__ == "__main__":
    raise SystemExit(main())
