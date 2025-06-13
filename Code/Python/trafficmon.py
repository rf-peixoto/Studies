#!/usr/bin/env python3
import sys
import time
import argparse

# --- Existing dependency for monitoring ---
try:
    import psutil
except ImportError:
    sys.stderr.write(
        "Error: psutil module not found. Install with:\n"
        "    pip install psutil\n"
    )
    sys.exit(1)

def human_readable(num_bytes: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

def get_counters():
    try:
        return psutil.net_io_counters()
    except PermissionError:
        sys.stderr.write(
            "Error: insufficient permissions to read network statistics.\n"
            "Please rerun with elevated privileges.\n"
        )
        sys.exit(1)

def monitor_mode(args):
    # Determine interval
    if args.weeks is not None:
        count, unit, duration = args.weeks, 'week',   args.weeks   * 7 * 24 * 3600
    elif args.days is not None:
        count, unit, duration = args.days,  'day',    args.days    * 24 * 3600
    elif args.hours is not None:
        count, unit, duration = args.hours, 'hour',   args.hours   * 3600
    else:
        count, unit, duration = args.minutes, 'minute', args.minutes * 60

    plural = 's' if count != 1 else ''
    sys.stdout.write(f"Monitoring for {count} {unit}{plural} ({duration} seconds)...\n")

    start = get_counters()
    time.sleep(duration)
    end = get_counters()

    sent = end.bytes_sent - start.bytes_sent
    recv = end.bytes_recv - start.bytes_recv

    sys.stdout.write("\n=== Total Traffic ===\n")
    sys.stdout.write(f"Upload:   {sent} bytes ({human_readable(sent)})\n")
    sys.stdout.write(f"Download: {recv} bytes ({human_readable(recv)})\n")

    # Averages
    sys.stdout.write("\n=== Average Traffic ===\n")
    if unit == 'week':
        days   = count * 7
        hours  = days * 24
        sys.stdout.write(
            f"Per day:  Upload {human_readable(sent/days)}, Download {human_readable(recv/days)}\n"
            f"Per hour: Upload {human_readable(sent/hours)}, Download {human_readable(recv/hours)}\n"
        )
    elif unit == 'day':
        hours = count * 24
        sys.stdout.write(
            f"Per hour: Upload {human_readable(sent/hours)}, Download {human_readable(recv/hours)}\n"
        )
    elif unit == 'hour':
        minutes = count * 60
        sys.stdout.write(
            f"Per minute: Upload {human_readable(sent/minutes)}, Download {human_readable(recv/minutes)}\n"
        )
    # minute → no further breakdown

def upload_mode(args):
    rate_kb    = args.rate
    if rate_kb <= 0:
        sys.stderr.write("Error: rate must be positive.\n")
        sys.exit(1)
    rate_bps   = rate_kb * 1024
    chunk_size = max(1, int(rate_bps))  # bytes per 1-second interval

    protocol = args.protocol.lower()
    infile   = args.input
    rhost    = args.rhost

    def throttle_send(send_func):
        with open(infile, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                send_func(chunk)
                time.sleep(1)

    if protocol in ('http', 'https', 'webdav'):
        try:
            import requests
        except ImportError:
            sys.stderr.write("Error: requests not installed. Use `pip install requests`.\n")
            sys.exit(1)

        def data_gen():
            with open(infile, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
                    time.sleep(1)

        resp = requests.put(rhost, data=data_gen())
        if resp.status_code >= 400:
            sys.stderr.write(f"HTTP error: {resp.status_code}\n")
            sys.exit(1)
        print("Upload completed (HTTP).")

    elif protocol in ('ftp', 'ftps'):
        from urllib.parse import urlparse
        import os
        import ftplib

        parsed = urlparse(rhost)
        host   = parsed.hostname
        port   = parsed.port or (21 if protocol=='ftp' else 990)
        user   = parsed.username or 'anonymous'
        passwd = parsed.password or ''
        path   = parsed.path or '/'
        dirname, filename = os.path.split(path)

        if protocol == 'ftps':
            ftp = ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()
        ftp.connect(host, port)
        ftp.login(user, passwd)
        if protocol == 'ftps':
            ftp.prot_p()
        if dirname:
            ftp.cwd(dirname)

        def cb(_: bytes):
            time.sleep(1)

        with open(infile, 'rb') as f:
            ftp.storbinary(f'STOR {filename}', f, blocksize=chunk_size, callback=cb)
        ftp.quit()
        print("Upload completed (FTP).")

    elif protocol in ('ssh', 'sftp', 'scp'):
        try:
            import paramiko
        except ImportError:
            sys.stderr.write("Error: paramiko not installed. Use `pip install paramiko`.\n")
            sys.exit(1)
        # Parse rhost as [user@]host[:port]/remote/path
        raw = rhost
        if '/' not in raw:
            sys.stderr.write("Error: SSH rhost must include remote path, e.g. user@host:/path\n")
            sys.exit(1)
        prefix, remotepath = raw.split('/', 1)
        remotepath = '/' + remotepath
        if '@' in prefix:
            user, hostport = prefix.split('@',1)
        else:
            user, hostport = None, prefix
        if ':' in hostport:
            host, port_str = hostport.split(':',1)
            port = int(port_str)
        else:
            host, port = hostport, 22

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=port, username=user)
        sftp = client.open_sftp()
        remote_f = sftp.file(remotepath, 'wb')

        def send_chunk(chunk: bytes):
            remote_f.write(chunk)

        with open(infile, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                send_chunk(chunk)
                time.sleep(1)

        remote_f.close()
        sftp.close()
        client.close()
        print("Upload completed (SSH/SFTP).")

    elif protocol == 'raw':
        import socket
        if ':' not in rhost:
            sys.stderr.write("Error: raw rhost must be host:port\n")
            sys.exit(1)
        host, port_str = rhost.split(':',1)
        port = int(port_str)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))

        def send_raw(chunk: bytes):
            sock.sendall(chunk)

        with open(infile, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                send_raw(chunk)
                time.sleep(1)

        sock.close()
        print("Upload completed (raw TCP).")

    else:
        sys.stderr.write(f"Error: unsupported protocol '{protocol}'.\n")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Monitor network I/O or perform rate-limited upload"
    )
    sub = parser.add_subparsers(dest='mode', required=True)

    # Monitor subcommand
    pm = sub.add_parser('monitor', help="Measure upload/download over an interval")
    gm = pm.add_mutually_exclusive_group(required=True)
    gm.add_argument('--weeks',   type=int, help="Number of weeks")
    gm.add_argument('--days',    type=int, help="Number of days")
    gm.add_argument('--hours',   type=int, help="Number of hours")
    gm.add_argument('--minutes', type=int, help="Number of minutes")
    pm.set_defaults(func=monitor_mode)

    # Upload subcommand
    pu = sub.add_parser('upload', help="Upload a file with a rate limit (KB/s)")
    pu.add_argument('--rate',     type=float, required=True,
                    help="Average upload rate in KB/s")
    pu.add_argument('--protocol', type=str, required=True,
                    choices=['http','https','ftp','ftps','ssh','scp','sftp','webdav','raw'],
                    help="Protocol to use")
    pu.add_argument('--input',    type=str, required=True,
                    help="Local file to upload")
    pu.add_argument('--rhost',    type=str, required=True,
                    help="Remote host/URL (format depends on protocol)")
    pu.set_defaults(func=upload_mode)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
