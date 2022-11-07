import discord

# Credentials:
token = "Bot Secret Token"
owner_id = "Admin Discord ID"

# Proxy setup:
class Proxy:
    def __init__(self):
        self.endpoint = None

proxy = Proxy()

# Start client:
client = discord.Client()

# --------------------------------------------------------------------------- #
# On Message:
# --------------------------------------------------------------------------- #
@client.event
async def on_message(message):
    # Ignore self and bot messages:
    if message.author == client.user or message.author.bot:
        return

    # Update endpoint channel:
    if str(message.channel.type) != "private" and message.content.startswith("!spawn"):
        if proxy.endpoint == None:
            proxy.endpoint = message.channel
            await message.add_reaction("\u2611")
        else:
            print("{0} tried to spawn your proxy at [{1} | {2}]".format(message.author.name, message.guild, message.channel))

    # Command Center:
    if str(message.channel.type) == "private" and str(message.author.id) == owner_id:
        if message.content.startswith("!say"):
            tmp = message.content.split("!say ")[-1]
            await proxy.endpoint.trigger_typing()
            await proxy.endpoint.send(tmp)

# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
client.run(token)
