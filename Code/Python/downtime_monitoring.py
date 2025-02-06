# Powered by ChatGPT na cara dura.
import asyncio
import os
import csv
import zipfile
import argparse
import logging
import time
from datetime import datetime, timedelta

# Default values
DEFAULT_LOG_DIR = "logs"
DEFAULT_CHECK_INTERVAL = 5  # seconds
DEFAULT_PING_TARGETS = ["8.8.8.8", "1.1.1.1"]  # Google & Cloudflare
DEFAULT_ALERT_THRESHOLD = 30  # Alert if downtime exceeds 30s
LOG_FORMAT = "csv"

def get_log_file():
    """Returns the current month's log file path."""
    current_month = datetime.now().strftime("%Y-%m")
    return os.path.join(LOG_DIR, f"connection_log_{current_month}.csv")

def log_event(event_type, host, downtime_start=None, downtime_end=None, total_downtime=None, latency_ms=None):
    """Logs an event to the CSV log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = get_log_file()
    file_exists = os.path.isfile(log_file)
    
    with open(log_file, "a", newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["timestamp", "event", "host", "downtime_start", "downtime_end", "total_downtime", "latency_ms"])
        writer.writerow([datetime.now().isoformat(), event_type, host, downtime_start, downtime_end, total_downtime, latency_ms])

def archive_old_logs():
    """Compresses last month's log file into a ZIP archive."""
    previous_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    old_log_file = os.path.join(LOG_DIR, f"connection_log_{previous_month}.csv")
    zip_file = os.path.join(LOG_DIR, f"connection_log_{previous_month}.zip")
    
    if os.path.exists(old_log_file):
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(old_log_file, os.path.basename(old_log_file))
        os.remove(old_log_file)

async def ping_host(host):
    """Pings a host asynchronously and returns response time in ms or None if unreachable."""
    proc = await asyncio.create_subprocess_exec("ping", "-c", "1", host,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await proc.communicate()
    
    if proc.returncode == 0:
        for line in stdout.decode().split("\n"):
            if "time=" in line:
                latency = line.split("time=")[1].split(" ")[0]
                return float(latency)
    return None

async def check_connections():
    """Checks all configured hosts in parallel and returns a summary."""
    results = await asyncio.gather(*(ping_host(target) for target in PING_TARGETS))
    return results

async def main():
    global LOG_DIR, CHECK_INTERVAL, PING_TARGETS, ALERT_THRESHOLD, DAEMON_MODE
    
    parser = argparse.ArgumentParser(description="Network Downtime Monitor")
    parser.add_argument("--log-dir", type=str, default=DEFAULT_LOG_DIR, help="Directory for log files")
    parser.add_argument("--interval", type=int, default=DEFAULT_CHECK_INTERVAL, help="Ping check interval (seconds)")
    parser.add_argument("--targets", nargs='+', default=DEFAULT_PING_TARGETS, help="List of ping targets")
    parser.add_argument("--alert-threshold", type=int, default=DEFAULT_ALERT_THRESHOLD, help="Downtime alert threshold (seconds)")
    parser.add_argument("--daemon", action="store_true", help="Run script as a background process")
    args = parser.parse_args()
    
    LOG_DIR = args.log_dir
    CHECK_INTERVAL = args.interval
    PING_TARGETS = args.targets
    ALERT_THRESHOLD = args.alert_threshold
    DAEMON_MODE = args.daemon
    
    connection_lost_time = None
    total_downtime = timedelta(0)
    last_logged_month = datetime.now().month
    
    if DAEMON_MODE:
        logging.info("Running in daemon mode.")
        import daemon
        with daemon.DaemonContext():
            asyncio.run(monitor_network(connection_lost_time, total_downtime, last_logged_month))
    else:
        await monitor_network(connection_lost_time, total_downtime, last_logged_month)

async def monitor_network(connection_lost_time, total_downtime, last_logged_month):
    while True:
        current_time = datetime.now()
        results = await check_connections()
        all_down = all(res is None for res in results)
        partially_down = any(res is None for res in results) and not all_down
        
        if all_down:
            if not connection_lost_time:
                connection_lost_time = current_time
                logging.warning("All monitored targets are down!")
        elif partially_down:
            logging.warning("Partial outage detected!")
        else:
            for host, latency in zip(PING_TARGETS, results):
                if latency is not None:
                    log_event("connection_active", host, latency_ms=latency)
            
            if connection_lost_time:
                connection_return_time = current_time
                downtime = connection_return_time - connection_lost_time
                total_downtime += downtime
                if downtime.total_seconds() > ALERT_THRESHOLD:
                    logging.error(f"Downtime exceeded alert threshold: {downtime}")
                log_event("connection_restored", "ALL", connection_lost_time, connection_return_time, str(downtime))
                connection_lost_time = None
                logging.info(f"Connection restored. Downtime: {downtime}")

        if current_time.month != last_logged_month:
            log_event("monthly_summary", "ALL", total_downtime=str(total_downtime))
            archive_old_logs()
            total_downtime = timedelta(0)
            last_logged_month = current_time.month

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
