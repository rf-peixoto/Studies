# Powered by ChatGPT na cara dura.

import subprocess
import time
from datetime import datetime, timedelta

def check_connection():
    try:
        # Ping Google's DNS server to check for internet connection.
        subprocess.check_call(['ping', '-c', '1', '8.8.8.8'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def log_message(message):
    with open("connection_log.txt", "a") as log_file:
        log_file.write(message + "\n")

def main():
    connection_lost_time = None
    total_downtime = timedelta(0)
    last_logged_month = None

    while True:
        current_time = datetime.now()
        if check_connection():
            if connection_lost_time:
                connection_return_time = current_time
                downtime = connection_return_time - connection_lost_time
                total_downtime += downtime
                message = f"Connection lost at: {connection_lost_time.strftime('%Y-%m-%d %H:%M:%S')}\n" \
                          f"Connection returned at: {connection_return_time.strftime('%Y-%m-%d %H:%M:%S')}\n" \
                          f"Total downtime: {downtime}\n"
                print(message)
                log_message(message)
                connection_lost_time = None
        else:
            if not connection_lost_time:
                connection_lost_time = current_time

        # Log monthly metrics
        if current_time.month != last_logged_month and current_time.strftime('%d-%H:%M:%S') == '30-23:59:59':
            monthly_message = f"Month: {current_time.strftime('%B %Y')}\nTotal Downtime This Month: {total_downtime}\n"
            print(monthly_message)
            log_message(monthly_message)
            total_downtime = timedelta(0)  # Reset total downtime for the new month
            last_logged_month = current_time.month

        time.sleep(1)  # Check every second

if __name__ == "__main__":
    main()
