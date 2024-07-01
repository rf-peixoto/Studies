import os
import requests
import time
import logging
import threading
from queue import Queue
from stem import Signal
from stem.control import Controller
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import socks
import socket
from termcolor import colored
import urllib.parse
from tqdm import tqdm
import argparse
import json

# Configuration parameters (default values)
config = {
    'timeout': 30,  # Timeout for requests in seconds
    'sleep_time': 5,  # Sleep time between requests in seconds
    'tor_control_port': 9051,
    'tor_socks_port': 9050,
    'tor_password': None,  # Set your Tor control password if applicable
    'renew_ip_on_error': True,  # Enable or disable IP renewal
    'decode_urls': True,  # Enable or disable URL decoding
    'download_dir': 'downloads',  # Directory to save downloads
    'concurrent_downloads': 4,  # Number of parallel downloads
    'progress_interval': 100  # Interval for detailed progress reporting
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': '',  # This will be set dynamically
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1'
}
log_file = 'download_log.txt'
urls_file = 'urls.txt'
failed_downloads_file = 'failed_downloads.txt'

# Set up logging
logging.basicConfig(filename=log_file, level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Global counters
success_count = 0
fail_count = 0

# Lock for counters
counter_lock = threading.Lock()

# Function to get a new Tor identity
def renew_tor_ip():
    try:
        with Controller.from_port(port=config['tor_control_port']) as controller:
            if config['tor_password']:
                controller.authenticate(password=config['tor_password'])
            else:
                controller.authenticate()
            controller.signal(Signal.NEWNYM)
        logging.info("Tor IP renewed.")
    except Exception as e:
        logging.error(f"Error renewing Tor IP: {e}")
        print(f"Error renewing Tor IP: {colored(str(e), 'red')}")

# Function to test Tor connection
def test_tor_connection():
    try:
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", config['tor_socks_port'])
        socket.socket = socks.socksocket
        response = requests.get("http://check.torproject.org", timeout=10, proxies=session.proxies)
        if "Congratulations. This browser is configured to use Tor." in response.text:
            logging.info("Tor connection successful.")
            print(colored("Tor connection successful.", "green"))
            return True
        else:
            logging.warning("Tor connection test failed. Not using Tor.")
            print(colored("Tor connection test failed. Not using Tor.", "red"))
            return False
    except Exception as e:
        logging.error(f"Tor connection failed: {e}")
        print(f"Tor connection failed: {colored(str(e), 'red')}")
        return False

# Set up requests session with retries and Tor proxy
session = requests.Session()
retry = Retry(
    total=5,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Configure Tor proxy
session.proxies = {
    'http': f'socks5h://127.0.0.1:{config['tor_socks_port']}',
    'https': f'socks5h://127.0.0.1:{config['tor_socks_port']}'
}

# Ensure download directory exists
if not os.path.exists(config['download_dir']):
    os.makedirs(config['download_dir'])

# Function to download a file from a URL
def download_file(url, progress_bar=None, progress_lock=None):
    global success_count, fail_count
    filename = os.path.basename(url)
    filepath = os.path.join(config['download_dir'], filename)
    try:
        logging.info(f"Attempting to download: {filename}")
        host = url.split('/')[2]
        headers['Host'] = host
        headers['Referer'] = '/'.join(url.split('/')[:-1]) + '/'
        response = session.get(url, headers=headers, timeout=config['timeout'], allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type')
        logging.info(f"Content-Type: {content_type}")
        with open(filepath, 'wb') as file:
            file.write(response.content)
        logging.info(f"Downloaded: {filename}")
        print(f"Downloaded: {colored(filename, 'green')}")

        with counter_lock:
            success_count += 1
            if success_count % config['progress_interval'] == 0:
                print(f"{success_count} files downloaded successfully.")

        if progress_bar:
            with progress_lock:
                progress_bar.update(1)
        return True
    except requests.exceptions.HTTPError as e:
        logging.error(f"Failed to download {filename}: {e}")
        with counter_lock:
            fail_count += 1
        if e.response.status_code == 404:
            print(f"Failed to download {colored(filename, 'red')}: {colored('404 Not Found', 'red')}")
        else:
            print(f"Failed to download {colored(filename, 'red')}: {colored(str(e), 'red')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download {filename}: {e}")
        with counter_lock:
            fail_count += 1
        print(f"Failed to download {colored(filename, 'red')}: {colored(str(e), 'red')}")
    return False

# Worker function for threading
def worker(url_queue, progress_bar, progress_lock, failed_downloads):
    while not url_queue.empty():
        url = url_queue.get()
        if config['decode_urls']:
            url = urllib.parse.unquote(url)
        success = download_file(url, progress_bar, progress_lock)
        time.sleep(config['sleep_time'])
        if config['renew_ip_on_error'] and not success:
            renew_tor_ip()
            failed_downloads.append(url)
        url_queue.task_done()

# Read URLs from file and add to queue
url_queue = Queue()
with open(urls_file, 'r') as file:
    for url in file.readlines():
        url_queue.put(url.strip())

failed_downloads = []

# Test Tor connection before starting the download process
def start_download():
    if test_tor_connection():
        # Set up progress bar and lock for thread-safe updates
        progress_bar = tqdm(total=url_queue.qsize(), desc="Downloading files")
        progress_lock = threading.Lock()
        # Start worker threads
        threads = []
        for _ in range(config['concurrent_downloads']):
            thread = threading.Thread(target=worker, args=(url_queue, progress_bar, progress_lock, failed_downloads))
            thread.start()
            threads.append(thread)

        # Wait for all threads to finish
        for thread in threads:
            thread.join()
        
        progress_bar.close()
    else:
        logging.error("Exiting due to Tor connection failure.")
        print(colored("Exiting due to Tor connection failure.", "red"))

start_download()

# Save failed downloads to a file
if failed_downloads:
    with open(failed_downloads_file, 'w') as file:
        for url in failed_downloads:
            file.write(url + '\n')

# Retry failed downloads
if os.path.exists(failed_downloads_file):
    with open(failed_downloads_file, 'r') as file:
        for url in file.readlines():
            url_queue.put(url.strip())

    failed_downloads.clear()
    start_download()

    if os.path.exists(failed_downloads_file):
        os.remove(failed_downloads_file)

# Command-line argument parsing
def parse_arguments():
    parser = argparse.ArgumentParser(description="Download files over Tor network")
    parser.add_argument('--config', type=str, help="Path to the configuration file")
    parser.add_argument('--decode', action='store_true', help="Decode URLs before downloading")
    parser.add_argument('--dir', type=str, help="Directory to save downloads")
    return parser.parse_args()

# Load configuration from a JSON file
def load_config(config_file):
    with open(config_file, 'r') as file:
        return json.load(file)

# Main function
def main():
    args = parse_arguments()

    if args.config:
        custom_config = load_config(args.config)
        config.update(custom_config)

    if args.decode:
        config['decode_urls'] = True

    if args.dir:
        config['download_dir'] = args.dir

    # Ensure download directory exists
    if not os.path.exists(config['download_dir']):
        os.makedirs(config['download_dir'])

    # Start the download process
    start_download()

    # Retry failed downloads
    if os.path.exists(failed_downloads_file):
        with open(failed_downloads_file, 'r') as file:
            for url in file.readlines():
                url_queue.put(url.strip())

        failed_downloads.clear()
        start_download()

        if os.path.exists(failed_downloads_file):
            os.remove(failed_downloads_file)

    # Print summary
    print(f"Download completed: {success_count} successful, {fail_count} failed.")

if __name__ == "__main__":
    main()
