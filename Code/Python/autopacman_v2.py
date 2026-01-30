#!/usr/bin/env python3
"""
AutoPacman (curses) — rewritten for performance, correctness, and visuals.

Key improvements vs the original:
- Correct grid indexing: maze[y][x] everywhere.
- Items and power-ups use O(1) structures (set/dict), no O(n) membership in hot loops.
- Pathfinding replaced with BFS distance fields:
  * 1 BFS from player per AI tick (monsters chase via gradient descent).
  * 1 multi-source BFS from monsters per AI tick (player/thief flee via gradient ascent).
  * Thief uses BFS to find nearest goal (item/power-up) without repeated A*.
- Rendering is viewport-based (camera follows player) + dirty-cell drawing (updates only changes).
- Better HUD, borders, colors, and optional Unicode glyphs.
- Safer spawning and bounded retries (no infinite loops).
- Controls: Q quit, P pause, +/- speed, R restart.

Tested assumptions:
- Terminal supports curses colors. Unicode is optional.
"""

from __future__ import annotations

import curses
import random
import time
from dataclasses import dataclass
from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

# ----------------------------
# Configuration
# ----------------------------
WORLD_W = 96
WORLD_H = 64

# Viewport (camera) size in cells (odd is nicer for centering)
VIEW_W = 25
VIEW_H = 25

# Simulation timing
BASE_TICK_MS = 80          # lower is faster
AI_TICK_EVERY_N_FRAMES = 2 # compute BFS fields every N frames

# Gameplay
NUM_ITEMS = 14
NUM_MONSTERS = 5
NUM_THIEVES = 1

ITEM_SPAWN_INTERVAL_S = 5
POWERUP_SPAWN_INTERVAL_S = 10
POWERUP_DURATION_S = 15

FLEE_THRESHOLD = 9   # if nearest monster is within this many steps, flee

POWER_UPS = ("speed", "extra_life", "double_value")

# Maze generation
MAZE_CARVE_STEP = 2  # standard "grid maze" carving with step=2


# ----------------------------
# Helpers
# ----------------------------
Pos = Tuple[int, int]  # (x, y)


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def now() -> float:
    return time.time()


def neighbors4(x: int, y: int) -> Iterable[Pos]:
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)


