#!/usr/bin/env python3
"""
ftp_dump.py — Bulk FTP credential tester and downloader.

Input file format:
  One entry per line: <ftp://host[:port]> <user> <pass>
  Fields may be separated by spaces, colons, semicolons, or commas.
  The colon in ftp:// and optional port number are never treated as delimiters.

Examples:
  ftp://example.com user pass
  ftp://example.com:21:user:pass
  ftp://example.com,user,pass
  ftp://example.com;user;pass
"""

import argparse
import ftplib
import logging
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────
# Terminal colours
# ──────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text

def green(t):  return _c("0;32", t)
def red(t):    return _c("0;31", t)
def yellow(t): return _c("0;33", t)
def cyan(t):   return _c("0;36", t)
def bold(t):   return _c("1",    t)
def dim(t):    return _c("2",    t)

# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────
@dataclass
class FTPEntry:
    url:  str
    host: str
    port: int
    user: str
    password: str
    raw_line: str

@dataclass
class DownloadStats:
    files_ok:     int = 0
    files_failed: int = 0
    files_skipped: int = 0
    bytes_written: int = 0
    failed_paths:  list = field(default_factory=list)

@dataclass
class SessionStats:
    total:    int = 0
    valid:    int = 0
    invalid:  int = 0
    errors:   int = 0
    dl_stats: dict = field(default_factory=dict)   # host -> DownloadStats

# ──────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────
_URL_RE = re.compile(
    r'^ftp://([^\s:;,]+?)(?::(\d+))?$',   # ftp://host  or  ftp://host:port
    re.IGNORECASE
)
_DELIM_RE = re.compile(r'[\s:;,]+')

