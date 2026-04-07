#!/usr/bin/env python3
"""
Extract account information from a Telethon .session file.
Usage: python session_info.py <session_file> [--api-id ID] [--api-hash HASH]
"""

import os
import sys
import argparse
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, ApiIdInvalidError

def get_api_credentials(api_id, api_hash):
    """Get API ID and hash from arguments, env vars, or user input."""
    if not api_id:
        api_id = os.environ.get("TG_API_ID")
    if not api_hash:
        api_hash = os.environ.get("TG_API_HASH")

    if not api_id:
        api_id = input("Enter your API ID (from my.telegram.org): ").strip()
    if not api_hash:
        api_hash = input("Enter your API hash: ").strip()

    try:
        api_id = int(api_id)
    except ValueError:
        print("Error: API ID must be an integer.")
        sys.exit(1)

    return api_id, api_hash

def main():
    parser = argparse.ArgumentParser(description="Show account info from a Telethon .session file")
    parser.add_argument("session_file", help="Path to the .session file")
    parser.add_argument("--api-id", type=int, help="Telegram API ID")
    parser.add_argument("--api-hash", help="Telegram API hash")
    args = parser.parse_args()

    session_path = args.session_file
    if not os.path.isfile(session_path):
        print(f"Error: Session file '{session_path}' not found.")
        sys.exit(1)

    # Remove .session extension if present (Telethon expects base name)
    base_name = session_path
    if base_name.endswith(".session"):
        base_name = base_name[:-8]

    api_id, api_hash = get_api_credentials(args.api_id, args.api_hash)

    # Create client (we won't send any messages, just connect)
    client = TelegramClient(base_name, api_id, api_hash)

    async def get_info():
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("Session is not authorized. You may need to re-login.")
                print("This script only reads existing sessions; it cannot re-authenticate.")
                return

            me = await client.get_me()
            print("\n" + "=" * 40)
            print("Account Information:")
            print("=" * 40)
            print(f"User ID:       {me.id}")
            print(f"First Name:    {me.first_name or ''}")
            print(f"Last Name:     {me.last_name or ''}")
            print(f"Username:      @{me.username}" if me.username else "Username:      (none)")
            if not me.bot:
                print(f"Phone Number:  {me.phone}")
            else:
                print("Phone Number:  (bot account)")
            print(f"Is Bot:        {me.bot}")
            print("=" * 40)
        except ApiIdInvalidError:
            print("Error: Invalid API ID or hash. Please double-check your credentials.")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            await client.disconnect()

    import asyncio
    asyncio.run(get_info())

if __name__ == "__main__":
    main()