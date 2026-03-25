from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

# ===== CONFIG =====
api_id = 01234        # from my.telegram.org
api_hash = "HASH"
session_name = "session"

OUTPUT_FILE = "telegram_chats.json"
# ==================

import json

async def main():
    chats_data = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        chat_type = "unknown"
        if isinstance(entity, Channel):
            if entity.broadcast:
                chat_type = "channel"
            else:
                chat_type = "supergroup"
        elif isinstance(entity, Chat):
            chat_type = "group"
        else:
            chat_type = "private"

        chats_data.append({
            "name": dialog.name,
            "id": entity.id,
            "username": getattr(entity, "username", None),
            "type": chat_type
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(chats_data, f, indent=2, ensure_ascii=False)

    print(f"[+] Exported {len(chats_data)} chats")

client = TelegramClient(session_name, api_id, api_hash)

with client:
    client.loop.run_until_complete(main())
