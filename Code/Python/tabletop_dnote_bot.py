import discord
import os
import random
import asyncio

# Replace with your own values
BOT_TOKEN = "YOUR_BOT_TOKEN"
GAME_MASTER_ID = 123456789012345678  # Replace with the Game Master's Discord user ID
PDF_PATH = "path/to/file.pdf"  # Local path to the PDF to send to Kira
KIRA_DATA_FILE = "data.txt"    # Local file for storing Kira's ID

# Intents and client setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

# Global variables
kira_id = None

def load_kira_data():
    global kira_id
    if os.path.exists(KIRA_DATA_FILE):
        with open(KIRA_DATA_FILE, "r") as file:
            stored_id = file.read().strip()
            if stored_id.isdigit():
                kira_id = int(stored_id)

def save_kira_data(kira_id_to_save):
    with open(KIRA_DATA_FILE, "w") as file:
        file.write(str(kira_id_to_save))

async def choose_kira():
    global kira_id
    guilds = client.guilds
    if not guilds:
        return  # Bot must be in at least one guild

    # Assuming the bot’s functionality is limited to the first guild in the list
    # Adjust if you need to support multiple guilds or different selection logic
    guild = guilds[0]
    members = await guild.fetch_members().flatten()

    # Filter out the Game Master and the bot itself
    valid_players = [
        member
        for member in members
        if (member.id != GAME_MASTER_ID and not member.bot)
    ]

    if not valid_players:
        return

    # Randomly choose Kira
    kira_member = random.choice(valid_players)
    kira_id = kira_member.id
    save_kira_data(kira_id)

    # Send the Kira pdf and a confirmation message via DM
    try:
        kira_dm = await kira_member.create_dm()
        await kira_dm.send(
            content="You have been chosen as Kira. The attached file contains important information."
        )
        await kira_dm.send(file=discord.File(PDF_PATH))
    except Exception:
        pass

@client.event
async def on_ready():
    # Load Kira from file if it exists
    load_kira_data()

    # If Kira is not chosen yet, choose now
    if kira_id is None:
        await choose_kira()

    print(f"Bot is ready. Logged in as {client.user} (ID: {client.user.id})")

@client.event
async def on_message(message):
    global kira_id

    # Ignore messages from the bot itself
    if message.author.id == client.user.id:
        return

    # Check if the message is a DM
    if isinstance(message.channel, discord.DMChannel):
        # If the author is the Game Master
        if message.author.id == GAME_MASTER_ID:
            # Check if the message is a command (starting with '%')
            if message.content.startswith("%"):
                command_parts = message.content[1:].split()
                if len(command_parts) > 0:
                    command = command_parts[0].lower()

                    if command == "reroll":
                        # Re-roll Kira
                        kira_id = None
                        await choose_kira()
                        await message.channel.send("A new Kira has been selected.")
                return

            # Forward the GM message to Kira
            if kira_id:
                kira_member = await client.fetch_user(kira_id)
                try:
                    kira_dm = await kira_member.create_dm()
                    await kira_dm.send(f"Game Master says: {message.content}")
                except Exception:
                    pass

        # If the author is Kira
        elif message.author.id == kira_id:
            # Forward the Kira message to the Game Master
            gm_member = await client.fetch_user(GAME_MASTER_ID)
            try:
                gm_dm = await gm_member.create_dm()
                await gm_dm.send(f"Kira says: {message.content}")
            except Exception:
                pass

# Run the bot
client.run(BOT_TOKEN)
