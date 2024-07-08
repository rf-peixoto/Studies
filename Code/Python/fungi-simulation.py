# Don't ask.

import curses
import time
import random

# Configurable settings
MAP_WIDTH = 96
MAP_HEIGHT = 24
INITIAL_FUNGUS_COUNT = 10
TURN_DURATION = 0.5  # Time interval between updates in seconds
DEAD_MATTER_DECAY_MULTIPLIER = 1.5
EVOLUTION_CHANCE = 0.1  # Chance for spores to evolve additional traits
DEVOLUTION_CHANCE = 0.1  # Chance for spores to devolve into a normal fungus
SPECIAL_TERRAIN_SPAWN_CHANCE = 0.02  # Chance for special terrain to spawn
RANDOM_FUNGUS_SPAWN_CHANCE = 0.01  # Chance for a random normal fungus to spawn

class Fungus:
    def __init__(self, x, y, health, can_feed_on_living=False, can_connect_roots=False, light_resistance=0, spore_distance=1, max_health=10, can_feed_on_dead=False, can_feed_on_spores=False, is_toxic=False):
        self.x = x
        self.y = y
        self.health = health
        self.can_feed_on_living = can_feed_on_living
        self.can_connect_roots = can_connect_roots
        self.light_resistance = light_resistance
        self.spore_distance = spore_distance
        self.max_health = max_health
        self.can_feed_on_dead = can_feed_on_dead
        self.can_feed_on_spores = can_feed_on_spores
        self.is_toxic = is_toxic

    def evolve(self):
        if random.random() < DEVOLUTION_CHANCE:
            self.can_feed_on_living = False
            self.can_feed_on_dead = False
            self.can_feed_on_spores = False
            self.is_toxic = False
        elif random.random() < EVOLUTION_CHANCE:
            trait = random.choice(['can_feed_on_living', 'can_feed_on_spores', 'can_feed_on_dead', 'is_toxic'])
            setattr(self, trait, True)

class Simulation:
    def __init__(self, width, height, initial_fungus_count):
        self.width = width
        self.height = height
        self.map = [['.' for _ in range(width)] for _ in range(height)]
        self.fungi = []
        self.dead_matter = []
        self.turns = 0
        self.initialize_fungi(initial_fungus_count)
        self.spawn_special_terrain()

    def initialize_fungi(self, count):
        for _ in range(count):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            fungus = Fungus(x, y, health=10)
            self.fungi.append(fungus)
            self.map[y][x] = 'F'

    def spawn_special_terrain(self):
        for _ in range(random.randint(1, 5)):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            self.map[y][x] = '+'

    def update(self):
        # Update the state of the simulation for one turn
        self.turns += 1
        new_fungi = []
        for fungus in self.fungi:
            fungus.health -= 1
            if fungus.health <= 0:
                if fungus.is_toxic:
                    self.map[fungus.y][fungus.x] = 'T'
                    self.dead_matter.append((fungus.x, fungus.y, int(fungus.max_health * DEAD_MATTER_DECAY_MULTIPLIER), True))
                elif fungus.can_feed_on_dead:
                    # Minimal resource dead matter
                    self.map[fungus.y][fungus.x] = 'd'
                    self.dead_matter.append((fungus.x, fungus.y, 1, False))  # Minimal decay time
                else:
                    # Normal dead matter
                    self.map[fungus.y][fungus.x] = 'D'
                    self.dead_matter.append((fungus.x, fungus.y, int(fungus.max_health * DEAD_MATTER_DECAY_MULTIPLIER), False))
                continue

            # Feeding on dead matter
            if self.map[fungus.y][fungus.x] == 'D':
                if fungus.can_feed_on_dead:
                    fungus.health += 2
                    self.map[fungus.y][fungus.x] = '.'
                else:
                    fungus.health += 1
                    self.map[fungus.y][fungus.x] = '.'
            elif self.map[fungus.y][fungus.x] == 'T':
                fungus.health = 0  # Toxic dead matter kills any feeding fungus
            elif self.map[fungus.y][fungus.x] == 'd' and fungus.can_feed_on_dead:
                fungus.health += 1
                self.map[fungus.y][fungus.x] = '.'

            # Spreading spores
            if fungus.health % 2 == 0:
                for _ in range(fungus.spore_distance):
                    nx, ny = fungus.x + random.randint(-1, 1), fungus.y + random.randint(-1, 1)
                    if 0 <= nx < self.width and 0 <= ny < self.height and self.map[ny][nx] == '.':
                        new_fungus = Fungus(nx, ny, health=5, 
                                            can_feed_on_living=fungus.can_feed_on_living, 
                                            can_connect_roots=fungus.can_connect_roots, 
                                            light_resistance=fungus.light_resistance, 
                                            spore_distance=fungus.spore_distance,
                                            max_health=fungus.max_health,
                                            can_feed_on_dead=fungus.can_feed_on_dead,
                                            can_feed_on_spores=fungus.can_feed_on_spores,
                                            is_toxic=fungus.is_toxic)
                        new_fungus.evolve()
                        new_fungi.append(new_fungus)
                        self.map[ny][nx] = 'S'
            
            self.map[fungus.y][fungus.x] = self.get_fungus_char(fungus)
            new_fungi.append(fungus)
        
        self.fungi = new_fungi

        # Process dead matter decay
        updated_dead_matter = []
        for x, y, remaining_turns, is_toxic in self.dead_matter:
            if remaining_turns > 0:
                updated_dead_matter.append((x, y, remaining_turns - 1, is_toxic))
            else:
                self.map[y][x] = '.'
        self.dead_matter = updated_dead_matter

        # Randomly spawn special terrain
        if random.random() < SPECIAL_TERRAIN_SPAWN_CHANCE:
            self.spawn_special_terrain()

        # Randomly spawn normal fungus
        if random.random() < RANDOM_FUNGUS_SPAWN_CHANCE:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.map[y][x] == '.':
                fungus = Fungus(x, y, health=10)
                self.fungi.append(fungus)
                self.map[y][x] = 'F'

    def get_fungus_char(self, fungus):
        if fungus.can_feed_on_living:
            return 'L'
        elif fungus.can_feed_on_dead:
            return 'D'
        elif fungus.can_feed_on_spores:
            return 'P'
        elif fungus.is_toxic:
            return 'X'
        else:
            return 'F'

