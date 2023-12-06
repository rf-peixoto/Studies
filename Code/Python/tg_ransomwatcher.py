import requests
import json
import telegram
from time import sleep

class DataFetcher:
    def __init__(self, url):
        self.url = url
        self.indexed_items = set()

    def fetch_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching data: {e}")
            return []

    def index_data(self):
        new_items = []
        data = self.fetch_data()

        for item in data:
            item_id = item.get('post_title')
            if item_id and item_id not in self.indexed_items:
                self.indexed_items.add(item_id)
                new_items.append(item)

        return new_items

    def get_new_items(self):
        new_items = self.index_data()
        return new_items

# Define monitor:
monitor = DataFetcher("https://raw.githubusercontent.com/joshhighet/ransomwatch/main/posts.json")
bot = telegram.Bot("TG TOKEN")

# Run:
if __name__ == '__main__':
    while True:
        try:
            # Fetch new itens:
            for i in monitor.get_new_items():
                msg = '❗️ Alerta de Ransomware ❗️\nPost: "{0}"\nGrupo: {1}\nIdentificado em: {2}'.format(i['post_title'], i['group_name'], i['discovered'].split(" ")[0])
                bot.sendMessage("CHANNEL or PROFILE ID", msg)
                sleep(30)
            print("{0} cases indexed and reported.".format(len(monitor.indexed_items)))
            sleep(3600)
        except Exception as error:
            print(error)
            sleep(15)
