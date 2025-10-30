#!/usr/bin/env python3
"""
verify_locally.py

Verify SPF and DKIM of a saved .eml file.

Usage:
    python verify_locally.py --eml mailbox/msg-...eml --ip 198.51.100.23
"""

import argparse
from email import policy
from email.parser import BytesParser
import dkim
import spf
import sys

def read_eml(path):
    with open(path, "rb") as f:
        raw = f.read()
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    return raw, msg

def verify_dkim(raw):
    try:
        res = dkim.verify(raw)
        return bool(res)
    except Exception as e:
        return False, str(e)

def verify_spf(ip, mailfrom, helo):
    # pyspf returns tuple (result, explanation, detail)
    res = spf.check2(i=ip, s=mailfrom, h=helo)
    return res

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eml", required=True, help="Path to saved .eml")
    parser.add_argument("--ip", required=True, help="Simulated sending IP (for SPF check)")
    parser.add_argument("--helo", default="localhost", help="HELO/EHLO domain to simulate")
    args = parser.parse_args()

    raw, msg = read_eml(args.eml)
    # Mail-from: try to read Return-Path or parse envelope; if missing, use From:
    # For lab usage, provide the envelope MAIL FROM in message 'X-Envelope-From' or based on your own logs.
    mailfrom = msg.get('Return-Path')
    if not mailfrom:
        # fallback to From header (not ideal but workable for local verification)
        mailfrom = msg.get('From')

    print("---- DKIM verification ----")
    try:
        dkim_ok = dkim.verify(raw)
        print("DKIM verified:", bool(dkim_ok))
    except Exception as e:
        print("DKIM verify error:", str(e))

    print("---- SPF verification (simulated) ----")
    res = verify_spf(args.ip, mailfrom, args.helo)
    print("SPF result tuple:", res)

if __name__ == "__main__":
    main()