def parse_line(line: str) -> Optional[FTPEntry]:
    """
    Extract (url, user, password) from a line with mixed delimiters.
    The ftp://host[:port] prefix is treated as one atomic token.
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    # Atomically consume the ftp://host[:port] prefix
    url_match = re.match(r'(ftp://[^\s:;,]+(?::\d+)?)', line, re.IGNORECASE)
    if not url_match:
        return None

    url_token = url_match.group(1)
    remainder = line[url_match.end():]

    # Split remainder on any delimiter run
    parts = [p for p in _DELIM_RE.split(remainder) if p]
    if len(parts) < 2:
        return None

    user, password = parts[0], parts[1]

    m = _URL_RE.match(url_token)
    if not m:
        return None

    host = m.group(1)
    port = int(m.group(2)) if m.group(2) else 21

    return FTPEntry(
        url=url_token,
        host=host,
        port=port,
        user=user,
        password=password,
        raw_line=line,
    )

# ──────────────────────────────────────────────
# FTP helpers
# ──────────────────────────────────────────────
# SSL context that skips certificate verification (used for FTPS fallback)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def ftp_connect(entry: FTPEntry, timeout: int) -> ftplib.FTP:
    """
    Connect and log in.  Tries plain FTP first; if the server responds
    with a 522/534 (TLS required) or the connection is immediately
    upgraded, retries as FTPS with certificate verification disabled.
    """
    # ── Plain FTP ────────────────────────────────────────────────────
    try:
        ftp = ftplib.FTP()
        ftp.connect(entry.host, entry.port, timeout=timeout)
        ftp.login(entry.user, entry.password)
        return ftp
    except ftplib.error_perm as e:
        code = str(e)[:3]
        if code not in ('522', '534', '530'):
            raise
        # Server demands TLS — fall through to FTPS
    except ssl.SSLError:
        pass   # Server spoke TLS immediately — fall through

    # ── FTPS (explicit TLS, AUTH TLS) ────────────────────────────────
    ftp_tls = ftplib.FTP_TLS(context=_SSL_CTX)
    ftp_tls.connect(entry.host, entry.port, timeout=timeout)
    ftp_tls.auth()            # send AUTH TLS
    ftp_tls.login(entry.user, entry.password)
    ftp_tls.prot_p()          # encrypt data channel too
    return ftp_tls


def ftp_test(entry: FTPEntry, timeout: int, retries: int) -> bool:
    """Return True if credentials are valid."""
    for attempt in range(1, retries + 1):
        try:
            ftp = ftp_connect(entry, timeout)
            ftp.quit()
            return True
        except ftplib.error_perm:
            return False          # auth failure — no point retrying
        except Exception:
            if attempt == retries:
                return False
            time.sleep(1)
    return False


def ftp_du(entry: FTPEntry, timeout: int) -> Optional[int]:
    """
    Try to calculate total remote size (bytes).
    Falls back to walking the tree with ftplib if lftp is unavailable.
    Returns None on failure.
    """
    # Try lftp du first (fast)
    if shutil.which("lftp"):
        try:
            cmd = (
                f"open -u {_sh(entry.user)},{_sh(entry.password)} "
                f"{entry.host}:{entry.port}; du -sb"
            )
            result = subprocess.run(
                ["lftp", "-c", cmd],
                capture_output=True, text=True, timeout=timeout * 4
            )
            m = re.match(r'(\d+)', result.stdout.strip())
            if m:
                return int(m.group(1))
        except Exception:
            pass

    # Fallback: walk with ftplib
    try:
        ftp = ftp_connect(entry, timeout)
        total = _walk_size(ftp, "/")
        ftp.quit()
        return total
    except Exception:
        return None


def _walk_size(ftp: ftplib.FTP, path: str) -> int:
    total = 0
    try:
        items = []
        ftp.retrlines(f'LIST {path}', items.append)
        for item in items:
            parts = item.split()
            if len(parts) < 9:
                continue
            name = ' '.join(parts[8:])
            if name in ('.', '..'):
                continue
            is_dir = item.startswith('d')
            full = f"{path.rstrip('/')}/{name}"
            if is_dir:
                total += _walk_size(ftp, full)
            else:
                try:
                    total += int(parts[4])
                except ValueError:
                    pass
    except Exception:
        pass
    return total


def _sh(s: str) -> str:
    """Shell-safe quote a value for lftp -c strings."""
    return "'" + s.replace("'", "'\\''") + "'"


def fmt_size(b: int) -> str:
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if b >= threshold:
            return f"{b / threshold:.2f} {unit}"
    return f"{b} B"

# ──────────────────────────────────────────────
# Download — mirror strategy then file-by-file fallback
# ──────────────────────────────────────────────
def download_entry(
    entry: FTPEntry,
    target_dir: Path,
    verbose: bool,
    retries: int,
    timeout: int,
    log: logging.Logger,
) -> DownloadStats:
    target_dir.mkdir(parents=True, exist_ok=True)
    stats = DownloadStats()

    # ── Strategy 1: lftp mirror ──────────────────
    if shutil.which("lftp"):
        log.info(f"[{entry.host}] Attempting lftp mirror …")
        success = _lftp_mirror(entry, target_dir, verbose, retries, timeout, log)
        if success:
            # Count what was downloaded
            for f in target_dir.rglob("*"):
                if f.is_file():
                    stats.files_ok += 1
                    stats.bytes_written += f.stat().st_size
            log.info(f"[{entry.host}] Mirror succeeded: "
                     f"{stats.files_ok} files / {fmt_size(stats.bytes_written)}")
            return stats
        log.warning(f"[{entry.host}] lftp mirror failed — falling back to file-by-file")

    # ── Strategy 2: file-by-file via ftplib ──────
    log.info(f"[{entry.host}] Starting file-by-file download …")
    _ftplib_download(entry, target_dir, "/", stats, verbose, retries, timeout, log)
    log.info(
        f"[{entry.host}] File-by-file complete: "
        f"{stats.files_ok} ok / {stats.files_failed} failed / "
        f"{stats.files_skipped} skipped / {fmt_size(stats.bytes_written)}"
    )
    return stats


def _lftp_mirror(
    entry: FTPEntry,
    target_dir: Path,
    verbose: bool,
    retries: int,
    timeout: int,
    log: logging.Logger,
) -> bool:
    """Run lftp mirror. Returns True on success."""
    v_flag = "-v" if verbose else ""
    # net:timeout sets socket-level timeout; net:reconnect-interval-base controls retry pacing
    settings = (
        f"set net:timeout {timeout}; "
        f"set net:max-retries {retries}; "
        f"set net:reconnect-interval-base 2; "
        f"set ftp:passive-mode true; "
        f"set ssl:verify-certificate false; "
    )
    cmd = (
        f"{settings}"
        f"open -u {_sh(entry.user)},{_sh(entry.password)} "
        f"{entry.host}:{entry.port}; "
        f"mirror -c --parallel=3 {v_flag} / {_sh(str(target_dir))}"
    )
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                ["lftp", "-c", cmd],
                capture_output=not verbose,
                text=True,
                timeout=timeout * 60,   # overall cap: generous for large servers
            )
            if result.returncode == 0:
                return True
            log.warning(
                f"[{entry.host}] lftp mirror attempt {attempt}/{retries} "
                f"returned {result.returncode}"
                + (f": {result.stderr.strip()}" if result.stderr else "")
            )
        except subprocess.TimeoutExpired:
            log.warning(f"[{entry.host}] lftp mirror attempt {attempt}/{retries} timed out")
        except Exception as e:
            log.warning(f"[{entry.host}] lftp mirror attempt {attempt}/{retries} error: {e}")
        if attempt < retries:
            time.sleep(2 ** attempt)   # exponential back-off: 2s, 4s, …
    return False


def _ftplib_download(
    entry: FTPEntry,
    local_base: Path,
    remote_path: str,
    stats: DownloadStats,
    verbose: bool,
    retries: int,
    timeout: int,
    log: logging.Logger,
    _ftp: Optional[ftplib.FTP] = None,
    _owned: bool = True,
):
    """
    Recursively walk remote_path and download every file, recreating
    the directory tree under local_base.  Resumes partial files where
    the server supports REST.
    """
    # Establish connection lazily (caller may pass an existing one)
    if _ftp is None:
        for attempt in range(1, retries + 1):
            try:
                _ftp = ftp_connect(entry, timeout)
                break
            except Exception as e:
                if attempt == retries:
                    log.error(f"[{entry.host}] Cannot connect for file-by-file: {e}")
                    return
                time.sleep(2 ** attempt)

    try:
        items = []
        _ftp.retrlines(f'LIST {remote_path}', items.append)
    except Exception as e:
        log.warning(f"[{entry.host}] LIST {remote_path} failed: {e}")
        return

    for item in items:
        parts = item.split()
        if len(parts) < 9:
            continue
        name = ' '.join(parts[8:])
        if name in ('.', '..'):
            continue

        is_dir  = item.startswith('d')
        is_link = item.startswith('l')
        remote_full = f"{remote_path.rstrip('/')}/{name}"

        if is_dir or (is_link and _is_dir_link(_ftp, remote_full)):
            # Recurse — reuse the same connection
            _ftplib_download(
                entry, local_base, remote_full, stats, verbose,
                retries, timeout, log, _ftp=_ftp, _owned=False
            )
        else:
            # It's a file
            rel_path = remote_full.lstrip('/')
            local_path = local_base / rel_path
            local_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                remote_size = int(parts[4])
            except ValueError:
                remote_size = None

            # Skip if already complete
            if local_path.exists() and remote_size is not None:
                local_size = local_path.stat().st_size
                if local_size == remote_size:
                    if verbose:
                        print(dim(f"  SKIP  {remote_full}"))
                    stats.files_skipped += 1
                    continue

            success = _download_file(
                entry, _ftp, remote_full, local_path,
                remote_size, retries, timeout, verbose, log
            )
            if success:
                stats.files_ok += 1
                stats.bytes_written += local_path.stat().st_size
            else:
                stats.files_failed += 1
                stats.failed_paths.append(remote_full)
                # Reconnect after a failed transfer — the session may be broken
                try:
                    _ftp.quit()
                except Exception:
                    pass
                for attempt in range(1, retries + 1):
                    try:
                        _ftp = ftp_connect(entry, timeout)
                        break
                    except Exception:
                        if attempt == retries:
                            log.error(f"[{entry.host}] Cannot reconnect after failure")
                            return
                        time.sleep(2 ** attempt)

    if _owned:
        try:
            _ftp.quit()
        except Exception:
            pass


def _is_dir_link(ftp: ftplib.FTP, path: str) -> bool:
    """Detect if a symlink points to a directory by trying to CWD into it."""
    try:
        prev = ftp.pwd()
        ftp.cwd(path)
        ftp.cwd(prev)
        return True
    except Exception:
        return False


def _download_file(
    entry: FTPEntry,
    ftp: ftplib.FTP,
    remote_path: str,
    local_path: Path,
    remote_size: Optional[int],
    retries: int,
    timeout: int,
    verbose: bool,
    log: logging.Logger,
) -> bool:
    """
    Download a single file with resume support (REST) and retries.
    Returns True on success.
    """
    for attempt in range(1, retries + 1):
        resume_offset = 0
        mode = 'wb'

        if local_path.exists():
            resume_offset = local_path.stat().st_size
            if remote_size is not None and resume_offset >= remote_size:
                return True   # already complete
            if resume_offset > 0:
                mode = 'ab'
                if verbose:
                    print(dim(f"  RESUME {remote_path} at {fmt_size(resume_offset)}"))

        try:
            with open(local_path, mode) as f:
                if resume_offset > 0:
                    ftp.voidcmd(f'REST {resume_offset}')
                cmd = f'RETR {remote_path}'
                ftp.retrbinary(cmd, f.write, blocksize=1 << 17)  # 128 KB blocks

            if verbose:
                size_str = fmt_size(local_path.stat().st_size)
                print(green(f"  ✓  {remote_path}") + dim(f"  ({size_str})"))
            return True

        except ftplib.error_perm as e:
            log.warning(f"[{entry.host}] Permission error on {remote_path}: {e}")
            return False   # no point retrying a permission error

        except Exception as e:
            log.warning(
                f"[{entry.host}] Attempt {attempt}/{retries} failed "
                f"for {remote_path}: {e}"
            )
            # Truncate partial file so next attempt starts clean if REST isn't supported
            try:
                if local_path.exists() and mode == 'wb':
                    local_path.unlink()
            except Exception:
                pass
            if attempt < retries:
                time.sleep(2 ** attempt)

    return False

# ──────────────────────────────────────────────
# Per-entry worker (called from thread pool)
# ──────────────────────────────────────────────
def process_entry(
    entry: FTPEntry,
    args,
    log: logging.Logger,
) -> tuple[FTPEntry, bool, Optional[int], Optional[DownloadStats]]:
    """
    Returns (entry, is_valid, size_bytes_or_None, dl_stats_or_None).
    """
    # ── Credential check ──
    valid = ftp_test(entry, args.timeout, args.retries)
    if not valid:
        return entry, False, None, None

    # ── Size calculation ──
    size_bytes = None
    if args.size:
        size_bytes = ftp_du(entry, args.timeout)

    # ── Download ──
    dl_stats = None
    if args.download:
        safe_host = re.sub(r'[:/\\]', '_', f"{entry.host}_{entry.port}" if entry.port != 21 else entry.host)
        target_dir = Path(args.output_dir) / safe_host
        dl_stats = download_entry(entry, target_dir, args.verbose, args.retries, args.timeout, log)
        _write_host_log(entry, dl_stats, target_dir, log)

    return entry, True, size_bytes, dl_stats


def _write_host_log(entry: FTPEntry, stats: DownloadStats, target_dir: Path, log: logging.Logger):
    """Write a per-host download summary next to the downloaded files."""
    log_path = target_dir / "_ftp_dump_log.txt"
    try:
        with open(log_path, 'w') as f:
            f.write(f"Host    : {entry.host}:{entry.port}\n")
            f.write(f"User    : {entry.user}\n")
            f.write(f"Files OK: {stats.files_ok}\n")
            f.write(f"Failed  : {stats.files_failed}\n")
            f.write(f"Skipped : {stats.files_skipped}\n")
            f.write(f"Size    : {fmt_size(stats.bytes_written)}\n")
            if stats.failed_paths:
                f.write("\nFailed paths:\n")
                for p in stats.failed_paths:
                    f.write(f"  {p}\n")
    except Exception as e:
        log.warning(f"Could not write host log: {e}")

# ──────────────────────────────────────────────
# Output helpers (thread-safe via print's GIL)
# ──────────────────────────────────────────────
_PRINT_LOCK = __import__('threading').Lock()

def tprint(*args, **kwargs):
    with _PRINT_LOCK:
        print(*args, **kwargs)


def print_result(entry: FTPEntry, valid: bool, size_bytes, dl_stats, args):
    if valid:
        parts = [green("VALID"), entry.raw_line]
        if size_bytes is not None:
            parts.append(cyan(f"[{fmt_size(size_bytes)}]"))
        if dl_stats is not None:
            parts.append(dim(
                f"[↓ {dl_stats.files_ok} files / "
                f"{fmt_size(dl_stats.bytes_written)}"
                + (f" / {dl_stats.files_failed} failed" if dl_stats.files_failed else "")
                + "]"
            ))
        tprint("  ".join(parts))
    else:
        if args.verbose:
            tprint(red("INVALID") + "  " + dim(entry.raw_line))

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────
def print_summary(stats: SessionStats, args):
    tprint()
    tprint(bold("─" * 52))
    tprint(bold("  Summary"))
    tprint(bold("─" * 52))
    tprint(f"  Total entries : {stats.total}")
    tprint(f"  Valid         : {green(str(stats.valid))}")
    tprint(f"  Invalid       : {red(str(stats.invalid))}")
    if stats.errors:
        tprint(f"  Parse errors  : {yellow(str(stats.errors))}")

    if args.download and stats.dl_stats:
        total_files   = sum(d.files_ok     for d in stats.dl_stats.values())
        total_failed  = sum(d.files_failed  for d in stats.dl_stats.values())
        total_skipped = sum(d.files_skipped for d in stats.dl_stats.values())
        total_bytes   = sum(d.bytes_written for d in stats.dl_stats.values())
        tprint()
        tprint(f"  Files OK      : {total_files}")
        tprint(f"  Files failed  : {red(str(total_failed)) if total_failed else '0'}")
        tprint(f"  Files skipped : {total_skipped}")
        tprint(f"  Total size    : {cyan(fmt_size(total_bytes))}")
        tprint(f"  Output dir    : {args.output_dir}")

        all_failed = [
            (host, p)
            for host, d in stats.dl_stats.items()
            for p in d.failed_paths
        ]
        if all_failed:
            tprint()
            tprint(yellow(f"  ⚠  {len(all_failed)} file(s) could not be downloaded:"))
            for host, path in all_failed[:20]:
                tprint(dim(f"      {host}{path}"))
            if len(all_failed) > 20:
                tprint(dim(f"      … and {len(all_failed) - 20} more (see per-host logs)"))

    tprint(bold("─" * 52))

# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ftp_dump.py",
        description="Bulk FTP credential tester and downloader.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("file", help="Input file with FTP credentials")
    p.add_argument("-v", "--verbose",    action="store_true", help="Show per-file progress and invalid entries")
    p.add_argument("-s", "--size",       action="store_true", help="Calculate total remote size for valid FTPs")
    p.add_argument("--download",         action="store_true", help="Download all content of valid FTPs")
    p.add_argument("--output-dir",       default="./ftp_downloads", metavar="DIR",
                   help="Base directory for downloads (default: ./ftp_downloads)")
    p.add_argument("--workers",          type=int, default=4, metavar="N",
                   help="Parallel host workers (default: 4)")
    p.add_argument("--retries",          type=int, default=3, metavar="N",
                   help="Retry attempts per operation (default: 3)")
    p.add_argument("--timeout",          type=int, default=10, metavar="SEC",
                   help="Connection/read timeout in seconds (default: 10)")
    return p


def setup_logging(verbose: bool) -> logging.Logger:
    log = logging.getLogger("ftp_dump")
    log.setLevel(logging.DEBUG if verbose else logging.WARNING)
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter(dim("%(levelname)s  %(message)s")))
    log.addHandler(h)
    return log

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = build_parser()
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        parser.error(f"File not found: {args.file}")

    if args.workers < 1:
        parser.error("--workers must be >= 1")

    log = setup_logging(args.verbose)

    # Graceful Ctrl+C
    interrupted = False
    def _sig(sig, frame):
        nonlocal interrupted
        interrupted = True
        tprint(yellow("\n  Interrupted — finishing in-flight tasks …"), file=sys.stderr)
    signal.signal(signal.SIGINT, _sig)

    # Parse input file
    entries: list[FTPEntry] = []
    parse_errors = 0
    with open(args.file, 'r', errors='replace') as f:
        for lineno, raw in enumerate(f, 1):
            entry = parse_line(raw)
            if entry is None:
                stripped = raw.strip()
                if stripped and not stripped.startswith('#'):
                    log.warning(f"Line {lineno}: cannot parse — {stripped!r}")
                    parse_errors += 1
            else:
                entries.append(entry)

    if not entries:
        print(red("No valid entries found in input file."), file=sys.stderr)
        sys.exit(1)

    tprint(bold(f"\n  ftp_dump  —  {len(entries)} entries  |  "
                f"{args.workers} workers  |  "
                f"retries={args.retries}  timeout={args.timeout}s\n"))

    stats = SessionStats(total=len(entries), errors=parse_errors)

    # Process entries in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_entry, entry, args, log): entry
            for entry in entries
        }
        for future in as_completed(futures):
            if interrupted:
                break
            try:
                entry, valid, size_bytes, dl_stats = future.result()
            except Exception as e:
                entry = futures[future]
                log.error(f"Unhandled error for {entry.host}: {e}")
                stats.errors += 1
                continue

            if valid:
                stats.valid += 1
                if dl_stats:
                    stats.dl_stats[entry.host] = dl_stats
            else:
                stats.invalid += 1

            print_result(entry, valid, size_bytes, dl_stats, args)

    print_summary(stats, args)


if __name__ == "__main__":
    main()
