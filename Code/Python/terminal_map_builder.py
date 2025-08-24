#!/usr/bin/env python3
import curses
import json
import os
import math
from enum import Enum
from typing import Dict, List, Tuple, Optional, Set

class CellType(Enum):
    EMPTY = " "
    WALL = "#"
    DOOR = "D"
    OBSTACLE = "X"
    TOKEN = "T"
    AREA = "A"
    FOG = "░"  # Light fog character

class GameMode(Enum):
    BUILD = 1
    PLAY = 2
    MEASURE = 3

class CyberpunkMap:
    def __init__(self, width: int = 20, height: int = 15):
        self.width = width
        self.height = height
        self.grid = [[CellType.EMPTY for _ in range(width)] for _ in range(height)]
        self.tokens = {}  # (x, y) -> token data
        self.fog = [[False for _ in range(width)] for _ in range(height)]  # True means hidden
        self.visibility = [[False for _ in range(width)] for _ in range(height)]  # True means visible
        self.current_tool = "select"
        self.cursor_x = 0
        self.cursor_y = 0
        self.measure_start = None
        self.cover_map = [[0 for _ in range(width)] for _ in range(height)]  # 0-100% cover
        
    def set_cell(self, x: int, y: int, cell_type: CellType):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = cell_type
            # Update cover value based on cell type
            if cell_type == CellType.WALL:
                self.cover_map[y][x] = 100
            elif cell_type == CellType.OBSTACLE:
                self.cover_map[y][x] = 50
            elif cell_type == CellType.DOOR:
                self.cover_map[y][x] = 25
            else:
                self.cover_map[y][x] = 0
                
    def get_cell(self, x: int, y: int) -> CellType:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return CellType.EMPTY
        
    def toggle_fog(self, x: int, y: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.fog[y][x] = not self.fog[y][x]
            
    def add_token(self, x: int, y: int, name: str = "Token"):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tokens[(x, y)] = {"name": name, "hp": 10, "max_hp": 10}
            self.set_cell(x, y, CellType.TOKEN)
            
    def remove_token(self, x: int, y: int):
        if (x, y) in self.tokens:
            del self.tokens[(x, y)]
            self.set_cell(x, y, CellType.EMPTY)
            
    def move_token(self, from_x: int, from_y: int, to_x: int, to_y: int) -> bool:
        if (from_x, from_y) not in self.tokens:
            return False
            
        if not (0 <= to_x < self.width and 0 <= to_y < self.height):
            return False
            
        # Check if target cell is empty
        if self.get_cell(to_x, to_y) != CellType.EMPTY:
            return False
            
        # Move the token
        token_data = self.tokens[(from_x, from_y)]
        del self.tokens[(from_x, from_y)]
        self.tokens[(to_x, to_y)] = token_data
        
        # Update grid
        self.set_cell(from_x, from_y, CellType.EMPTY)
        self.set_cell(to_x, to_y, CellType.TOKEN)
        
        return True
        
    def calculate_visibility(self, x: int, y: int, radius: int = 10):
        # Simple line-of-sight algorithm
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx, ty = x + dx, y + dy
                if 0 <= tx < self.width and 0 <= ty < self.height:
                    distance = math.sqrt(dx*dx + dy*dy)
                    if distance <= radius:
                        # Check if line of sight is blocked
                        if not self.is_line_blocked(x, y, tx, ty):
                            self.visibility[ty][tx] = True
        
    def is_line_blocked(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        # Bresenham's line algorithm to check for blocking cells
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        x, y = x1, y1
        sx = -1 if x1 > x2 else 1
        sy = -1 if y1 > y2 else 1
        
        if dx > dy:
            err = dx / 2.0
            while x != x2:
                if self.get_cell(x, y) in [CellType.WALL, CellType.OBSTACLE]:
                    return True
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
        else:
            err = dy / 2.0
            while y != y2:
                if self.get_cell(x, y) in [CellType.WALL, CellType.OBSTACLE]:
                    return True
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
                
        return False
        
    def calculate_cover(self, x: int, y: int) -> int:
        # Calculate cover based on adjacent cells
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
            
        cover = 0
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                    
                tx, ty = x + dx, y + dy
                if 0 <= tx < self.width and 0 <= ty < self.height:
                    cover += self.cover_map[ty][tx]
                    
        return min(100, cover // 4)  # Average and cap at 100%
        
    def measure_distance(self, x1: int, y1: int, x2: int, y2: int) -> Tuple[float, int]:
        # Euclidean distance
        dx = x2 - x1
        dy = y2 - y1
        euclidean = math.sqrt(dx*dx + dy*dy)
        
        # Manhattan distance
        manhattan = abs(dx) + abs(dy)
        
        return euclidean, manhattan
        
    def save(self, filename: str):
        data = {
            "width": self.width,
            "height": self.height,
            "grid": [[cell.value for cell in row] for row in self.grid],
            "tokens": {f"{x},{y}": token for (x, y), token in self.tokens.items()},
            "fog": self.fog,
            "cover_map": self.cover_map
        }
        with open(filename, 'w') as f:
            json.dump(data, f)
            
    def load(self, filename: str):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                data = json.load(f)
                self.width = data["width"]
                self.height = data["height"]
                self.grid = [[CellType(cell) for cell in row] for row in data["grid"]]
                self.tokens = {}
                for pos, token in data["tokens"].items():
                    x, y = map(int, pos.split(','))
                    self.tokens[(x, y)] = token
                self.fog = data["fog"]
                if "cover_map" in data:
                    self.cover_map = data["cover_map"]

class CyberpunkTerminalMap:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.map = CyberpunkMap()
        self.running = True
        self.message = ""
        self.message_timer = 0
        self.show_help = False
        self.mode = GameMode.BUILD
        self.selected_token = None
        self.dirty = True  # Flag to indicate if screen needs redrawing
        self.measure_start = None
        
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)    # Walls
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Doors
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Obstacles
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Tokens
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Areas
        curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)     # Highlight/Selection
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)   # Text
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_BLUE)    # Status bar
        
    def show_message(self, msg: str, duration: int = 20):
        self.message = msg
        self.message_timer = duration
        self.dirty = True
        
    def draw(self):
        if not self.dirty:
            return
            
        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        
        # Draw title with mode indicator
        mode_str = f" {self.mode.name} "
        title = f" CYBERPUNK TERMINAL GRID MAP {mode_str} "
        self.stdscr.addstr(0, (w - len(title)) // 2, title, curses.color_pair(7) | curses.A_BOLD)
        
        # Draw grid
        grid_start_y = 2
        grid_start_x = (w - self.map.width * 2) // 2
        
        for y in range(self.map.height):
            for x in range(self.map.width):
                cell_char = " "
                color_pair = 0
                attr = curses.A_NORMAL
                
                # Check visibility in PLAY mode
                if self.mode == GameMode.PLAY and not self.map.visibility[y][x] and self.map.fog[y][x]:
                    cell_char = CellType.FOG.value
                    color_pair = 0
                else:
                    cell = self.map.get_cell(x, y)
                    cell_char = cell.value
                    
                    if cell == CellType.WALL:
                        color_pair = 1
                    elif cell == CellType.DOOR:
                        color_pair = 2
                    elif cell == CellType.OBSTACLE:
                        color_pair = 3
                    elif cell == CellType.TOKEN:
                        color_pair = 4
                    elif cell == CellType.AREA:
                        color_pair = 5
                
                # Draw cell
                self.stdscr.addstr(
                    grid_start_y + y, 
                    grid_start_x + x * 2, 
                    cell_char, 
                    curses.color_pair(color_pair) | attr
                )
                
                # Draw cursor
                if x == self.map.cursor_x and y == self.map.cursor_y:
                    self.stdscr.addstr(
                        grid_start_y + y, 
                        grid_start_x + x * 2, 
                        cell_char, 
                        curses.color_pair(6) | curses.A_REVERSE
                    )
        
        # Draw measurement line if in measure mode
        if self.mode == GameMode.MEASURE and self.measure_start:
            x1, y1 = self.measure_start
            x2, y2 = self.map.cursor_x, self.map.cursor_y
            
            # Draw line using Bresenham's algorithm
            points = self.get_line_points(x1, y1, x2, y2)
            for x, y in points:
                if 0 <= x < self.map.width and 0 <= y < self.map.height:
                    self.stdscr.addstr(
                        grid_start_y + y, 
                        grid_start_x + x * 2, 
                        "•", 
                        curses.color_pair(6)
                    )
            
            # Draw distance info
            euclidean, manhattan = self.map.measure_distance(x1, y1, x2, y2)
            dist_text = f"Dist: {euclidean:.1f} units (Manhattan: {manhattan})"
            self.stdscr.addstr(grid_start_y + self.map.height + 1, grid_start_x, dist_text, curses.color_pair(7))
            
            # Draw cover info
            cover = self.map.calculate_cover(x2, y2)
            cover_text = f"Cover: {cover}%"
            self.stdscr.addstr(grid_start_y + self.map.height + 2, grid_start_x, cover_text, curses.color_pair(7))
        
        # Draw status bar
        status_line = f"Tool: {self.map.current_tool} | Pos: ({self.map.cursor_x}, {self.map.cursor_y})"
        if self.mode == GameMode.PLAY and (self.map.cursor_x, self.map.cursor_y) in self.map.tokens:
            token = self.map.tokens[(self.map.cursor_x, self.map.cursor_y)]
            status_line += f" | Token: {token['name']} HP: {token['hp']}/{token['max_hp']}"
        
        # Add cover information to status bar
        cover = self.map.calculate_cover(self.map.cursor_x, self.map.cursor_y)
        status_line += f" | Cover: {cover}%"
        
        self.stdscr.addstr(h-2, 0, status_line, curses.color_pair(8))
        
        # Draw message if any
        if self.message and self.message_timer > 0:
            self.stdscr.addstr(h-1, 0, self.message, curses.color_pair(7) | curses.A_BOLD)
            self.message_timer -= 1
        
        # Draw help if requested
        if self.show_help:
            help_text = self.get_help_text()
            for i, text in enumerate(help_text):
                if i < h - 1:
                    self.stdscr.addstr(2 + i, w - 40, text, curses.color_pair(7))
        
        self.stdscr.refresh()
        self.dirty = False
        
    def get_help_text(self):
        if self.mode == GameMode.BUILD:
            return [
                "BUILD MODE:",
                "Arrow keys: Move cursor",
                "W: Wall, D: Door, O: Obstacle",
                "A: Area, T: Token, F: Toggle fog",
                "C: Clear cell, S: Save, L: Load",
                "N: New map, M: Measure mode",
                "P: Play mode, H: Toggle help, Q: Quit"
            ]
        elif self.mode == GameMode.PLAY:
            return [
                "PLAY MODE:",
                "Arrow keys: Move cursor",
                "M: Move token, V: Calculate visibility",
                "R: Reset visibility, F: Toggle fog",
                "B: Build mode, H: Toggle help, Q: Quit"
            ]
        else:  # MEASURE mode
            return [
                "MEASURE MODE:",
                "Arrow keys: Move cursor",
                "M: Set measure point, ESC: Cancel",
                "B: Build mode, H: Toggle help, Q: Quit"
            ]
        
    def get_line_points(self, x1: int, y1: int, x2: int, y2: int) -> List[Tuple[int, int]]:
        """Bresenham's line algorithm"""
        points = []
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        x, y = x1, y1
        sx = -1 if x1 > x2 else 1
        sy = -1 if y1 > y2 else 1
        
        if dx > dy:
            err = dx / 2.0
            while x != x2:
                points.append((x, y))
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
        else:
            err = dy / 2.0
            while y != y2:
                points.append((x, y))
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
                
        points.append((x, y))
        return points
        
    def handle_input(self):
        key = self.stdscr.getch()
        
        if key == curses.KEY_RESIZE:
            self.dirty = True
            return
            
        # Handle mode-specific input
        if self.mode == GameMode.BUILD:
            self.handle_build_input(key)
        elif self.mode == GameMode.PLAY:
            self.handle_play_input(key)
        elif self.mode == GameMode.MEASURE:
            self.handle_measure_input(key)
        
    def handle_build_input(self, key):
        # Movement
        if key == curses.KEY_UP and self.map.cursor_y > 0:
            self.map.cursor_y -= 1
            self.dirty = True
        elif key == curses.KEY_DOWN and self.map.cursor_y < self.map.height - 1:
            self.map.cursor_y += 1
            self.dirty = True
        elif key == curses.KEY_LEFT and self.map.cursor_x > 0:
            self.map.cursor_x -= 1
            self.dirty = True
        elif key == curses.KEY_RIGHT and self.map.cursor_x < self.map.width - 1:
            self.map.cursor_x += 1
            self.dirty = True
            
        # Tools
        elif key == ord('w'):
            self.map.set_cell(self.map.cursor_x, self.map.cursor_y, CellType.WALL)
            self.show_message("Placed wall")
            self.dirty = True
        elif key == ord('d'):
            self.map.set_cell(self.map.cursor_x, self.map.cursor_y, CellType.DOOR)
            self.show_message("Placed door")
            self.dirty = True
        elif key == ord('o'):
            self.map.set_cell(self.map.cursor_x, self.map.cursor_y, CellType.OBSTACLE)
            self.show_message("Placed obstacle")
            self.dirty = True
        elif key == ord('a'):
            self.map.set_cell(self.map.cursor_x, self.map.cursor_y, CellType.AREA)
            self.show_message("Placed area")
            self.dirty = True
        elif key == ord('t'):
            self.map.add_token(self.map.cursor_x, self.map.cursor_y, "Character")
            self.show_message("Placed token")
            self.dirty = True
        elif key == ord('f'):
            self.map.toggle_fog(self.map.cursor_x, self.map.cursor_y)
            self.show_message("Toggled fog")
            self.dirty = True
        elif key == ord('c'):
            self.map.set_cell(self.map.cursor_x, self.map.cursor_y, CellType.EMPTY)
            if (self.map.cursor_x, self.map.cursor_y) in self.map.tokens:
                self.map.remove_token(self.map.cursor_x, self.map.cursor_y)
            self.show_message("Cleared cell")
            self.dirty = True
            
        # File operations
        elif key == ord('s'):
            self.map.save("cyberpunk_map.json")
            self.show_message("Map saved to cyberpunk_map.json")
        elif key == ord('l'):
            self.map.load("cyberpunk_map.json")
            self.show_message("Map loaded from cyberpunk_map.json")
            self.dirty = True
        elif key == ord('n'):
            self.map = CyberpunkMap()
            self.show_message("New map created")
            self.dirty = True
            
        # Mode switching
        elif key == ord('m'):
            self.mode = GameMode.MEASURE
            self.measure_start = (self.map.cursor_x, self.map.cursor_y)
            self.show_message("Measure mode: Select end point")
            self.dirty = True
        elif key == ord('p'):
            self.mode = GameMode.PLAY
            # Reset visibility when entering play mode
            self.map.visibility = [[False for _ in range(self.map.width)] for _ in range(self.map.height)]
            self.show_message("Play mode: Use M to move tokens, V for visibility")
            self.dirty = True
            
        # Help
        elif key == ord('h'):
            self.show_help = not self.show_help
            self.dirty = True
            
        # Quit
        elif key == ord('q'):
            self.running = False
            
    def handle_play_input(self, key):
        # Movement
        if key == curses.KEY_UP and self.map.cursor_y > 0:
            self.map.cursor_y -= 1
            self.dirty = True
        elif key == curses.KEY_DOWN and self.map.cursor_y < self.map.height - 1:
            self.map.cursor_y += 1
            self.dirty = True
        elif key == curses.KEY_LEFT and self.map.cursor_x > 0:
            self.map.cursor_x -= 1
            self.dirty = True
        elif key == curses.KEY_RIGHT and self.map.cursor_x < self.map.width - 1:
            self.map.cursor_x += 1
            self.dirty = True
            
        # Token movement
        elif key == ord('m'):
            if (self.map.cursor_x, self.map.cursor_y) in self.map.tokens:
                self.selected_token = (self.map.cursor_x, self.map.cursor_y)
                self.show_message("Selected token. Move cursor and press M again to move.")
            elif self.selected_token:
                from_x, from_y = self.selected_token
                if self.map.move_token(from_x, from_y, self.map.cursor_x, self.map.cursor_y):
                    self.show_message("Token moved")
                    # Update visibility after moving
                    self.map.calculate_visibility(self.map.cursor_x, self.map.cursor_y)
                else:
                    self.show_message("Cannot move token there")
                self.selected_token = None
                self.dirty = True
                
        # Visibility calculation
        elif key == ord('v'):
            if (self.map.cursor_x, self.map.cursor_y) in self.map.tokens:
                self.map.calculate_visibility(self.map.cursor_x, self.map.cursor_y)
                self.show_message("Visibility calculated from token position")
                self.dirty = True
            else:
                self.show_message("No token at cursor position")
                
        # Reset visibility
        elif key == ord('r'):
            self.map.visibility = [[False for _ in range(self.map.width)] for _ in range(self.map.height)]
            self.show_message("Visibility reset")
            self.dirty = True
            
        # Fog toggle
        elif key == ord('f'):
            self.map.toggle_fog(self.map.cursor_x, self.map.cursor_y)
            self.show_message("Toggled fog")
            self.dirty = True
            
        # Mode switching
        elif key == ord('b'):
            self.mode = GameMode.BUILD
            self.show_message("Build mode")
            self.dirty = True
            
        # Help
        elif key == ord('h'):
            self.show_help = not self.show_help
            self.dirty = True
            
        # Quit
        elif key == ord('q'):
            self.running = False
            
    def handle_measure_input(self, key):
        # Movement
        if key == curses.KEY_UP and self.map.cursor_y > 0:
            self.map.cursor_y -= 1
            self.dirty = True
        elif key == curses.KEY_DOWN and self.map.cursor_y < self.map.height - 1:
            self.map.cursor_y += 1
            self.dirty = True
        elif key == curses.KEY_LEFT and self.map.cursor_x > 0:
            self.map.cursor_x -= 1
            self.dirty = True
        elif key == curses.KEY_RIGHT and self.map.cursor_x < self.map.width - 1:
            self.map.cursor_x += 1
            self.dirty = True
            
        # Set measure point
        elif key == ord('m'):
            if self.measure_start:
                # Calculate distance
                x1, y1 = self.measure_start
                x2, y2 = self.map.cursor_x, self.map.cursor_y
                euclidean, manhattan = self.map.measure_distance(x1, y1, x2, y2)
                self.show_message(f"Distance: {euclidean:.1f} units (Manhattan: {manhattan})")
                self.measure_start = None
            else:
                self.measure_start = (self.map.cursor_x, self.map.cursor_y)
                self.show_message("Measure point set. Select end point.")
            self.dirty = True
            
        # Cancel measurement
        elif key == 27:  # ESC key
            self.measure_start = None
            self.show_message("Measurement cancelled")
            self.dirty = True
            
        # Mode switching
        elif key == ord('b'):
            self.mode = GameMode.BUILD
            self.measure_start = None
            self.show_message("Build mode")
            self.dirty = True
            
        # Help
        elif key == ord('h'):
            self.show_help = not self.show_help
            self.dirty = True
            
        # Quit
        elif key == ord('q'):
            self.running = False
            
    def run(self):
        curses.curs_set(0)  # Hide cursor
        self.stdscr.timeout(100)  # Non-blocking input with 100ms timeout
        
        while self.running:
            self.draw()
            self.handle_input()

def main(stdscr):
    app = CyberpunkTerminalMap(stdscr)
    app.run()

if __name__ == "__main__":
    curses.wrapper(main)