# ----------------------------
# World & Maze
# ----------------------------
class World:
    """
    Grid world: 0 = floor, 1 = wall.
    """
    def __init__(self, w: int, h: int, num_items: int):
        self.w = w
        self.h = h
        self.grid: List[List[int]] = [[1] * w for _ in range(h)]  # grid[y][x]

        # Gameplay objects
        self.items: Set[Pos] = set()
        self.powerups: Dict[Pos, str] = {}  # (x,y) -> effect

        # Cached list of free cells for robust spawning
        self._free_cells: List[Pos] = []

        self._generate_maze()
        self._rebuild_free_cells()

        self._spawn_many_items(num_items)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_floor(self, x: int, y: int) -> bool:
        return self.grid[y][x] == 0

    def _generate_maze(self) -> None:
        """
        Recursive backtracker (iterative) carving maze on odd coordinates.
        """
        # Start with all walls
        for y in range(self.h):
            for x in range(self.w):
                self.grid[y][x] = 1

        # Ensure boundaries are walls; carve within [1..w-2, 1..h-2]
        sx, sy = 1, 1
        self.grid[sy][sx] = 0
        stack = [(sx, sy)]

        def unvisited_neighbors(cx: int, cy: int) -> List[Pos]:
            out = []
            for dx, dy in ((-MAZE_CARVE_STEP, 0), (MAZE_CARVE_STEP, 0), (0, -MAZE_CARVE_STEP), (0, MAZE_CARVE_STEP)):
                nx, ny = cx + dx, cy + dy
                if 1 <= nx < self.w - 1 and 1 <= ny < self.h - 1 and self.grid[ny][nx] == 1:
                    out.append((nx, ny))
            return out

        while stack:
            cx, cy = stack[-1]
            nbrs = unvisited_neighbors(cx, cy)
            if not nbrs:
                stack.pop()
                continue

            nx, ny = random.choice(nbrs)
            # Carve passage between current and neighbor
            mx, my = (cx + nx) // 2, (cy + ny) // 2
            self.grid[my][mx] = 0
            self.grid[ny][nx] = 0
            stack.append((nx, ny))

        # Optionally add a few random holes to reduce dead-ends
        holes = max(10, (self.w * self.h) // 200)
        for _ in range(holes):
            x = random.randint(1, self.w - 2)
            y = random.randint(1, self.h - 2)
            self.grid[y][x] = 0

    def _rebuild_free_cells(self) -> None:
        self._free_cells = [(x, y) for y in range(1, self.h - 1) for x in range(1, self.w - 1) if self.is_floor(x, y)]

    def random_free_cell(self, forbidden: Set[Pos], max_tries: int = 2000) -> Optional[Pos]:
        """
        Returns a random floor cell not in forbidden, or None if not found quickly.
        """
        if not self._free_cells:
            return None

        for _ in range(max_tries):
            x, y = random.choice(self._free_cells)
            if (x, y) not in forbidden:
                return (x, y)
        return None

    def _spawn_many_items(self, n: int) -> None:
        forbidden = set(self.items) | set(self.powerups.keys())
        while len(self.items) < n:
            cell = self.random_free_cell(forbidden)
            if cell is None:
                break
            self.items.add(cell)
            forbidden.add(cell)

    def spawn_item_away_from(self, avoid_center: Pos, avoid_radius: int = 6) -> None:
        """
        Spawn one item not too close to avoid_center (usually player).
        """
        ax, ay = avoid_center
        forbidden = set(self.items) | set(self.powerups.keys())
        # Also forbid near player to avoid immediate collection
        for x in range(ax - avoid_radius, ax + avoid_radius + 1):
            for y in range(ay - avoid_radius, ay + avoid_radius + 1):
                if self.in_bounds(x, y):
                    forbidden.add((x, y))

        cell = self.random_free_cell(forbidden)
        if cell is not None:
            self.items.add(cell)

    def spawn_powerup(self) -> None:
        forbidden = set(self.items) | set(self.powerups.keys())
        cell = self.random_free_cell(forbidden)
        if cell is None:
            return
        self.powerups[cell] = random.choice(POWER_UPS)


# ----------------------------
# Entities
# ----------------------------
@dataclass
class Actor:
    x: int
    y: int

    def pos(self) -> Pos:
        return (self.x, self.y)

    def move_to(self, p: Pos) -> None:
        self.x, self.y = p


@dataclass
class Player(Actor):
    name: str
    items_collected: int = 0
    turns_survived: int = 0

    extra_life: bool = False
    double_value: bool = False
    speed_boost: bool = False

    powerup_effect: Optional[str] = None
    powerup_until: Optional[float] = None

    def apply_powerup(self, effect: str) -> None:
        self.powerup_effect = effect
        self.powerup_until = now() + POWERUP_DURATION_S

        if effect == "speed":
            self.speed_boost = True
        elif effect == "extra_life":
            self.extra_life = True
        elif effect == "double_value":
            self.double_value = True

    def expire_powerups_if_needed(self) -> None:
        if self.powerup_until is None:
            return
        if now() < self.powerup_until:
            return

        # Expire
        self.powerup_until = None
        self.powerup_effect = None
        self.speed_boost = False
        self.double_value = False
        self.extra_life = False


@dataclass
class Monster(Actor):
    pass


@dataclass
class Thief(Actor):
    items_stolen: int = 0
    extra_life: bool = False
    double_value: bool = False
    speed_boost: bool = False
    powerup_effect: Optional[str] = None
    powerup_until: Optional[float] = None

    def apply_powerup(self, effect: str) -> None:
        self.powerup_effect = effect
        self.powerup_until = now() + POWERUP_DURATION_S

        if effect == "speed":
            self.speed_boost = True
        elif effect == "extra_life":
            self.extra_life = True
        elif effect == "double_value":
            self.double_value = True

    def expire_powerups_if_needed(self) -> None:
        if self.powerup_until is None:
            return
        if now() < self.powerup_until:
            return

        self.powerup_until = None
        self.powerup_effect = None
        self.speed_boost = False
        self.double_value = False
        self.extra_life = False


# ----------------------------
# Path utilities: BFS distance fields
# ----------------------------
INF = 10**9


def bfs_distances(world: World, sources: Iterable[Pos]) -> List[List[int]]:
    """
    Multi-source BFS distances over floors.
    Returns dist[y][x] with INF for unreachable.
    """
    dist = [[INF] * world.w for _ in range(world.h)]
    q = deque()

    for (sx, sy) in sources:
        if world.in_bounds(sx, sy) and world.is_floor(sx, sy):
            dist[sy][sx] = 0
            q.append((sx, sy))

    while q:
        x, y = q.popleft()
        d = dist[y][x] + 1
        for nx, ny in neighbors4(x, y):
            if not world.in_bounds(nx, ny):
                continue
            if not world.is_floor(nx, ny):
                continue
            if dist[ny][nx] <= d:
                continue
            dist[ny][nx] = d
            q.append((nx, ny))
    return dist


def step_by_gradient(world: World, start: Pos, dist: List[List[int]], want_min: bool) -> Pos:
    """
    Move one step from start to a neighbor based on distance field.
    If want_min=True: choose neighbor with minimum dist (chase).
    If want_min=False: choose neighbor with maximum dist (flee).
    Ties are randomized for more natural motion.
    """
    x, y = start
    best = (x, y)
    best_val = dist[y][x]

    candidates: List[Pos] = []
    for nx, ny in neighbors4(x, y):
        if not world.in_bounds(nx, ny) or not world.is_floor(nx, ny):
            continue
        v = dist[ny][nx]
        if want_min:
            if v < best_val:
                best_val = v
                candidates = [(nx, ny)]
            elif v == best_val:
                candidates.append((nx, ny))
        else:
            if v > best_val:
                best_val = v
                candidates = [(nx, ny)]
            elif v == best_val:
                candidates.append((nx, ny))

    if candidates:
        return random.choice(candidates)
    return best


def bfs_find_nearest_goal(world: World, start: Pos, goals: Set[Pos]) -> Optional[Pos]:
    """
    BFS until the first goal is found (true shortest path in steps).
    Returns the goal cell, or None.
    """
    if not goals:
        return None
    sx, sy = start
    if (sx, sy) in goals:
        return (sx, sy)

    seen = set([(sx, sy)])
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for nx, ny in neighbors4(x, y):
            if not world.in_bounds(nx, ny) or not world.is_floor(nx, ny):
                continue
            if (nx, ny) in seen:
                continue
            if (nx, ny) in goals:
                return (nx, ny)
            seen.add((nx, ny))
            q.append((nx, ny))
    return None


# ----------------------------
# Rendering
# ----------------------------
class Renderer:
    def __init__(self, stdscr: "curses._CursesWindow", world: World):
        self.stdscr = stdscr
        self.world = world

        self.last_cells: Dict[Tuple[int, int], Tuple[str, int]] = {}
        self.unicode_ok = self._detect_unicode_ok()

        self._init_colors()
        self._init_glyphs()

    def _detect_unicode_ok(self) -> bool:
        try:
            "█".encode()
            return True
        except Exception:
            return False

    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()

        # Pair IDs
        # 1 wall, 2 floor, 3 player, 4 item, 5 monster, 6 powerup, 7 thief, 8 hud
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        curses.init_pair(7, curses.COLOR_WHITE, -1)
        curses.init_pair(8, curses.COLOR_BLUE, -1)

        self.A_WALL = curses.color_pair(1)
        self.A_FLOOR = curses.color_pair(2)
        self.A_PLAYER = curses.color_pair(3) | curses.A_BOLD
        self.A_ITEM = curses.color_pair(4)
        self.A_MONSTER = curses.color_pair(5) | curses.A_BOLD
        self.A_POWERUP = curses.color_pair(6) | curses.A_BOLD
        self.A_THIEF = curses.color_pair(7) | curses.A_BOLD
        self.A_HUD = curses.color_pair(8)

    def _init_glyphs(self) -> None:
        if self.unicode_ok:
            self.G_WALL = "#"
            self.G_FLOOR = "·"
            self.G_ITEM = "I"
            self.G_POWERUP = "P"
            self.G_PLAYER = "@"
            self.G_MONSTER = "M"
            self.G_THIEF = "T"
        else:
            # ASCII fallback
            self.G_WALL = "#"
            self.G_FLOOR = "."
            self.G_ITEM = "I"
            self.G_POWERUP = "P"
            self.G_PLAYER = "@"
            self.G_MONSTER = "M"
            self.G_THIEF = "T"

    def _put(self, sy: int, sx: int, ch: str, attr: int) -> None:
        """
        Dirty-cell drawing: only write if changed.
        """
        key = (sy, sx)
        prev = self.last_cells.get(key)
        cur = (ch, attr)
        if prev == cur:
            return
        try:
            self.stdscr.addstr(sy, sx, ch, attr)
        except curses.error:
            # Window too small or edge write: ignore
            pass
        self.last_cells[key] = cur

    def clear(self) -> None:
        self.stdscr.erase()
        self.last_cells.clear()

    def draw(
        self,
        player: Player,
        monsters: List[Monster],
        thieves: List[Thief],
        high_scores: List[Tuple[str, int, int]],
        paused: bool,
        tick_ms: int,
    ) -> None:
        h, w = self.stdscr.getmaxyx()

        # Minimum size check
        needed_w = VIEW_W + 2 + 34
        needed_h = max(VIEW_H + 2, 14)
        if w < needed_w or h < needed_h:
            self.stdscr.erase()
            msg = f"Terminal too small. Need at least {needed_w}x{needed_h}. Current {w}x{h}."
            self.stdscr.addstr(0, 0, msg)
            self.stdscr.addstr(2, 0, "Resize the terminal and restart.")
            self.stdscr.refresh()
            return

        # Camera origin (top-left world cell shown)
        cam_x = clamp(player.x - VIEW_W // 2, 0, self.world.w - VIEW_W)
        cam_y = clamp(player.y - VIEW_H // 2, 0, self.world.h - VIEW_H)

        # Precompute positions for O(1) checks
        monster_pos = {m.pos() for m in monsters}
        thief_pos = {t.pos() for t in thieves}
        power_pos = set(self.world.powerups.keys())

        # Frame border
        top = 0
        left = 0
        for sx in range(left, left + VIEW_W + 2):
            self._put(top, sx, "─", self.A_HUD)
            self._put(top + VIEW_H + 1, sx, "─", self.A_HUD)
        for sy in range(top, top + VIEW_H + 2):
            self._put(sy, left, "│", self.A_HUD)
            self._put(sy, left + VIEW_W + 1, "│", self.A_HUD)
        self._put(top, left, "┌", self.A_HUD)
        self._put(top, left + VIEW_W + 1, "┐", self.A_HUD)
        self._put(top + VIEW_H + 1, left, "└", self.A_HUD)
        self._put(top + VIEW_H + 1, left + VIEW_W + 1, "┘", self.A_HUD)

        # Map area
        for vy in range(VIEW_H):
            wy = cam_y + vy
            sy = top + 1 + vy
            for vx in range(VIEW_W):
                wx = cam_x + vx
                sx = left + 1 + vx

                p = (wx, wy)
                if p == player.pos():
                    self._put(sy, sx, self.G_PLAYER, self.A_PLAYER)
                elif p in monster_pos:
                    self._put(sy, sx, self.G_MONSTER, self.A_MONSTER)
                elif p in thief_pos:
                    self._put(sy, sx, self.G_THIEF, self.A_THIEF)
                elif p in self.world.items:
                    self._put(sy, sx, self.G_ITEM, self.A_ITEM)
                elif p in power_pos:
                    self._put(sy, sx, self.G_POWERUP, self.A_POWERUP)
                else:
                    if self.world.is_floor(wx, wy):
                        self._put(sy, sx, self.G_FLOOR, self.A_FLOOR)
                    else:
                        self._put(sy, sx, self.G_WALL, self.A_WALL)

        # HUD panel
        hud_x = left + VIEW_W + 3
        hud_y = 0

        lines: List[str] = []
        lines.append("AutoPacman — autoplay")
        lines.append("")
        lines.append(f"Player: {player.name}")
        lines.append(f"Items:  {player.items_collected}")
        lines.append(f"Turns:  {player.turns_survived}")
        lines.append(f"Life:   {'EXTRA' if player.extra_life else 'NORMAL'}")
        pu = player.powerup_effect if player.powerup_effect else "None"
        lines.append(f"Power:  {pu}")
        lines.append("")
        lines.append(f"Monsters: {len(monsters)}   Thieves: {len(thieves)}")
        lines.append(f"Speed: {tick_ms} ms/tick")
        lines.append(f"State: {'PAUSED' if paused else 'RUNNING'}")
        lines.append("")
        lines.append("Controls:")
        lines.append("  Q quit   P pause")
        lines.append("  + faster  - slower")
        lines.append("  R restart")
        lines.append("")
        lines.append("High Scores:")

        # Print top-5 scores
        hs = high_scores[:5]
        if not hs:
            lines.append("  (none yet)")
        else:
            for i, (name, score, turns) in enumerate(hs, 1):
                lines.append(f"  {i}. {name}: {score} items, {turns} turns")

        for i, s in enumerate(lines):
            try:
                self.stdscr.addstr(hud_y + i, hud_x, s[: (w - hud_x - 1)], self.A_HUD)
            except curses.error:
                pass

        self.stdscr.noutrefresh()
        curses.doupdate()


# ----------------------------
# Game Loop
# ----------------------------
PLAYER_NAMES = ["Alex", "Blake", "Casey", "Drew", "Elliot", "Frankie", "Glen", "Harper", "Jesse", "Kai"]


class Game:
    def __init__(self, stdscr: "curses._CursesWindow"):
        self.stdscr = stdscr
        self.tick_ms = BASE_TICK_MS
        self.paused = False

        self.high_scores: List[Tuple[str, int, int]] = []

        self.reset()

    def reset(self) -> None:
        self.world = World(WORLD_W, WORLD_H, NUM_ITEMS)

        # Spawn player on a free cell (prefer near 1,1 if available)
        spawn = (1, 1) if self.world.is_floor(1, 1) else self.world.random_free_cell(set()) or (1, 1)
        self.player = Player(spawn[0], spawn[1], name=random.choice(PLAYER_NAMES))

        forbidden = {self.player.pos()} | self.world.items | set(self.world.powerups.keys())

        self.monsters: List[Monster] = []
        for _ in range(NUM_MONSTERS):
            cell = self.world.random_free_cell(forbidden)
            if cell is None:
                break
            self.monsters.append(Monster(*cell))
            forbidden.add(cell)

        self.thieves: List[Thief] = []
        for _ in range(NUM_THIEVES):
            cell = self.world.random_free_cell(forbidden)
            if cell is None:
                break
            self.thieves.append(Thief(*cell))
            forbidden.add(cell)

        self.renderer = Renderer(self.stdscr, self.world)
        self.renderer.clear()

        self.frame = 0
        self.last_item_spawn = now()
        self.last_power_spawn = now()

        # Cached distance fields updated on AI ticks
        self.dist_to_player: Optional[List[List[int]]] = None
        self.dist_to_monsters: Optional[List[List[int]]] = None

    def handle_input(self) -> bool:
        """
        Returns False to quit.
        """
        ch = self.stdscr.getch()
        if ch == -1:
            return True

        if ch in (ord("q"), ord("Q")):
            return False
        if ch in (ord("p"), ord("P")):
            self.paused = not self.paused
        if ch == ord("+") or ch == ord("="):
            self.tick_ms = max(20, self.tick_ms - 10)
        if ch == ord("-") or ch == ord("_"):
            self.tick_ms = min(300, self.tick_ms + 10)
        if ch in (ord("r"), ord("R")):
            self.reset()

        return True

    def _collect_if_present(self, actor: Actor) -> None:
        p = actor.pos()

        # Items
        if p in self.world.items:
            self.world.items.remove(p)

            if isinstance(actor, Player):
                actor.items_collected += (2 if actor.double_value else 1)
            elif isinstance(actor, Thief):
                actor.items_stolen += (2 if actor.double_value else 1)

        # Power-ups
        if p in self.world.powerups:
            eff = self.world.powerups.pop(p)
            if isinstance(actor, Player):
                actor.apply_powerup(eff)
            elif isinstance(actor, Thief):
                actor.apply_powerup(eff)

    def _respawn_player_after_death(self) -> None:
        # Record score
        self.high_scores.append((self.player.name, self.player.items_collected, self.player.turns_survived))
        self.high_scores.sort(key=lambda t: (t[1], t[2]), reverse=True)
        self.high_scores = self.high_scores[:5]

        # New player
        cell = self.world.random_free_cell(set(self.monsters_pos()) | set(self.thieves_pos()))
        if cell is None:
            cell = (1, 1)
        self.player = Player(cell[0], cell[1], name=random.choice(PLAYER_NAMES))

    def monsters_pos(self) -> Set[Pos]:
        return {m.pos() for m in self.monsters}

    def thieves_pos(self) -> Set[Pos]:
        return {t.pos() for t in self.thieves}

    def compute_fields(self) -> None:
        # Player field: used by monsters to chase
        self.dist_to_player = bfs_distances(self.world, [self.player.pos()])

        # Monster field: used by player/thief to flee (multi-source)
        if self.monsters:
            self.dist_to_monsters = bfs_distances(self.world, [m.pos() for m in self.monsters])
        else:
            self.dist_to_monsters = None

    def step_ai(self) -> None:
        """
        One AI step for all entities.
        """
        self.player.expire_powerups_if_needed()
        for t in self.thieves:
            t.expire_powerups_if_needed()

        # Distance fields might not be computed yet (first frame)
        if self.dist_to_player is None or (self.monsters and self.dist_to_monsters is None):
            self.compute_fields()

        # ---- Monsters: chase player via gradient descent on dist_to_player
        if self.dist_to_player is not None:
            for m in self.monsters:
                nxt = step_by_gradient(self.world, m.pos(), self.dist_to_player, want_min=True)
                m.move_to(nxt)

        # ---- Thief: flee if too close to monsters; otherwise steal nearest (powerup preferred)
        for t in list(self.thieves):
            # If thief collides with player, the player "recovers" stolen items (and thief disappears)
            if t.pos() == self.player.pos():
                self.player.items_collected += t.items_stolen
                self.thieves.remove(t)
                continue

            fled = False
            if self.dist_to_monsters is not None:
                d = self.dist_to_monsters[t.y][t.x]
                if d < FLEE_THRESHOLD:
                    nxt = step_by_gradient(self.world, t.pos(), self.dist_to_monsters, want_min=False)
                    t.move_to(nxt)
                    fled = True

            if not fled:
                # Prefer power-ups if any exist
                goals = set(self.world.powerups.keys()) if self.world.powerups else set(self.world.items)
                target = bfs_find_nearest_goal(self.world, t.pos(), goals)
                if target is not None:
                    # Move one step along shortest path: use dist-from-target and descend
                    dist_to_target = bfs_distances(self.world, [target])
                    nxt = step_by_gradient(self.world, t.pos(), dist_to_target, want_min=True)
                    t.move_to(nxt)

            self._collect_if_present(t)

        # ---- Player: flee if monsters nearby, otherwise collect (powerups first)
        self.player.turns_survived += 1

        flee_move_done = False
        if self.dist_to_monsters is not None:
            d = self.dist_to_monsters[self.player.y][self.player.x]
            if d < FLEE_THRESHOLD:
                nxt = step_by_gradient(self.world, self.player.pos(), self.dist_to_monsters, want_min=False)
                self.player.move_to(nxt)
                flee_move_done = True

        if not flee_move_done:
            # Prefer power-ups, then items
            if self.world.powerups:
                # Find nearest power-up by BFS
                target = bfs_find_nearest_goal(self.world, self.player.pos(), set(self.world.powerups.keys()))
                if target is not None:
                    dist_to_target = bfs_distances(self.world, [target])
                    nxt = step_by_gradient(self.world, self.player.pos(), dist_to_target, want_min=True)
                    self.player.move_to(nxt)
            elif self.world.items:
                target = bfs_find_nearest_goal(self.world, self.player.pos(), set(self.world.items))
                if target is not None:
                    dist_to_target = bfs_distances(self.world, [target])
                    nxt = step_by_gradient(self.world, self.player.pos(), dist_to_target, want_min=True)
                    self.player.move_to(nxt)

        self._collect_if_present(self.player)

        # ---- Collisions: monsters vs player
        for m in self.monsters:
            if m.pos() == self.player.pos():
                if self.player.extra_life:
                    # Consume extra life and keep playing
                    self.player.extra_life = False
                    self.player.powerup_until = None
                    self.player.powerup_effect = None
                else:
                    self._respawn_player_after_death()
                break

    def step_spawners(self) -> None:
        t = now()
        if t - self.last_item_spawn >= ITEM_SPAWN_INTERVAL_S:
            self.world.spawn_item_away_from(self.player.pos(), avoid_radius=5)
            self.last_item_spawn = t

        if t - self.last_power_spawn >= POWERUP_SPAWN_INTERVAL_S:
            self.world.spawn_powerup()
            self.last_power_spawn = t

    def run(self) -> None:
        curses.curs_set(0)
        self.stdscr.nodelay(True)

        # Main loop
        last_frame_time = now()
        while True:
            if not self.handle_input():
                return

            if self.paused:
                self.renderer.draw(self.player, self.monsters, self.thieves, self.high_scores, self.paused, self.tick_ms)
                time.sleep(0.03)
                continue

            # Frame pacing
            t = now()
            elapsed = t - last_frame_time
            target = self.tick_ms / 1000.0
            if elapsed < target:
                time.sleep(target - elapsed)
            last_frame_time = now()

            # AI tick scheduling
            if self.frame % AI_TICK_EVERY_N_FRAMES == 0:
                self.compute_fields()

            # If speed power-up is active, player effectively acts twice (lightweight boost)
            # (This is intentionally conservative to keep balance.)
            self.step_ai()
            if self.player.speed_boost and (self.frame % 3 == 0):
                self.step_ai()

            self.step_spawners()

            self.renderer.draw(self.player, self.monsters, self.thieves, self.high_scores, self.paused, self.tick_ms)

            self.frame += 1


# ----------------------------
# Entry point
# ----------------------------
def main(stdscr: "curses._CursesWindow") -> None:
    random.seed()
    game = Game(stdscr)
    game.run()


if __name__ == "__main__":
    curses.wrapper(main)
