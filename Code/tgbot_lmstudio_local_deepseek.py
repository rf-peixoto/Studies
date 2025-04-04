import asyncio
import logging
import re
import aiohttp

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Configuration Variables ---
BOT_TOKEN = "YOUR_BOT_TOKEN"              # Replace with your bot token.
ALLOWED_GROUP_ID = -10000000000           # Replace with your allowed group ID.
LM_API_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "deepseek-r1-distill-qwen-7b"

# Global variable to store the bot's username.
BOT_USERNAME = None

# In-memory message queue.
message_queue = asyncio.Queue()

# Global dictionary to record groups the bot sees.
GROUPS = {}  # Maps chat id to chat title


def sanitize(text: str) -> str:
    """
    Remove emojis and special characters by keeping only ASCII characters.
    """
    return text.encode("ascii", errors="ignore").decode("ascii")


def remove_think_block(text: str) -> str:
    """
    Remove any text enclosed in <think>...</think> blocks.
    """
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


async def call_model_api(prompt: str) -> str:
    """
    Call the LM Studio API with the given prompt and return the processed response.
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "Be formal, do not use emojis or slangs."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": -1,
        "stream": False
    }
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(LM_API_URL, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return remove_think_block(content)
            else:
                logging.error(f"LM API returned status {response.status}")
                return "Error: Model API request failed."


async def process_queue(app: Application):
    """
    Process messages from the queue sequentially.
    """
    while True:
        update, prompt, sender_username = await message_queue.get()
        try:
            response_text = await call_model_api(prompt)
            if sender_username:
                reply_message = f"@{sender_username} {response_text}"
            else:
                reply_message = response_text
            await update.message.reply_text(reply_message)
            logging.info(f"Replied to message {update.message.message_id} in chat {update.effective_chat.id}")
        except Exception as e:
            logging.error(f"Error processing queue: {e}")
        message_queue.task_done()


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming messages from group chats.
    """
    global BOT_USERNAME, GROUPS

    # Only process messages from group or supergroup chats.
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    # Record group information.
    GROUPS[update.effective_chat.id] = update.effective_chat.title
    logging.info(f"Received message from group: '{update.effective_chat.title}' (ID: {update.effective_chat.id})")

    # Process only messages from the allowed group.
    if update.effective_chat.id != ALLOWED_GROUP_ID:
        return

    if not update.message or not update.message.text:
        return

    text = update.message.text
    sanitized_text = sanitize(text)
    logging.info(f"Message {update.message.message_id}: {sanitized_text}")

    # Diagnostic command: reply immediately if the message is exactly "/ping".
    if sanitized_text.strip() == "/ping":
        sender_username = update.message.from_user.username
        diag_reply = f"@{sender_username} Pong. Bot is active and listening." if sender_username else "Pong. Bot is active and listening."
        await update.message.reply_text(diag_reply)
        logging.info(f"Sent diagnostic reply for message {update.message.message_id}")
        return

    # Process only if the bot is mentioned.
    if BOT_USERNAME is None or f"@{BOT_USERNAME}" not in text:
        logging.info("Message does not contain bot mention; ignoring.")
        return

    # Check for an attached document (text file).
    if update.message.document:
        document = update.message.document
        if document.mime_type == "text/plain" and document.file_size <= 5 * 1024 * 1024:
            try:
                file = await document.get_file()
                file_bytes = await file.download_as_bytearray()
                file_text = file_bytes.decode("utf-8", errors="ignore")
                sanitized_text += "\nFile content:\n" + file_text
                logging.info(f"Appended file content from document {document.file_id}")
            except Exception as e:
                logging.error(f"Error processing file: {e}")
        else:
            logging.info("Attached document is not a valid text file or exceeds 5MB.")

    sender_username = update.message.from_user.username
    await message_queue.put((update, sanitized_text, sender_username))
    logging.info(f"Message {update.message.message_id} enqueued for processing.")


async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reply with the list of known groups (group title and ID) that the bot has recorded.
    """
    if not GROUPS:
        await update.message.reply_text("No groups recorded yet.")
        return

    message_lines = ["Known groups:"]
    for chat_id, title in GROUPS.items():
        message_lines.append(f"{title} (ID: {chat_id})")
    await update.message.reply_text("\n".join(message_lines))
    logging.info("Replied with the list of known groups.")


async def post_init(app: Application):
    """
    Post-initialization callback: set bot's username, send startup message,
    and start the background task.
    """
    global BOT_USERNAME
    bot_me = await app.bot.get_me()
    BOT_USERNAME = bot_me.username
    logging.info(f"Bot username: {BOT_USERNAME}")

    # Send a startup message to the allowed group.
    try:
        startup_message = f"Bot {BOT_USERNAME} has started and is active."
        await app.bot.send_message(ALLOWED_GROUP_ID, startup_message)
        logging.info(f"Sent startup message to group ID {ALLOWED_GROUP_ID}")
    except Exception as e:
        logging.error(f"Failed to send startup message: {e}")

    # Start the background processing task.
    app.create_task(process_queue(app))


def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register handlers.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CommandHandler("listgroups", list_groups))

    # Start polling (this call blocks until the bot is stopped).
    app.run_polling()


if __name__ == '__main__':
    main()