def draw(stdscr, sim):
    stdscr.clear()
    # Draw the map
    for y in range(sim.height):
        for x in range(sim.width):
            char = sim.map[y][x]
            if char == 'F':
                stdscr.addch(y, x, char, curses.color_pair(1))
            elif char == 'L':
                stdscr.addch(y, x, char, curses.color_pair(5))
            elif char == 'D':
                stdscr.addch(y, x, char, curses.color_pair(6))
            elif char == 'P':
                stdscr.addch(y, x, char, curses.color_pair(7))
            elif char == 'd':
                stdscr.addch(y, x, char, curses.color_pair(8))
            elif char == 'S':
                stdscr.addch(y, x, char, curses.color_pair(3))
            elif char == 'X':
                stdscr.addch(y, x, char, curses.color_pair(10))
            elif char == '+':
                stdscr.addch(y, x, char, curses.color_pair(9))
            elif char == '.':
                stdscr.addch(y, x, char, curses.color_pair(4))
            elif char == 'T':
                stdscr.addch(y, x, char, curses.color_pair(11))  # Toxic Dead Matter

    # Draw statistics
    stats_start_x = sim.width + 2
    stdscr.addstr(0, stats_start_x, f"Turn: {sim.turns}")
    stdscr.addstr(1, stats_start_x, f"Fungi: {len(sim.fungi)}")
    stdscr.addstr(2, stats_start_x, f"Dead Matter: {len([d for d in sim.dead_matter if not d[3]])}")
    stdscr.addstr(3, stats_start_x, f"Toxic Dead Matter: {len([d for d in sim.dead_matter if d[3]])}")
    stdscr.addstr(4, stats_start_x, f"Spores: {sum(1 for row in sim.map for cell in row if cell == 'S')}")
    stdscr.addstr(6, stats_start_x, "Legend:")
    stdscr.addstr(7, stats_start_x, "F: Fungus", curses.color_pair(1))
    stdscr.addstr(8, stats_start_x, "L: Fungus (Feeds on Living)", curses.color_pair(5))
    stdscr.addstr(9, stats_start_x, "D: Fungus (Feeds on Dead)", curses.color_pair(6))
    stdscr.addstr(10, stats_start_x, "P: Fungus (Feeds on Spores)", curses.color_pair(7))
    stdscr.addstr(11, stats_start_x, "d: Minimal Dead Matter", curses.color_pair(8))
    stdscr.addstr(12, stats_start_x, "D: Dead Matter", curses.color_pair(2))
    stdscr.addstr(13, stats_start_x, "X: Toxic Fungus", curses.color_pair(10))
    stdscr.addstr(14, stats_start_x, "T: Toxic Dead Matter", curses.color_pair(11))
    stdscr.addstr(15, stats_start_x, "S: Spore", curses.color_pair(3))
    stdscr.addstr(16, stats_start_x, "+: Special Terrain", curses.color_pair(9))
    stdscr.addstr(17, stats_start_x, ".: Empty Terrain", curses.color_pair(4))

    stdscr.refresh()

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(1)
    stdscr.timeout(int(TURN_DURATION * 1000))

    # Initialize colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Fungus
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)    # Dead Matter
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Spore
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Empty Terrain
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Fungus (Feeds on Living)
    curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Fungus (Feeds on Dead)
    curses.init_pair(7, curses.COLOR_BLUE, curses.COLOR_BLACK)   # Fungus (Feeds on Spores)
    curses.init_pair(8, curses.COLOR_RED, curses.COLOR_BLACK)    # Minimal Dead Matter
    curses.init_pair(9, curses.COLOR_GREEN, curses.COLOR_YELLOW) # Special Terrain
    curses.init_pair(10, curses.COLOR_RED, curses.COLOR_GREEN)   # Toxic Fungus
    curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_RED)   # Toxic Dead Matter

    sim = Simulation(MAP_WIDTH, MAP_HEIGHT, INITIAL_FUNGUS_COUNT)

    while True:
        draw(stdscr, sim)
        sim.update()
        time.sleep(TURN_DURATION)
        if stdscr.getch() == ord('q'):
            break

curses.wrapper(main)
