import random
import string
import curses
import time
from collections import defaultdict
import csv

# Parameters (configurable)
GRID_WIDTH = 64
GRID_HEIGHT = 20
NUM_REGIONS = 4
CONNECTION_PROBABILITY = 0.3
NUM_USERS = 100
INITIAL_CONNECTIONS = 5
MEME_TTL = 10
TURN_DURATION = 0.01  # Seconds each turn lasts
THEMES = ['politics', 'technology', 'sports', 'entertainment', 'music', 'cinema', 'influencers', 'shitpost', 'business', 'social media']
EVOLUTION_CHANCE = 0.05
LIFESPAN_DECREASE = 1
SPECIAL_EVENT_PROBABILITY = 0.1
NUM_TURNS = 1000
CSV_FILENAME = "simulation_stats.csv"

# Define data structures
class Meme:
    def __init__(self, creator_id, content):
        self.id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        self.creator_id = creator_id
        self.content = content
        self.likes = 0
        self.shares = 0
        self.ttl = MEME_TTL
        self.version_history = [(creator_id, content, None)]

    def update_version(self, user_id, content):
        self.ttl = MEME_TTL
        self.likes = 0
        self.shares = 0
        self.version_history.append((self.creator_id, self.content, user_id))
        self.creator_id = user_id
        self.content = content

class User:
    def __init__(self, user_id):
        self.id = user_id
        self.connections = set()
        self.liked_themes = {theme: random.uniform(0, 1) for theme in THEMES}
        self.position = (random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1))
        self.memes_shared = set()

    def add_connection(self, user):
        self.connections.add(user.id)

    def remove_connection(self, user):
        self.connections.discard(user.id)

    def like_meme(self, meme):
        if random.random() < self.liked_themes[meme.content]:
            meme.likes += 1
            return True
        return False

    def evolve_preferences(self):
        for theme in THEMES:
            if random.random() < EVOLUTION_CHANCE:
                self.liked_themes[theme] = random.uniform(0, 1)

    def move(self):
        x, y = self.position
        dx = random.choice([-1, 0, 1])
        dy = random.choice([-1, 0, 1])
        new_x = max(0, min(GRID_WIDTH - 1, x + dx))
        new_y = max(0, min(GRID_HEIGHT - 1, y + dy))
        self.position = (new_x, new_y)

# Helper functions
def initialize_users(num_users):
    users = [User(user_id) for user_id in range(num_users)]
    for user in users:
        potential_connections = [u for u in users if u.id != user.id]
        for _ in range(INITIAL_CONNECTIONS):
            if potential_connections:
                conn_user = random.choice(potential_connections)
                user.add_connection(conn_user)
                conn_user.add_connection(user)
                potential_connections.remove(conn_user)
    return users

def initialize_memes(users):
    memes = []
    for user in users:
        content = random.choice(THEMES)
        meme = Meme(user.id, content)
        memes.append(meme)
        user.memes_shared.add(meme.id)
    return memes

def update_grid(grid, users, memes):
    # Clear grid
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            grid[y][x] = '.'
    
    # Place users on the grid
    for user in users:
        x, y = user.position
        grid[y][x] = 'U'
    
    # Place memes on the grid (indicating meme sharing activity)
    for meme in memes:
        if meme.ttl > 0:
            for user in users:
                if meme.id in user.memes_shared:
                    x, y = user.position
                    if grid[y][x] == 'U':
                        grid[y][x] = 'U+M'
                    else:
                        grid[y][x] = 'M'
    
    return grid

def display_screen(stdscr, grid, turn, memes, users):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    # Initialize color pairs
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    # Display grid
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            if grid[y][x] == 'U':
                stdscr.addch(y, x, 'U', curses.color_pair(1))
            elif grid[y][x] == 'M':
                stdscr.addch(y, x, 'M', curses.color_pair(2))
            elif grid[y][x] == 'U+M':
                stdscr.addch(y, x, 'M', curses.color_pair(3))  # Mixed color for both
            else:
                stdscr.addch(y, x, '.')
    
    # Display analytics
    stdscr.addstr(GRID_HEIGHT + 1, 0, f"Turn {turn + 1}")
    stdscr.addstr(GRID_HEIGHT + 2, 0, "Meme Analytics:")
    for idx, meme in enumerate(memes[:10]):  # Display top 10 memes for brevity
        stdscr.addstr(GRID_HEIGHT + 3 + idx, 0, f"Meme ID: {meme.id}, Content: {meme.content}, Likes: {meme.likes}, Shares: {meme.shares}, TTL: {meme.ttl}")
    
    stdscr.refresh()

def generate_csv(memes, users):
    with open(CSV_FILENAME, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Meme ID', 'Creator ID', 'Content', 'Likes', 'Shares', 'TTL', 'Version History'])
        for meme in memes:
            version_history_str = ' | '.join([f"({creator_id}, {content}, {user_id})" for creator_id, content, user_id in meme.version_history])
            writer.writerow([meme.id, meme.creator_id, meme.content, meme.likes, meme.shares, meme.ttl, version_history_str])
        
        writer.writerow([])
        writer.writerow(['User ID', 'Position', 'Memes Shared', 'Connections'])
        for user in users:
            memes_shared_str = ', '.join(user.memes_shared)
            connections_str = ', '.join(map(str, user.connections))
            writer.writerow([user.id, user.position, memes_shared_str, connections_str])

def run_simulation(stdscr, users, memes):
    grid = [['.' for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    
    for turn in range(NUM_TURNS):
        # User actions
        for user in users:
            if random.random() < SPECIAL_EVENT_PROBABILITY:
                content = random.choice(THEMES)
                meme = Meme(user.id, content)
                memes.append(meme)
                user.memes_shared.add(meme.id)
            
            user.evolve_preferences()
            user.move()
            
            for meme in memes:
                if meme.ttl > 0:
                    meme.ttl -= LIFESPAN_DECREASE
                    if meme.ttl <= 0:
                        memes.remove(meme)
                
                for conn_id in user.connections:
                    connected_user = next((u for u in users if u.id == conn_id), None)
                    if connected_user and connected_user.like_meme(meme):
                        meme.shares += 1
                        if random.random() < 0.1:
                            new_content = random.choice(THEMES)
                            meme.update_version(user.id, new_content)
                            connected_user.memes_shared.add(meme.id)
        
        update_grid(grid, users, memes)
        display_screen(stdscr, grid, turn, memes, users)
        time.sleep(TURN_DURATION)  # Wait for the duration of each turn

    generate_csv(memes, users)

if __name__ == "__main__":
    users = initialize_users(NUM_USERS)
    memes = initialize_memes(users)
    curses.wrapper(run_simulation, users, memes)
