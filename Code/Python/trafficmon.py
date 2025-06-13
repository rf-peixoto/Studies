#!/usr/bin/env python3

import time
import argparse
import sys

# Attempt import of psutil
try:
    import psutil
except ImportError:
    sys.stderr.write(
        "Error: psutil module not found. Install it with:\n"
        "    pip install psutil\n"
    )
    sys.exit(1)

def human_readable(num_bytes: float) -> str:
    """Convert a byte count into a human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

def get_counters():
    """Retrieve total network I/O counters, or exit on permission error."""
    try:
        return psutil.net_io_counters()
    except PermissionError:
        sys.stderr.write(
            "Error: insufficient permissions to read network statistics.\n"
            "Please rerun with elevated privileges (e.g. sudo).\n"
        )
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Monitor local network I/O over a specified interval"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--weeks",   type=int, help="Number of weeks to monitor"
    )
    group.add_argument(
        "--days",    type=int, help="Number of days to monitor"
    )
    group.add_argument(
        "--hours",   type=int, help="Number of hours to monitor"
    )
    group.add_argument(
        "--minutes", type=int, help="Number of minutes to monitor"
    )
    args = parser.parse_args()

    # Determine interval count, unit and duration in seconds
    if args.weeks is not None:
        count, unit, duration = args.weeks, 'week', args.weeks * 7 * 24 * 3600
    elif args.days is not None:
        count, unit, duration = args.days, 'day', args.days * 24 * 3600
    elif args.hours is not None:
        count, unit, duration = args.hours, 'hour', args.hours * 3600
    else:  # args.minutes is not None
        count, unit, duration = args.minutes, 'minute', args.minutes * 60

    plural = 's' if count != 1 else ''
    print(f"Starting network I/O monitoring for {count} {unit}{plural} ({duration} seconds)...")

    # Capture counters at start and end
    start = get_counters()
    time.sleep(duration)
    end = get_counters()

    sent = end.bytes_sent   - start.bytes_sent
    recv = end.bytes_recv   - start.bytes_recv

    # Total
    print("\n=== Total Traffic ===")
    print(f"Upload:   {sent} bytes ({human_readable(sent)})")
    print(f"Download: {recv} bytes ({human_readable(recv)})")

    # Sub‐interval averages
    print("\n=== Average Traffic ===")
    if unit == 'week':
        days_count    = count * 7
        hours_count   = days_count * 24
        avg_sent_day  = sent / days_count
        avg_recv_day  = recv / days_count
        avg_sent_hour = sent / hours_count
        avg_recv_hour = recv / hours_count
        print(f"Per day:  Upload {human_readable(avg_sent_day)}, Download {human_readable(avg_recv_day)}")
        print(f"Per hour: Upload {human_readable(avg_sent_hour)}, Download {human_readable(avg_recv_hour)}")
    elif unit == 'day':
        hours_count   = count * 24
        avg_sent_hour = sent / hours_count
        avg_recv_hour = recv / hours_count
        print(f"Per hour: Upload {human_readable(avg_sent_hour)}, Download {human_readable(avg_recv_hour)}")
    elif unit == 'hour':
        minutes_count = count * 60
        avg_sent_min  = sent / minutes_count
        avg_recv_min  = recv / minutes_count
        print(f"Per minute: Upload {human_readable(avg_sent_min)}, Download {human_readable(avg_recv_min)}")
    # unit == 'minute': no further breakdown

if __name__ == "__main__":
    main()
