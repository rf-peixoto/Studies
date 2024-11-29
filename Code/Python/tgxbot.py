import tweepy
import time
import asyncio
from rich.console import Console
from rich.text import Text
from telegram import Bot

# Set up rich console
console = Console()

# Twitter API credentials
BEARER_TOKEN = "BEARER"

# Telegram Bot credentials
TELEGRAM_BOT_TOKEN = "Telegram Token"
TELEGRAM_CHAT_ID = -000000000 # Telegram Group ID to notify

# User to track
TARGET_USERNAME = "USERNAME" # Username to monitor

# Check interval (in seconds)
CHECK_INTERVAL = 3600 # 30 minutes

# Authenticate with Twitter API v2
client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Initialize Telegram Bot
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Function to fetch the latest tweet from a user
def get_latest_tweet(username):
    try:
        # Fetch user ID
        user = client.get_user(username=username)
        if user.data is None:
            console.print(Text(f"Error: User @{username} not found.", style="bold red"))
            return None

        user_id = user.data.id

        # Fetch recent tweets
        tweets = client.get_users_tweets(user_id, max_results=5, tweet_fields=["created_at", "text"])
        if tweets.data:
            return tweets.data[0]  # Return the latest tweet
        return None
    except tweepy.errors.TweepyException as e:
        console.print(Text(f"Error: {e}", style="bold red"))
        return None

# Asynchronous function to send message to Telegram group
async def send_telegram_message(message):
    try:
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="HTML")
    except Exception as e:
        console.print(Text(f"Telegram Error: {e}", style="bold red"))

# Function to format tweet for Telegram
def format_tweet_for_telegram(tweet):
    tweet_url = f"https://twitter.com/{TARGET_USERNAME}/status/{tweet.id}"
    return (
        f"<b>New Post Found!</b>\n"
        f"<b>Author:</b> @{TARGET_USERNAME}\n"
        f"<b>Posted at:</b> {tweet.created_at}\n\n"
        f"{tweet.text}\n\n"
        f"<a href='{tweet_url}'>View Tweet</a>"
    )

# Main function
async def main():
    console.print(Text("Twitter Bot Started", style="bold green"))
    last_seen_tweet_id = None

    while True:
        console.print(Text(f"Checking for new posts from @{TARGET_USERNAME}...", style="cyan"))
        tweet = get_latest_tweet(TARGET_USERNAME)

        if tweet:
            if last_seen_tweet_id is None or tweet.id != last_seen_tweet_id:
                last_seen_tweet_id = tweet.id
                console.print(Text("New Post Found!", style="bold green"))
                console.print(Text(f"Posted at: {tweet.created_at}", style="yellow"))
                console.print(Text(f"Content: {tweet.text}", style="bold white"))
                console.print(Text(f"URL: https://twitter.com/{TARGET_USERNAME}/status/{tweet.id}", style="magenta"))

                # Send formatted tweet to Telegram
                telegram_message = format_tweet_for_telegram(tweet)
                await send_telegram_message(telegram_message)
            else:
                console.print(Text("No new posts.", style="bold yellow"))
        else:
            console.print(Text("Could not retrieve tweets.", style="bold red"))
        
        await asyncio.sleep(CHECK_INTERVAL)

# Entry point for asynchronous execution
if __name__ == "__main__":
    asyncio.run(main())
