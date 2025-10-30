#!/usr/bin/env python3
"""
send_email.py
Send an email with arbitrary envelope-from and From: header.

Usage examples:

# Send to local SMTP server (default)
python send_email.py --mail-from spoofed@yourdomain.test \
    --from-header "Display Name <spoofed@yourdomain.test>" \
    --to somebody@localhost \
    --subject "Test spoof" \
    --body "This is a test." 

# Send to specific SMTP server (relay)
python send_email.py --smtp-host 192.0.2.10 --smtp-port 25 \
    --mail-from spoofed@yourdomain.test --from-header "spoofed@yourdomain.test" \
    --to target@yourdomain.test --subject "Test"

# With DKIM signing
python send_email.py --dkim-key ./dkim_private.pem --dkim-selector s1 \
    --dkim-domain yourdomain.test ...
"""

import argparse
import smtplib
from email.message import EmailMessage
import dkim
import os

def build_message(from_header, to_addrs, subject, body):
    m = EmailMessage()
    m["From"] = from_header
    m["To"] = ", ".join(to_addrs)
    m["Subject"] = subject
    m.set_content(body)
    return m

def dkim_sign(message_bytes, selector, domain, privkey_path):
    with open(privkey_path, "rb") as f:
        priv = f.read()
    sig = dkim.sign(message_bytes,
                    selector=selector.encode(),
                    domain=domain.encode(),
                    privkey=priv,
                    include_headers=[b"from", b"to", b"subject", b"date", b"message-id"])
    # dkim.sign returns the signature header bytes; we need to prepend to message
    return sig

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smtp-host", default="127.0.0.1", help="SMTP server to connect to")
    parser.add_argument("--smtp-port", type=int, default=1025, help="SMTP server port")
    parser.add_argument("--mail-from", required=True, help="Envelope MAIL FROM (RFC5321)")
    parser.add_argument("--from-header", required=True, help="From: header (what users see)")
    parser.add_argument("--to", required=True, nargs="+", help="Recipient(s)")
    parser.add_argument("--subject", default="Test message", help="Subject header")
    parser.add_argument("--body", default="Test body", help="Message body")
    parser.add_argument("--dkim-key", help="Path to DKIM private key (PEM) to sign message")
    parser.add_argument("--dkim-selector", help="DKIM selector")
    parser.add_argument("--dkim-domain", help="DKIM signing domain")
    args = parser.parse_args()

    msg = build_message(args.from_header, args.to, args.subject, args.body)
    raw = msg.as_bytes()

    # Optionally sign with DKIM before sending
    if args.dkim_key:
        if not (args.dkim_domain and args.dkim_selector):
            raise SystemExit("DKIM domain and selector required when providing dkim-key.")
        sig = dkim_sign(raw, args.dkim_selector, args.dkim_domain, args.dkim_key)
        # sig is a b"DKIM-Signature: ....\r\n"
        # Prepend the signature header to the raw message
        raw = sig + raw

    # Connect and send using given MAIL FROM (envelope sender)
    with smtplib.SMTP(args.smtp_host, args.smtp_port) as s:
        s.set_debuglevel(1)   # show SMTP dialog
        s.ehlo_or_helo_if_needed()
        # Make sure we use the provided envelope-from
        s.sendmail(args.mail_from, args.to, raw)

    print("Message sent (to SMTP server).")

if __name__ == "__main__":
    main()
