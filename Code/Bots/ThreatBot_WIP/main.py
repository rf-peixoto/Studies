import requests
import json
import telegram
import logging
import os
import datetime
from time import sleep
from config import Config

# Load configuration
config = Config('config.json')

# Configure logging
logging.basicConfig(filename=config.log_file, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def get_time_format():
    try:
        current_utc_time = datetime.datetime.utcnow()
        gmt_minus_3_offset = datetime.timedelta(hours=-3)
        current_date_time_gmt_minus_3 = current_utc_time + gmt_minus_3_offset
        return current_date_time_gmt_minus_3.strftime("%Y-%m-%dT%H:%M:%S-03:00")
    except Exception as e:
        logging.error(f"Error in get_time_format: {e}")
        return None

def download_cve_feed():
    try:
        url = f"{config.cve_url}?pubStartDate={get_time_format()}&pubEndDate={get_time_format()}"
        response = requests.get(url)
        response.raise_for_status()

        json_data = response.json()
        with open(config.local_cve_file, "w") as outfile:
            json.dump(json_data, outfile)
        logging.info("CVE feed downloaded and saved.")
    except requests.RequestException as e:
        logging.error(f"Failed to download CVE feed: {e}")
    except Exception as e:
        logging.error(f"Error in download_cve_feed: {e}")

def parse_cve_file():
    cves = []
    try:
        with open(config.local_cve_file, "r", encoding='utf-8') as fl:
            data = json.load(fl)
        for i in data['vulnerabilities']:
            try:
                cve_id = f"⚠️ New CVE: {i['cve']['id']} ⚠️\n"
                description = f"{i['cve']['descriptions'][0]['value']}\n"
                severity = f"{i['cve']['metrics']['cvssMetricV2'][0]['baseSeverity']} - "
                score = f"{i['cve']['metrics']['cvssMetricV31'][0]['cvssData']['baseScore']}\n\n"
                references = "\n".join(j['url'] for j in i['cve']['references'])
                cves.append(f"{cve_id}\n{severity} - {score}\n{description}\n\n{references}")
            except Exception as error:
                logging.error(f"Error parsing CVE item: {error}")
                continue
        return cves
    except FileNotFoundError:
        logging.error("CVE file not found.")
    except Exception as e:
        logging.error(f"Error in parse_cve_file: {e}")
    return cves

def fetch_and_compare_vulnerabilities(url, local_file):
    new_items = []
    try:
        response = requests.get(url)
        response.raise_for_status()
        latest_data = response.json()

        if os.path.exists(local_file):
            with open(local_file, 'r') as file:
                local_data = json.load(file)
        else:
            local_data = {}

        for item in latest_data.get('vulnerabilities', []):
            if item not in local_data.get('vulnerabilities', []):
                new_items.append(item)

        with open(local_file, 'w') as file:
            json.dump(latest_data, file, indent=4)

    except requests.RequestException as e:
        logging.error(f"Error while fetching data from URL: {url}, Error: {e}")
    except Exception as e:
        logging.error(f"Error in fetch_and_compare_vulnerabilities: {e}")
    return new_items

class DataFetcher:
    def __init__(self, url, local_file, chat_id, bot_token):
        self.url = url
        self.local_file = local_file
        self.chat_id = chat_id
        self.bot_token = bot_token
        self.bot = telegram.Bot(bot_token)
        self.indexed_items = set()

    def download_initial_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            initial_data = response.json()
            self.indexed_items.update(item['post_title'] for item in initial_data)
            with open(self.local_file, 'w') as file:
                json.dump(initial_data, file)
        except requests.RequestException as e:
            logging.error(f"Error downloading initial data: {e}")
            self.send_error_alert(f"Error downloading initial data:\n{e}")

    def fetch_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching data: {e}")
            self.send_error_alert(f"Failed to fetch JSON file:\n{e}")
            return None

    def read_local_data(self):
        if os.path.exists(self.local_file):
            with open(self.local_file, 'r') as file:
                return json.load(file)
        return []

    def index_data(self, data):
        new_items = []
        for item in data:
            item_id = item.get('post_title')
            if item_id and item_id not in self.indexed_items:
                self.indexed_items.add(item_id)
                new_items.append(item)
        return new_items

    def update_local_data(self, data):
        with open(self.local_file, 'w') as file:
            json.dump(data, file)

    def get_new_items(self):
        web_data = self.fetch_data()
        if web_data is None:
            return []

        local_data = self.read_local_data()
        new_items = self.index_data(web_data)
        if new_items:
            self.update_local_data(local_data + new_items)
        return new_items

    def send_error_alert(self, message):
        self.bot.sendMessage(self.chat_id, f"❌ Error:\n{message}")

if __name__ == '__main__':
    monitor = DataFetcher(
        url=config.monitor_url,
        local_file=config.local_ransomware_file,
        chat_id=config.telegram_chat_id,
        bot_token=config.telegram_bot_token
    )

    first_run = True
    checked_cves = False

    while True:
        try:
            now = datetime.datetime.now()
            right_now = f"{now.hour}h{now.minute}"
            
            if first_run:
                monitor.download_initial_data()
                first_run = False
                sleep(config.sleep_interval)
                continue
                
            if now.hour == 0:
                checked_cves = False

            if right_now in config.check_intervals and not checked_cves:
                download_cve_feed()
                for msg in parse_cve_file():
                    monitor.bot.sendMessage(monitor.chat_id, msg)
                    sleep(30)
                checked_cves = True

            for i in monitor.get_new_items():
                msg = '❗️ Ransomware Alert ❗️\nPost: "{0}"\nGroup: {1}\nIdentified on: {2}'.format(i['post_title'], i['group_name'], i['discovered'].split(" ")[0])
                monitor.bot.sendMessage(monitor.chat_id, msg)
                sleep(30)
            logging.info(f"{len(monitor.indexed_items)} cases indexed and reported.")
            
            for i in fetch_and_compare_vulnerabilities(config.cisa_url, config.local_cisa_file):
                msg = '🚨 Exploitation in the Wild! 🚨\nID: {0}\n{1}\nSuggestion: {2}'.format(i['cveID'], i['shortDescription'], i['requiredAction'])
                monitor.bot.sendMessage(monitor.chat_id, msg)
                sleep(30)
            logging.info("CISA alerts checked.")

            sleep(config.sleep_interval)
        except Exception as error:
            logging.error(f"An error occurred in main loop: {error}")
            monitor.send_error_alert(f"An unidentified error occurred:\n{error}")
            sleep(15)
