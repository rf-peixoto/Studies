import random
import curses
import heapq
import time

# Configuration variables
WIDTH = 50
HEIGHT = 50
CHUNK_SIZE = 20
SCREEN_SIZE = 20
REFRESH_RATE = 100  # Time in milliseconds
NUM_ITEMS = 10
NUM_MONSTERS = 5  # Number of monsters
SPAWN_INTERVAL = 5  # Time interval in seconds to spawn new items
POWER_UP_SPAWN_INTERVAL = 30  # Time interval in seconds to spawn power-ups
POWER_UP_DURATION = 15  # Duration of power-up effects in seconds
PLAYER_CHAR = '@'
ITEM_CHAR = 'I'
MONSTER_CHAR = 'M'
POWER_UP_CHAR = 'P'  # Display as a different color for differentiation
WALL_CHAR = '#'
PATH_CHAR = '.'
MONSTER_NEAR_THRESHOLD = 10  # Distance within which the player flees from monsters

# Random names for players
PLAYER_NAMES = ["Alex", "Blake", "Casey", "Drew", "Elliot", "Frankie", "Glen", "Harper", "Jesse", "Kai"]

# Power-up effects
POWER_UPS = ["Speed", "Extra Life", "Double"]

class Maze:
    def __init__(self, width, height, chunk_size, num_items):
        self.width = width
        self.height = height
        self.chunk_size = chunk_size
        self.num_items = num_items
        self.maze = [[1 for _ in range(width)] for _ in range(height)]
        self.items = []
        self.power_ups = []
        self.generate_maze()
        self.spawn_items()

    def generate_maze(self):
        stack = [(1, 1)]
        self.maze[1][1] = 0

        while stack:
            x, y = stack[-1]
            neighbors = self.get_neighbors(x, y)

            if neighbors:
                nx, ny = random.choice(neighbors)
                self.maze[(x + nx) // 2][(y + ny) // 2] = 0
                self.maze[nx][ny] = 0
                stack.append((nx, ny))
            else:
                stack.pop()

    def get_neighbors(self, x, y):
        neighbors = []

        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            nx, ny = x + dx, y + dy
            if 1 <= nx < self.width - 1 and 1 <= ny < self.height - 1 and self.maze[nx][ny] == 1:
                neighbors.append((nx, ny))

        return neighbors

    def spawn_items(self):
        while len(self.items) < self.num_items:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            if self.maze[x][y] == 0 and (x, y) not in self.items and (x, y) not in self.power_ups:
                self.items.append((x, y))

    def spawn_power_up(self):
        while True:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            if self.maze[x][y] == 0 and (x, y) not in self.items and (x, y) not in self.power_ups:
                self.power_ups.append((x, y, random.choice(POWER_UPS)))
                break

    def spawn_new_item(self, player_chunk_x, player_chunk_y):
        while True:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            chunk_x = x // self.chunk_size
            chunk_y = y // self.chunk_size
            if self.maze[x][y] == 0 and (x, y) not in self.items and (chunk_x, chunk_y) != (player_chunk_x, player_chunk_y):
                self.items.append((x, y))
                break

    def display_chunk(self, stdscr, player_x, player_y, monsters, player_name, player_items, player_turns, high_scores, power_up_effect):
        chunk_x = player_x // self.chunk_size * self.chunk_size
        chunk_y = player_y // self.chunk_size * self.chunk_size

        for y in range(chunk_y, chunk_y + self.chunk_size):
            if 0 <= y < self.height:
                for x in range(chunk_x, chunk_x + self.chunk_size):
                    if 0 <= x < self.width:
                        if (x, y) == (player_x, player_y):
                            stdscr.addch(y - chunk_y, x - chunk_x, PLAYER_CHAR, curses.color_pair(3))
                        elif (x, y) in self.items:
                            stdscr.addch(y - chunk_y, x - chunk_x, ITEM_CHAR, curses.color_pair(4))
                        elif (x, y) in [(m.x, m.y) for m in monsters]:
                            stdscr.addch(y - chunk_y, x - chunk_x, MONSTER_CHAR, curses.color_pair(5))
                        elif (x, y) in [(p[0], p[1]) for p in self.power_ups]:
                            stdscr.addch(y - chunk_y, x - chunk_x, POWER_UP_CHAR, curses.color_pair(6))
                        elif self.maze[x][y] == 0:
                            stdscr.addch(y - chunk_y, x - chunk_x, PATH_CHAR, curses.color_pair(2))
                        else:
                            stdscr.addch(y - chunk_y, x - chunk_x, WALL_CHAR, curses.color_pair(1))

        # Display player's current status
        status_y = 0
        stdscr.addstr(status_y, self.width + 2, f"Player: {player_name}")
        stdscr.addstr(status_y + 1, self.width + 2, f"Items Collected: {player_items}")
        stdscr.addstr(status_y + 2, self.width + 2, f"Turns Survived: {player_turns}")
        stdscr.addstr(status_y + 3, self.width + 2, f"Power-Up: {power_up_effect if power_up_effect else 'None'}")

        # Display high scores
        stdscr.addstr(status_y + 5, self.width + 2, "High Scores:")
        for i, (name, score, turns) in enumerate(high_scores):
            stdscr.addstr(status_y + 6 + i, self.width + 2, f"{i+1}. {name}: {score} items, {turns} turns")

        stdscr.refresh()

class Entity:
    def __init__(self, start_x, start_y):
        self.x = start_x
        self.y = start_y

class Player(Entity):
    def __init__(self, start_x, start_y):
        super().__init__(start_x, start_y)
        self.collected_items = 0
        self.turns_survived = 0
        self.name = random.choice(PLAYER_NAMES)
        self.extra_life = False
        self.double_value_active = False
        self.power_up_end_time = None
        self.power_up_effect = None

    def move(self, path, maze, items, power_ups):
        if path:
            next_pos = path.pop(0)
            self.x, self.y = next_pos
            self.turns_survived += 1
            if (self.x, self.y) in items:
                items.remove((self.x, self.y))
                if self.double_value_active:
                    self.collected_items += 2
                else:
                    self.collected_items += 1
            for power_up in power_ups:
                if (self.x, self.y) == (power_up[0], power_up[1]):
                    self.apply_power_up(power_up[2])
                    power_ups.remove(power_up)

    def apply_power_up(self, effect):
        self.power_up_effect = effect
        if effect == "speed":
            self.power_up_end_time = time.time() + POWER_UP_DURATION
        elif effect == "extra_life":
            self.extra_life = True
            self.power_up_end_time = time.time() + POWER_UP_DURATION  # Ensuring it doesn't stack
        elif effect == "double_value":
            self.double_value_active = True
            self.power_up_end_time = time.time() + POWER_UP_DURATION

    def check_power_up_expiry(self):
        if self.power_up_end_time and time.time() >= self.power_up_end_time:
            self.power_up_end_time = None
            self.power_up_effect = None
            self.double_value_active = False
            self.extra_life = False

    def flee(self, path):
        if path:
            next_pos = path.pop(0)
            self.x, self.y = next_pos
            self.turns_survived += 1

class Monster(Entity):
    def __init__(self, start_x, start_y):
        super().__init__(start_x, start_y)

    def move(self, path):
        if path:
            next_pos = path.pop(0)
            self.x, self.y = next_pos

def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def a_star_search(start, goal, maze):
    neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    close_set = set()
    came_from = {}
    gscore = {start: 0}
    fscore = {start: heuristic(start, goal)}
    oheap = []

    heapq.heappush(oheap, (fscore[start], start))

    while oheap:
        current = heapq.heappop(oheap)[1]

        if current == goal:
            data = []
            while current in came_from:
                data.append(current)
                current = came_from[current]
            return data[::-1]

        close_set.add(current)
        for i, j in neighbors:
            neighbor = current[0] + i, current[1] + j
            tentative_g_score = gscore[current] + 1

            if 0 <= neighbor[0] < len(maze):
                if 0 <= neighbor[1] < len(maze[0]):
                    if maze[neighbor[0]][neighbor[1]] == 1:
                        continue
                else:
                    continue
            else:
                continue

            if neighbor in close_set and tentative_g_score >= gscore.get(neighbor, 0):
                continue

            if tentative_g_score < gscore.get(neighbor, 0) or neighbor not in [i[1] for i in oheap]:
                came_from[neighbor] = current
                gscore[neighbor] = tentative_g_score
                fscore[neighbor] = tentative_g_score + heuristic(neighbor, goal)
                heapq.heappush(oheap, (fscore[neighbor], neighbor))

    return []

def main(stdscr):
    curses.curs_set(0)  # Hide the cursor
    curses.start_color()  # Initialize colors
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Walls
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Paths
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Player
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Items
    curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)  # Monsters
    curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # Power-Ups

    width, height = max(WIDTH, CHUNK_SIZE), max(HEIGHT, CHUNK_SIZE)
    maze = Maze(width, height, CHUNK_SIZE, NUM_ITEMS)
    player = Player(1, 1)
    monsters = [Monster(random.randint(1, width - 2), random.randint(1, height - 2)) for _ in range(NUM_MONSTERS)]
    high_scores = []

    stdscr.nodelay(1)  # Set getch() to non-blocking
    stdscr.timeout(REFRESH_RATE)  # Refresh every 100ms

    last_spawn_time = time.time()
    last_power_up_spawn_time = time.time()

    while True:
        stdscr.clear()
        player.check_power_up_expiry()
        maze.display_chunk(stdscr, player.x, player.y, monsters, player.name, player.collected_items, player.turns_survived, high_scores, player.power_up_effect)

        flee_path = None
        for monster in monsters:
            path_to_player = a_star_search((monster.x, monster.y), (player.x, player.y), maze.maze)
            monster.move(path_to_player)

            if heuristic((monster.x, monster.y), (player.x, player.y)) < MONSTER_NEAR_THRESHOLD:
                flee_path = a_star_search((player.x, player.y), (player.x + (player.x - monster.x), player.y + (player.y - monster.y)), maze.maze)

            if (monster.x, monster.y) == (player.x, player.y):
                if player.extra_life:
                    player.extra_life = False
                    player.power_up_end_time = None  # Remove extra life effect after use
                else:
                    stdscr.addstr(CHUNK_SIZE + 1, 0, "Player was caught by a monster! Respawning...")
                    stdscr.refresh()
                    time.sleep(2)
                    high_scores.append((player.name, player.collected_items, player.turns_survived))
                    high_scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
                    high_scores = high_scores[:5]  # Keep top 5 high scores
                    player = Player(random.randint(1, width - 2), random.randint(1, height - 2))
                    break

        if flee_path:
            player.flee(flee_path)
        else:
            if maze.power_ups:
                nearest_power_up = min(maze.power_ups, key=lambda power_up: heuristic((player.x, player.y), (power_up[0], power_up[1])))
                path = a_star_search((player.x, player.y), (nearest_power_up[0], nearest_power_up[1]), maze.maze)
                player.move(path, maze.maze, maze.items, maze.power_ups)
            elif maze.items:
                nearest_item = min(maze.items, key=lambda item: heuristic((player.x, player.y), item))
                path = a_star_search((player.x, player.y), nearest_item, maze.maze)
                player.move(path, maze.maze, maze.items, maze.power_ups)

        current_time = time.time()
        if current_time - last_spawn_time > SPAWN_INTERVAL:
            player_chunk_x = player.x // CHUNK_SIZE
            player_chunk_y = player.y // CHUNK_SIZE
            maze.spawn_new_item(player_chunk_x, player_chunk_y)
            last_spawn_time = current_time

        if current_time - last_power_up_spawn_time > POWER_UP_SPAWN_INTERVAL:
            maze.spawn_power_up()
            last_power_up_spawn_time = current_time

        stdscr.getch()  # To handle keyboard interrupts
        time.sleep(0.1)

if __name__ == "__main__":
    curses.wrapper(main)
