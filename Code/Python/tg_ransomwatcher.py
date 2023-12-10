import requests
import json
import telegram
import logging
from time import sleep
import os

# Configure logging
logging.basicConfig(filename='app.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

class DataFetcher:
    def __init__(self, url, local_file, chat_id, bot_token):
        self.url = url
        self.local_file = local_file
        self.indexed_items = set()
        self.chat_id = chat_id
        self.bot_token = bot_token
        self.bot = telegram.Bot(bot_token)

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
            self.send_error_alert(f"Error downloading initial data: {e}")

    def fetch_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching data: {e}")
            self.send_error_alert(f"Error fetching data: {e}")
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
        self.bot.sendMessage(self.chat_id, f"❌ Error Alert: {message}")

# Define monitor:
monitor = DataFetcher(
    url="https://raw.githubusercontent.com/joshhighet/ransomwatch/main/posts.json",
    local_file="local_data.json",
    chat_id="YOUR_CHAT_ID",
    bot_token="YOUR_TOKEN"
)

# Run:
if __name__ == '__main__':
    first_run = True
    while True:
        try:
            if first_run:
                monitor.download_initial_data()
                first_run = False
                sleep(1800)  # Wait for 30 minutes before the next run
                continue

            # Fetch new items:
            for i in monitor.get_new_items():
                msg = '❗️ Alerta de Ransomware ❗️\nPost: "{0}"\nGrupo: {1}\nIdentificado em: {2}'.format(i['post_title'], i['group_name'], i['discovered'].split(" ")[0])
                monitor.bot.sendMessage(monitor.chat_id, msg)
                sleep(30)
            logging.info("{0} cases indexed and reported.".format(len(monitor.indexed_items)))
            sleep(1800)
        except Exception as error:
            logging.error(f"An error occurred: {error}")
            monitor.send_error_alert(f"An error occurred: {error}")
            sleep(15)
