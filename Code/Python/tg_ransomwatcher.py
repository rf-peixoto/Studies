import requests
import json
import telegram
from time import sleep
import os

class DataFetcher:
    def __init__(self, url, local_file):
        self.url = url
        self.local_file = local_file
        self.indexed_items = set()

    def download_initial_data(self):
        response = requests.get(self.url)
        if response.status_code == 200:
            with open(self.local_file, 'w') as file:
                json.dump(response.json(), file)

    def fetch_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching data: {e}")
            return []

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
        local_data = self.read_local_data()
        new_items = self.index_data(web_data)
        if new_items:
            self.update_local_data(web_data)
        return new_items

# Define monitor:
monitor = DataFetcher("https://raw.githubusercontent.com/joshhighet/ransomwatch/main/posts.json", "local_data.json")
bot = telegram.Bot("TOKEN")

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
                bot.sendMessage("CHANNEL", msg)
                sleep(30)
            print("{0} cases indexed and reported.".format(len(monitor.indexed_items)))
            sleep(1800)
        except Exception as error:
            print(error)
            sleep(15)
