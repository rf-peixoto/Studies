# pip install python-telegram-bot==3.1.0
# pip install python-dotenv

from dotenv import load_dotenv # or load_dotenv('/full/path/to/.env')
from time import sleep
import telegram, os

# Load .env vars:
load_dotenv()

# SETUP
# There is no API token hardcoded. You must create a .env file
# and create a line TG_TOKEN=YOURAPITOKEN

authorized = [USERID,USERID]
bot = telegram.Bot(token=os.getenv('TG_TOKEN'))

# Get raw updates from API:
def get_updates() -> list:
    return bot.getUpdates()

# Convert one update into json:
def parse_update(update) -> list:
    chatid = update.message.chat_id
    txt = update.message.text
    sender_id = update.message.from_user.id
    username = update.message.from_user.username
    return [chatid, txt, sender_id, username]

# Proccess data on message:
def process_message(data: list):
    # Check if user is allowed to call this bot:
    if data[0] in authorized:
        # Ping:
        if data[1].startswith("%ping"):
            bot.sendMessage(data[0], "200")

        # Command A

# Run:
if __name__ == '__main__':
    updates_received = []
    try:
        while True:
            # Read new updates
            new_updates = get_updates()
            for up in new_updates:
                if up.update_id not in updates_received:
                    process_message(parse_update(up))
                    updates_received.append(up.update_id)
            sleep(5)
    except KeyboardInterrupt:
        pass
