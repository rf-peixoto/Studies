# This code was made by Yellow at https://onniforums.com/Thread-HIDE-YOUR-TELEGRAM-REAL-ACCOUNT

from pyrogram import Client, filters

# generate api_id and api_hash from https://my.telegram.org/apps
# if you can't, you can find it somewhere :)
API_ID = 0
API_HASH = ""

# generate bot token from @BotFather
BOT_TOKEN = ""

app = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN)

CHAT_ID = 0 # must be numeric only

user_reply_info = {}

@app.on_message(filters.private)
async def forward_to_group(client, message):
    forwarded = await client.forward_messages(chat_id=CHAT_ID, from_chat_id=message.chat.id, message_ids=message.id)
    user_reply_info[forwarded.id] = (message.chat.id, message.id)

@app.on_message(filters.chat(CHAT_ID) & filters.reply)
async def handle_group_reply(client, message):
    if message.reply_to_message.id in user_reply_info:
        orig_chat_id, orig_msg_id = user_reply_info[message.reply_to_message.id]
        await client.send_message(chat_id=orig_chat_id, text=message.text, reply_to_message_id=orig_msg_id)

app.run()
