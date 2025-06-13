#!/usr/bin/env python3

import time
import argparse
import sys

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
        description="Monitor local network I/O and compute upload allowances"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--weeks",   type=int, help="Number of weeks to monitor")
    group.add_argument("--days",    type=int, help="Number of days to monitor")
    group.add_argument("--hours",   type=int, help="Number of hours to monitor")
    group.add_argument("--minutes", type=int, help="Number of minutes to monitor")
    args = parser.parse_args()

    # Determine interval count, unit, and total seconds
    if args.weeks is not None:
        count, unit, duration = args.weeks, 'week',   args.weeks   * 7 * 24 * 3600
    elif args.days is not None:
        count, unit, duration = args.days,  'day',    args.days    * 24 * 3600
    elif args.hours is not None:
        count, unit, duration = args.hours, 'hour',   args.hours   * 3600
    else:
        count, unit, duration = args.minutes, 'minute', args.minutes * 60

    plural = 's' if count != 1 else ''
    sys.stdout.write(
        f"Monitoring network I/O for {count} {unit}{plural} ({duration} seconds)...\n"
    )

    # Sample counters
    start = get_counters()
    time.sleep(duration)
    end = get_counters()

    # Compute totals
    sent = end.bytes_sent - start.bytes_sent
    recv = end.bytes_recv - start.bytes_recv

    # Compute averages
    avg_rate       = sent / duration  # bytes per second
    if unit == 'week':
        days_count  = count * 7
        hours_count = days_count * 24
        avg_per_day = sent / days_count
        avg_per_hour= sent / hours_count
    elif unit == 'day':
        hours_count = count * 24
        avg_per_day = None
        avg_per_hour= sent / hours_count
    elif unit == 'hour':
        minutes_count = count * 60
        avg_per_day = None
        avg_per_hour= None
        avg_per_min = sent / minutes_count
    else:  # minute
        avg_per_day = None
        avg_per_hour= None
        avg_per_min = None

    # Report measured usage
    sys.stdout.write("\n=== Measured Traffic ===\n")
    sys.stdout.write(f"Upload:   {sent} bytes ({human_readable(sent)})\n")
    sys.stdout.write(f"Download: {recv} bytes ({human_readable(recv)})\n")

    # Report historical averages
    sys.stdout.write("\n=== Historical Upload Averages ===\n")
    sys.stdout.write(f"Average rate: {avg_rate:.2f} B/s ({human_readable(avg_rate)}/s)\n")
    if unit == 'week':
        sys.stdout.write(f"Per day:    {human_readable(avg_per_day)}\n")
        sys.stdout.write(f"Per hour:   {human_readable(avg_per_hour)}\n")
    elif unit == 'day':
        sys.stdout.write(f"Per hour:   {human_readable(avg_per_hour)}\n")
    elif unit == 'hour':
        sys.stdout.write(f"Per minute: {human_readable(avg_per_min)}\n")

    # Recommend allowances for next interval
    sys.stdout.write("\n=== Recommended Upload Allowance for Next Interval ===\n")
    sys.stdout.write(
        f"Total budget: {sent} bytes ({human_readable(sent)})\n"
    )
    sys.stdout.write(
        f"Maintain ≤ {avg_rate:.2f} B/s ({human_readable(avg_rate)}/s)\n"
    )
    if unit == 'week':
        sys.stdout.write(
            f"Limit per day:  {human_readable(avg_per_day)}\n"
            f"Limit per hour: {human_readable(avg_per_hour)}\n"
        )
    elif unit == 'day':
        sys.stdout.write(f"Limit per hour: {human_readable(avg_per_hour)}\n")
    elif unit == 'hour':
        sys.stdout.write(f"Limit per minute: {human_readable(avg_per_min)}\n")
    # for minute interval, only total budget applies

if __name__ == "__main__":
    main()
