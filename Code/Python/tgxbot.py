import tweepy
import time
import asyncio
import json
from rich.console import Console
from rich.text import Text
from telegram import Bot

# Set up rich console
console = Console()

# Twitter API credentials
BEARER_TOKEN = "YOUR_BEARER_TOKEN"

# Telegram Bot credentials
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_GROUP_CHAT_ID"

# User to track
TARGET_USERNAME = "TARGET_USERNAME"

# Check interval (in seconds)
CHECK_INTERVAL = 1800  # 30 minutes

# JSON file to store seen posts
SEEN_POSTS_FILE = "{0}_posts.json".format(TARGET_USERNAME)

# Authenticate with Twitter API v2
client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Initialize Telegram Bot
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Function to load seen posts from JSON file
def load_seen_posts():
    try:
        with open(SEEN_POSTS_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Function to save seen posts to JSON file
def save_seen_posts(seen_posts):
    with open(SEEN_POSTS_FILE, "w") as file:
        json.dump(seen_posts, file, indent=4)

# Function to fetch all posts from a user
def get_all_posts(username, max_results=10):
    try:
        user = client.get_user(username=username)
        if user.data is None:
            console.print(Text(f"Error: User @{username} not found.", style="bold red"))
            return []

        user_id = user.data.id

        # Fetch recent tweets and replies
        tweets = client.get_users_tweets(
            user_id, max_results=max_results, tweet_fields=["created_at", "text", "conversation_id"]
        )
        return tweets.data if tweets and tweets.data else []
    except tweepy.errors.TweepyException as e:
        console.print(Text(f"Error: {e}", style="bold red"))
        return []

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

    # Load seen posts from JSON
    seen_posts = load_seen_posts()

    while True:
        console.print(Text(f"Checking for new posts from @{TARGET_USERNAME}...", style="cyan"))
        tweets = get_all_posts(TARGET_USERNAME)

        new_posts = []
        for tweet in tweets:
            if str(tweet.id) not in seen_posts:
                new_posts.append(tweet)
                seen_posts[str(tweet.id)] = {
                    "text": tweet.text,
                    "created_at": str(tweet.created_at),
                }

        if new_posts:
            for post in new_posts:
                console.print(Text("New Post Found!", style="bold green"))
                console.print(Text(f"Posted at: {post.created_at}", style="yellow"))
                console.print(Text(f"Content: {post.text}", style="bold white"))
                console.print(Text(f"URL: https://twitter.com/{TARGET_USERNAME}/status/{post.id}", style="magenta"))

                # Send formatted post to Telegram
                telegram_message = format_tweet_for_telegram(post)
                await send_telegram_message(telegram_message)

            # Save updated seen posts to JSON
            save_seen_posts(seen_posts)
        else:
            console.print(Text("No new posts.", style="bold yellow"))

        await asyncio.sleep(CHECK_INTERVAL)

# Entry point for asynchronous execution
if __name__ == "__main__":
    asyncio.run(main())
