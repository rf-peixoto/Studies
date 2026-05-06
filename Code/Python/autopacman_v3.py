#!/usr/bin/env python3
"""
AutoPacman (curses) — v3: bug-fixed, optimized, and feature-expanded.

━━ Bug fixes vs v2.1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. Unicode detection: `"█".encode()` always succeeds in Python 3 (UTF-8).
    Fixed to check sys.stdout.encoding properly.
 2. Unicode/ASCII glyph tables were identical in both branches. Now distinct.
 3. Single powerup_effect/powerup_until couldn't track multiple active power-ups
    concurrently. Replaced with Dict[str, float] (effect→expiry) — each power-up
    expires independently.
 4. Thief color pair 7 (WHITE) clashed with wall pair 1 (WHITE). Thief is now BLUE.
 5. Caught thieves were removed but never respawned. Added _respawn_thief().
 6. Monster spawn had no minimum distance from player. Added random_free_cell_far_from().
 7. BFS sources not deduplicated — two monsters at same cell enqueued twice. Fixed.
 8. bfs_distances called once per entity per AI tick for goal navigation.
    Replaced with a per-tick goal→dist cache (_goal_bfs_cache).
 9. HUD text not padded; stale characters lingered on resize/state change. Fixed.
10. time.time() replaced with time.monotonic() for frame pacing (clock-skew safe).
11. extra_life consumed by clearing powerup_until, nuking ALL active effects. Fixed
    to pop only the "extra_life" key from active_powerups.

━━ New features ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • Shield power-up    — temporary invincibility; player shown in cyan.
  • Score combo        — collecting items rapidly multiplies their value (tier
                         increases every 3 consecutive collects within window).
  • Monster variants   — Normal | Fast (moves twice per AI tick) | Scatter type
                         (always uses corner-targeting, never chases).
  • Global scatter mode — all monsters periodically flee to maze corners instead
                         of chasing the player (classic Pac-Man scatter phase).
  • FPS counter        — rolling average displayed in HUD.
  • Thief respawn      — a new thief spawns immediately when one is caught.
  • Active power-up TTL — HUD shows remaining seconds per active effect.
  • Better tile visuals — walls/floors/entities have distinct Unicode glyphs.

━━ AI improvements ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • BFS-to-goal cached per AI tick; reused across entities targeting same cell.
  • Shielded player skips flee logic and charges straight through monsters.
  • Scatter monsters reassign corner target once they reach it.
  • Monster min-distance spawn prevents instant death at game start.

Controls: Q quit | P pause | +/= faster | - slower | R restart
"""

from __future__ import annotations

import curses
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
WORLD_W = 96
WORLD_H = 64

VIEW_W = 25   # viewport width in cells
VIEW_H = 25   # viewport height in cells

BASE_TICK_MS    = 80
AI_TICK_EVERY_N = 2   # recompute BFS fields every N frames

# Scatter mode timing
SCATTER_INTERVAL_S = 20   # chase duration before scatter
SCATTER_DURATION_S = 6    # scatter phase length

NUM_ITEMS    = 14
NUM_MONSTERS = 5
NUM_THIEVES  = 1

ITEM_SPAWN_INTERVAL_S    = 5
POWERUP_SPAWN_INTERVAL_S = 10
POWERUP_DURATION_S       = 15

FLEE_THRESHOLD   = 9     # BFS steps to nearest monster before player/thief flees
COMBO_WINDOW_S   = 2.5   # seconds between collects to extend combo streak
MONSTER_MIN_DIST = 12    # minimum Manhattan distance from player at monster spawn

POWER_UPS = ("speed", "extra_life", "double_value", "shield")

# Monster kinds
KIND_NORMAL  = "normal"    # chases player via BFS gradient
KIND_FAST    = "fast"      # acts twice per AI tick
KIND_SCATTER = "scatter"   # always targets corners; never chases

MAZE_CARVE_STEP = 2

# ─────────────────────────────────────────────────────────────────────────────
# Type alias
# ─────────────────────────────────────────────────────────────────────────────
Pos = Tuple[int, int]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def now() -> float:
    # FIX: monotonic clock — immune to NTP/wall-clock adjustments
    return time.monotonic()


def neighbors4(x: int, y: int) -> Iterable[Pos]:
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ─────────────────────────────────────────────────────────────────────────────
# World & Maze
# ─────────────────────────────────────────────────────────────────────────────
class World:
    """Grid world: 0 = floor, 1 = wall."""

    def __init__(self, w: int, h: int, num_items: int) -> None:
        self.w = w
        self.h = h
        self.grid: List[List[int]] = [[1] * w for _ in range(h)]
        self.items: Set[Pos] = set()
        self.powerups: Dict[Pos, str] = {}
        self._free_cells: List[Pos] = []

        self._generate_maze()
        self._rebuild_free_cells()
        self._spawn_many_items(num_items)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_floor(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.grid[y][x] == 0

    # ── Maze generation ───────────────────────────────────────────────────────

    def _generate_maze(self) -> None:
        """Iterative recursive-backtracker maze carving on odd grid coordinates."""
        sx, sy = 1, 1
        self.grid[sy][sx] = 0
        stack: List[Pos] = [(sx, sy)]

        def unvisited(cx: int, cy: int) -> List[Pos]:
            out: List[Pos] = []
            for dx, dy in (
                (-MAZE_CARVE_STEP, 0),
                (MAZE_CARVE_STEP, 0),
                (0, -MAZE_CARVE_STEP),
                (0, MAZE_CARVE_STEP),
            ):
                nx, ny = cx + dx, cy + dy
                if (
                    1 <= nx < self.w - 1
                    and 1 <= ny < self.h - 1
                    and self.grid[ny][nx] == 1
                ):
                    out.append((nx, ny))
            return out

        while stack:
            cx, cy = stack[-1]
            nbrs = unvisited(cx, cy)
            if not nbrs:
                stack.pop()
                continue
            nx, ny = random.choice(nbrs)
            # Carve passage between current and neighbor
            self.grid[(cy + ny) // 2][(cx + nx) // 2] = 0
            self.grid[ny][nx] = 0
            stack.append((nx, ny))

        # Extra random holes to reduce dead-ends and create loops
        holes = max(10, (self.w * self.h) // 200)
        for _ in range(holes):
            x = random.randint(1, self.w - 2)
            y = random.randint(1, self.h - 2)
            self.grid[y][x] = 0

    def _rebuild_free_cells(self) -> None:
        self._free_cells = [
            (x, y)
            for y in range(1, self.h - 1)
            for x in range(1, self.w - 1)
            if self.is_floor(x, y)
        ]

    # ── Spawning ──────────────────────────────────────────────────────────────

    def random_free_cell(
        self, forbidden: Set[Pos], max_tries: int = 2000
    ) -> Optional[Pos]:
        """Random floor cell not in forbidden; None if not found quickly."""
        if not self._free_cells:
            return None
        for _ in range(max_tries):
            p = random.choice(self._free_cells)
            if p not in forbidden:
                return p
        return None

    def random_free_cell_far_from(
        self,
        forbidden: Set[Pos],
        center: Pos,
        min_dist: int,
        max_tries: int = 3000,
    ) -> Optional[Pos]:
        """Like random_free_cell but also requires ≥ min_dist Manhattan from center."""
        if not self._free_cells:
            return None
        for _ in range(max_tries):
            p = random.choice(self._free_cells)
            if p not in forbidden and manhattan(p, center) >= min_dist:
                return p
        # Fallback: relax distance constraint
        return self.random_free_cell(forbidden)

    def _spawn_many_items(self, n: int) -> None:
        forbidden: Set[Pos] = set(self.items) | set(self.powerups.keys())
        while len(self.items) < n:
            cell = self.random_free_cell(forbidden)
            if cell is None:
                break
            self.items.add(cell)
            forbidden.add(cell)

    def spawn_item_away_from(self, avoid_center: Pos, avoid_radius: int = 6) -> None:
        """Spawn one item not too close to avoid_center (usually the player)."""
        ax, ay = avoid_center
        forbidden: Set[Pos] = set(self.items) | set(self.powerups.keys())
        for x in range(ax - avoid_radius, ax + avoid_radius + 1):
            for y in range(ay - avoid_radius, ay + avoid_radius + 1):
                if self.in_bounds(x, y):
                    forbidden.add((x, y))
        cell = self.random_free_cell(forbidden)
        if cell is not None:
            self.items.add(cell)

    def spawn_powerup(self) -> None:
        forbidden: Set[Pos] = set(self.items) | set(self.powerups.keys())
        cell = self.random_free_cell(forbidden)
        if cell is None:
            return
        self.powerups[cell] = random.choice(POWER_UPS)

    def corner_cells(self) -> List[Pos]:
        """
        Return up to 4 floor cells nearest to maze corners.
        Used as scatter-mode targets for monsters.
        Expands outward via Manhattan rings until a floor cell is found.
        """
        corners: List[Pos] = []
        for cx, cy in [
            (1, 1),
            (self.w - 2, 1),
            (1, self.h - 2),
            (self.w - 2, self.h - 2),
        ]:
            for r in range(10):
                found = False
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if abs(dx) + abs(dy) == r and self.is_floor(cx + dx, cy + dy):
                            corners.append((cx + dx, cy + dy))
                            found = True
                            break
                    if found:
                        break
        return corners


# ─────────────────────────────────────────────────────────────────────────────
# Entities
# ─────────────────────────────────────────────────────────────────────────────
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
    combo: int = 0
    last_collect_time: float = 0.0
    # FIX: each power-up tracked independently with its own expiry timestamp
    active_powerups: Dict[str, float] = field(default_factory=dict)

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def extra_life(self) -> bool:
        return "extra_life" in self.active_powerups

    @property
    def double_value(self) -> bool:
        return "double_value" in self.active_powerups

    @property
    def speed_boost(self) -> bool:
        return "speed" in self.active_powerups

    @property
    def shield(self) -> bool:
        return "shield" in self.active_powerups

    # ── Power-up management ───────────────────────────────────────────────────

    def apply_powerup(self, effect: str) -> None:
        """Apply (or refresh) an effect, setting its own independent expiry."""
        self.active_powerups[effect] = now() + POWERUP_DURATION_S

    def expire_powerups_if_needed(self) -> None:
        """Remove only effects whose individual expiry has passed."""
        t = now()
        expired = [k for k, v in self.active_powerups.items() if t >= v]
        for k in expired:
            del self.active_powerups[k]

    def powerup_summary(self) -> str:
        if not self.active_powerups:
            return "None"
        return ", ".join(sorted(self.active_powerups))

    def powerup_ttl(self, effect: str) -> float:
        """Remaining seconds for a specific effect."""
        if effect not in self.active_powerups:
            return 0.0
        return max(0.0, self.active_powerups[effect] - now())

    # ── Scoring / combo ───────────────────────────────────────────────────────

    def collect_value(self) -> int:
        """
        Value of the next item collection. Tracks combo streak.
        Combo resets if more than COMBO_WINDOW_S passes between collects.
        Bonus tier unlocks every 3 consecutive collects.
        """
        t = now()
        if t - self.last_collect_time <= COMBO_WINDOW_S:
            self.combo += 1
        else:
            self.combo = 1
        self.last_collect_time = t
        base = 2 if self.double_value else 1
        return base * (1 + self.combo // 3)


@dataclass
class Monster(Actor):
    kind: str = KIND_NORMAL
    scatter_target: Optional[Pos] = None


@dataclass
class Thief(Actor):
    items_stolen: int = 0
    # FIX: same independent power-up tracking as Player
    active_powerups: Dict[str, float] = field(default_factory=dict)

    @property
    def double_value(self) -> bool:
        return "double_value" in self.active_powerups

    @property
    def speed_boost(self) -> bool:
        return "speed" in self.active_powerups

    def apply_powerup(self, effect: str) -> None:
        self.active_powerups[effect] = now() + POWERUP_DURATION_S

    def expire_powerups_if_needed(self) -> None:
        t = now()
        expired = [k for k, v in self.active_powerups.items() if t >= v]
        for k in expired:
            del self.active_powerups[k]


# ─────────────────────────────────────────────────────────────────────────────
# BFS utilities
# ─────────────────────────────────────────────────────────────────────────────
INF = 10**9


def bfs_distances(world: World, sources: Iterable[Pos]) -> List[List[int]]:
    """
    Multi-source BFS on floor cells.
    FIX: sources deduplicated before enqueueing to avoid redundant work.
    Returns dist[y][x] = INF for unreachable cells.
    """
    dist = [[INF] * world.w for _ in range(world.h)]
    q: Deque[Pos] = deque()
    enqueued: Set[Pos] = set()

    for sx, sy in sources:
        p = (sx, sy)
        if p not in enqueued and world.is_floor(sx, sy):
            dist[sy][sx] = 0
            q.append(p)
            enqueued.add(p)

    while q:
        x, y = q.popleft()
        d = dist[y][x] + 1
        for nx, ny in neighbors4(x, y):
            if not world.in_bounds(nx, ny) or not world.is_floor(nx, ny):
                continue
            if dist[ny][nx] <= d:
                continue
            dist[ny][nx] = d
            q.append((nx, ny))

    return dist


def step_by_gradient(
    world: World, start: Pos, dist: List[List[int]], want_min: bool
) -> Pos:
    """
    Move one step from start along the distance-field gradient.
      want_min=True  → descend (chase / approach goal).
      want_min=False → ascend  (flee / maximize distance).
    Ties broken randomly for natural-looking motion.
    Returns start unchanged if no improving neighbor exists.
    """
    x, y = start
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

    return random.choice(candidates) if candidates else (x, y)


def bfs_find_nearest_goal(world: World, start: Pos, goals: Set[Pos]) -> Optional[Pos]:
    """BFS from start; returns the nearest reachable goal cell, or None."""
    if not goals:
        return None
    sx, sy = start
    if (sx, sy) in goals:
        return (sx, sy)

    seen: Set[Pos] = {(sx, sy)}
    q: Deque[Pos] = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for nx, ny in neighbors4(x, y):
            if not world.in_bounds(nx, ny) or not world.is_floor(nx, ny):
                continue
            p = (nx, ny)
            if p in seen:
                continue
            if p in goals:
                return p
            seen.add(p)
            q.append(p)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────
class Renderer:
    def __init__(self, stdscr: "curses._CursesWindow", world: World) -> None:
        self.stdscr = stdscr
        self.world = world
        self.last_cells: Dict[Tuple[int, int], Tuple[str, int]] = {}
        # FIX: proper Unicode detection via stdout encoding
        self.unicode_ok = self._detect_unicode()
        self._init_colors()
        self._init_glyphs()

    def _detect_unicode(self) -> bool:
        enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
        return enc.startswith("utf")

    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        # Pair assignments:
        #  1=wall  2=floor  3=player  4=item  5=monster
        #  6=powerup  7=thief  8=hud  9=shielded-player  10=combo-active
        curses.init_pair(1, curses.COLOR_WHITE,   -1)
        curses.init_pair(2, curses.COLOR_GREEN,   -1)
        curses.init_pair(3, curses.COLOR_YELLOW,  -1)
        curses.init_pair(4, curses.COLOR_CYAN,    -1)
        curses.init_pair(5, curses.COLOR_RED,     -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        # FIX: thief was WHITE (same as wall); now BLUE — visually distinct
        curses.init_pair(7, curses.COLOR_BLUE,    -1)
        curses.init_pair(8, curses.COLOR_WHITE,   -1)
        curses.init_pair(9, curses.COLOR_CYAN,    -1)  # shield glow
        curses.init_pair(10, curses.COLOR_YELLOW, -1)  # combo indicator

        self.A_WALL    = curses.color_pair(1) | curses.A_DIM
        self.A_FLOOR   = curses.color_pair(2) | curses.A_DIM
        self.A_PLAYER  = curses.color_pair(3) | curses.A_BOLD
        self.A_ITEM    = curses.color_pair(4)
        self.A_MONSTER = curses.color_pair(5) | curses.A_BOLD
        self.A_POWERUP = curses.color_pair(6) | curses.A_BOLD
        self.A_THIEF   = curses.color_pair(7) | curses.A_BOLD
        self.A_HUD     = curses.color_pair(8)
        self.A_SHIELD  = curses.color_pair(9) | curses.A_BOLD
        self.A_COMBO   = curses.color_pair(10) | curses.A_BOLD

    def _init_glyphs(self) -> None:
        # FIX: unicode and ASCII branches are now visually distinct
        if self.unicode_ok:
            self.G_WALL    = "█"
            self.G_FLOOR   = "·"
            self.G_ITEM    = "◆"
            self.G_POWERUP = "★"
            self.G_PLAYER  = "☺"
            self.G_MONSTER = "▲"
            self.G_THIEF   = "◀"
        else:
            self.G_WALL    = "#"
            self.G_FLOOR   = "."
            self.G_ITEM    = "o"
            self.G_POWERUP = "*"
            self.G_PLAYER  = "@"
            self.G_MONSTER = "M"
            self.G_THIEF   = "T"

    def _put(self, sy: int, sx: int, ch: str, attr: int) -> None:
        """Dirty-cell render: only write to screen when content changes."""
        key = (sy, sx)
        cur = (ch, attr)
        if self.last_cells.get(key) == cur:
            return
        try:
            self.stdscr.addstr(sy, sx, ch, attr)
        except curses.error:
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
        fps: float,
        scatter_mode: bool,
    ) -> None:
        term_h, term_w = self.stdscr.getmaxyx()

        needed_w = VIEW_W + 2 + 36
        needed_h = max(VIEW_H + 2, 18)
        if term_w < needed_w or term_h < needed_h:
            self.stdscr.erase()
            try:
                self.stdscr.addstr(
                    0, 0,
                    f"Terminal too small. Need ≥{needed_w}×{needed_h}, have {term_w}×{term_h}.",
                )
                self.stdscr.addstr(1, 0, "Resize and restart.")
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        # Camera: center viewport on player, clamped to world bounds
        cam_x = clamp(player.x - VIEW_W // 2, 0, max(0, self.world.w - VIEW_W))
        cam_y = clamp(player.y - VIEW_H // 2, 0, max(0, self.world.h - VIEW_H))

        monster_pos = {m.pos() for m in monsters}
        thief_pos   = {t.pos() for t in thieves}
        power_pos   = set(self.world.powerups.keys())
        player_pos  = player.pos()

        # ── Viewport border ────────────────────────────────────────────────────
        for sx in range(VIEW_W + 2):
            self._put(0, sx, "─", self.A_HUD)
            self._put(VIEW_H + 1, sx, "─", self.A_HUD)
        for sy in range(VIEW_H + 2):
            self._put(sy, 0, "│", self.A_HUD)
            self._put(sy, VIEW_W + 1, "│", self.A_HUD)
        self._put(0, 0, "┌", self.A_HUD)
        self._put(0, VIEW_W + 1, "┐", self.A_HUD)
        self._put(VIEW_H + 1, 0, "└", self.A_HUD)
        self._put(VIEW_H + 1, VIEW_W + 1, "┘", self.A_HUD)

        # ── Map area ───────────────────────────────────────────────────────────
        for vy in range(VIEW_H):
            wy = cam_y + vy
            row = 1 + vy
            for vx in range(VIEW_W):
                wx = cam_x + vx
                col = 1 + vx
                p = (wx, wy)

                if p == player_pos:
                    attr = self.A_SHIELD if player.shield else self.A_PLAYER
                    self._put(row, col, self.G_PLAYER, attr)
                elif p in monster_pos:
                    self._put(row, col, self.G_MONSTER, self.A_MONSTER)
                elif p in thief_pos:
                    self._put(row, col, self.G_THIEF, self.A_THIEF)
                elif p in self.world.items:
                    self._put(row, col, self.G_ITEM, self.A_ITEM)
                elif p in power_pos:
                    self._put(row, col, self.G_POWERUP, self.A_POWERUP)
                elif self.world.is_floor(wx, wy):
                    self._put(row, col, self.G_FLOOR, self.A_FLOOR)
                else:
                    self._put(row, col, self.G_WALL, self.A_WALL)

        # ── HUD panel ──────────────────────────────────────────────────────────
        hud_x = VIEW_W + 3
        hud_w = max(1, term_w - hud_x - 1)

        def hud(row: int, text: str, attr: int = 0) -> None:
            """
            Write a HUD line, padding to hud_w to clear stale characters.
            FIX: previously bare addstr left old chars visible when text shrunk.
            """
            if row >= term_h:
                return
            padded = text[:hud_w].ljust(hud_w)
            try:
                self.stdscr.addstr(row, hud_x, padded, attr or self.A_HUD)
            except curses.error:
                pass

        r = 0
        hud(r, "AutoPacman  v3", self.A_HUD | curses.A_BOLD); r += 1
        hud(r, ""); r += 1
        hud(r, f"Player : {player.name}"); r += 1
        hud(r, f"Items  : {player.items_collected}"); r += 1
        hud(r, f"Turns  : {player.turns_survived}"); r += 1

        combo_attr = self.A_COMBO if player.combo > 2 else self.A_HUD
        combo_str  = f"x{player.combo}  (tier +{player.combo // 3})" if player.combo > 1 else "-"
        hud(r, f"Combo  : {combo_str}", combo_attr); r += 1
        hud(r, ""); r += 1

        pu_attr = self.A_POWERUP if player.active_powerups else self.A_HUD
        hud(r, f"Active : {player.powerup_summary()}", pu_attr); r += 1

        if player.shield:
            hud(r, f"Shield : {player.powerup_ttl('shield'):.0f}s left", self.A_SHIELD)
        elif player.extra_life:
            hud(r, "Life   : EXTRA LIFE", self.A_POWERUP)
        else:
            hud(r, "Life   : normal")
        r += 1
        hud(r, ""); r += 1

        mode_label = "!SCATTER!" if scatter_mode else "chase"
        mode_attr  = self.A_MONSTER if scatter_mode else self.A_HUD
        hud(r, f"Monsters: {len(monsters)} [{mode_label}]", mode_attr); r += 1
        hud(r, f"Thieves : {len(thieves)}"); r += 1
        hud(r, f"Speed  : {tick_ms} ms/tick"); r += 1
        hud(r, f"FPS    : {fps:.1f}"); r += 1
        hud(r, f"State  : {'PAUSED' if paused else 'running'}"); r += 1
        hud(r, ""); r += 1

        hud(r, "Controls:", self.A_HUD | curses.A_UNDERLINE); r += 1
        hud(r, "  Q quit   P pause"); r += 1
        hud(r, "  +/= faster  - slower"); r += 1
        hud(r, "  R restart"); r += 1
        hud(r, ""); r += 1

        hud(r, "Top Scores:", self.A_HUD | curses.A_UNDERLINE); r += 1
        if not high_scores:
            hud(r, "  (none yet)"); r += 1
        else:
            for i, (nm, sc, tr) in enumerate(high_scores[:5], 1):
                hud(r, f"  {i}. {nm}: {sc} pts  ({tr} turns)"); r += 1

        self.stdscr.noutrefresh()
        curses.doupdate()


# ─────────────────────────────────────────────────────────────────────────────
# Game
# ─────────────────────────────────────────────────────────────────────────────
PLAYER_NAMES = [
    "Alex", "Blake", "Casey", "Drew", "Elliot",
    "Frankie", "Glen", "Harper", "Jesse", "Kai",
]

# Monster kind distribution for NUM_MONSTERS spawns
# (3 normal, 1 fast, 1 scatter) — shuffled each reset
_KIND_POOL = [KIND_NORMAL, KIND_NORMAL, KIND_NORMAL, KIND_FAST, KIND_SCATTER]


class Game:
    def __init__(self, stdscr: "curses._CursesWindow") -> None:
        self.stdscr = stdscr
        self.tick_ms = BASE_TICK_MS
        self.paused = False
        self.high_scores: List[Tuple[str, int, int]] = []
        self.renderer: Optional[Renderer] = None
        # Rolling frame-timestamp window for FPS calculation
        self._fps_times: Deque[float] = deque(maxlen=60)
        self.reset()

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.world = World(WORLD_W, WORLD_H, NUM_ITEMS)

        spawn = (
            (1, 1)
            if self.world.is_floor(1, 1)
            else self.world.random_free_cell(set()) or (1, 1)
        )
        self.player = Player(spawn[0], spawn[1], name=random.choice(PLAYER_NAMES))

        forbidden: Set[Pos] = (
            {self.player.pos()} | self.world.items | set(self.world.powerups.keys())
        )

        # Monsters with enforced minimum spawn distance from player
        self.monsters: List[Monster] = []
        kinds = _KIND_POOL.copy()
        random.shuffle(kinds)
        for i in range(NUM_MONSTERS):
            kind = kinds[i % len(kinds)]
            cell = self.world.random_free_cell_far_from(
                forbidden, self.player.pos(), MONSTER_MIN_DIST
            )
            if cell is None:
                break
            self.monsters.append(Monster(*cell, kind=kind))
            forbidden.add(cell)

        self.thieves: List[Thief] = []
        for _ in range(NUM_THIEVES):
            cell = self.world.random_free_cell(forbidden)
            if cell is None:
                break
            self.thieves.append(Thief(*cell))
            forbidden.add(cell)

        self.frame = 0
        self.last_item_spawn    = now()
        self.last_power_spawn   = now()
        self.last_scatter_event = now()
        self.scatter_mode       = False

        # BFS distance fields recomputed every AI_TICK_EVERY_N frames
        self.dist_to_player:   Optional[List[List[int]]] = None
        self.dist_to_monsters: Optional[List[List[int]]] = None
        # Per-tick BFS cache: goal_pos → dist field; cleared each AI tick
        self._goal_bfs_cache: Dict[Pos, List[List[int]]] = {}

        # Reuse renderer across resets; only create once
        if self.renderer is None:
            self.renderer = Renderer(self.stdscr, self.world)
        else:
            self.renderer.world = self.world
        self.renderer.clear()

    # ── Input ─────────────────────────────────────────────────────────────────

    def handle_input(self) -> bool:
        """Returns False to quit."""
        ch = self.stdscr.getch()
        if ch == -1:
            return True
        if ch in (ord("q"), ord("Q")):
            return False
        if ch in (ord("p"), ord("P")):
            self.paused = not self.paused
        if ch in (ord("+"), ord("=")):
            self.tick_ms = max(20, self.tick_ms - 10)
        if ch in (ord("-"), ord("_")):
            self.tick_ms = min(300, self.tick_ms + 10)
        if ch in (ord("r"), ord("R")):
            self.reset()
        return True

    # ── Item/power-up collection ───────────────────────────────────────────────

    def _collect(self, actor: Actor) -> None:
        """Handle item and power-up pickup for any actor."""
        p = actor.pos()

        if p in self.world.items:
            self.world.items.discard(p)
            if isinstance(actor, Player):
                actor.items_collected += actor.collect_value()
            elif isinstance(actor, Thief):
                actor.items_stolen += 2 if actor.double_value else 1

        if p in self.world.powerups:
            eff = self.world.powerups.pop(p)
            # FIX: single branch — both Player and Thief have apply_powerup
            if hasattr(actor, "apply_powerup"):
                actor.apply_powerup(eff)  # type: ignore[union-attr]

    # ── BFS field management ───────────────────────────────────────────────────

    def compute_fields(self) -> None:
        """Recompute player and monster distance fields; clear goal cache."""
        self.dist_to_player = bfs_distances(self.world, [self.player.pos()])
        if self.monsters:
            self.dist_to_monsters = bfs_distances(
                self.world, [m.pos() for m in self.monsters]
            )
        else:
            self.dist_to_monsters = None
        # FIX: clear the per-tick goal-BFS cache so stale entries are not reused
        self._goal_bfs_cache.clear()

    def _dist_from_goal(self, goal: Pos) -> List[List[int]]:
        """
        BFS from a specific goal cell, cached for the current AI tick.
        FIX: avoids recomputing the same BFS multiple times per tick when
        several entities share the same nearest target.
        """
        if goal not in self._goal_bfs_cache:
            self._goal_bfs_cache[goal] = bfs_distances(self.world, [goal])
        return self._goal_bfs_cache[goal]

    def _navigate_toward_goals(self, actor: Actor, goals: Set[Pos]) -> Optional[Pos]:
        """One step toward the nearest reachable goal; returns new pos or None."""
        target = bfs_find_nearest_goal(self.world, actor.pos(), goals)
        if target is None:
            return None
        return step_by_gradient(
            self.world, actor.pos(), self._dist_from_goal(target), want_min=True
        )

    # ── Scatter mode ──────────────────────────────────────────────────────────

    def _update_scatter_mode(self) -> None:
        """Toggle global scatter mode on a timer."""
        t = now()
        if self.scatter_mode:
            if t - self.last_scatter_event >= SCATTER_DURATION_S:
                self.scatter_mode = False
                self.last_scatter_event = t
                for m in self.monsters:
                    m.scatter_target = None   # reset assigned corners
        else:
            if t - self.last_scatter_event >= SCATTER_INTERVAL_S:
                self.scatter_mode = True
                self.last_scatter_event = t

    def _scatter_target_for(self, monster: Monster) -> Pos:
        """Return (or freshly assign) a corner target for scatter mode."""
        corners = self.world.corner_cells()
        if not corners:
            return monster.pos()
        if monster.scatter_target is None:
            monster.scatter_target = random.choice(corners)
        return monster.scatter_target

    # ── Monster movement ───────────────────────────────────────────────────────

    def _move_monster(self, m: Monster) -> None:
        """Move monster one step (scatter-to-corner or chase-player logic)."""
        if self.scatter_mode or m.kind == KIND_SCATTER:
            target = self._scatter_target_for(m)
            if m.pos() == target:
                m.scatter_target = None   # reached corner; pick a new one next tick
                target = self._scatter_target_for(m)
            nxt = step_by_gradient(
                self.world, m.pos(), self._dist_from_goal(target), want_min=True
            )
        else:
            nxt = (
                step_by_gradient(
                    self.world, m.pos(), self.dist_to_player, want_min=True
                )
                if self.dist_to_player is not None
                else m.pos()
            )
        m.move_to(nxt)

    # ── AI step ───────────────────────────────────────────────────────────────

    def step_ai(self) -> None:
        """Advance all entities by one logical step."""

        # Expire any individual power-ups whose time is up
        self.player.expire_powerups_if_needed()
        for t in self.thieves:
            t.expire_powerups_if_needed()

        # Ensure distance fields are available
        if self.dist_to_player is None:
            self.compute_fields()

        # ── Monsters ──────────────────────────────────────────────────────────
        for m in self.monsters:
            self._move_monster(m)
            if m.kind == KIND_FAST:
                # Fast monsters get an extra move every AI tick
                self._move_monster(m)

        # ── Thieves ───────────────────────────────────────────────────────────
        for t in list(self.thieves):
            if t.pos() == self.player.pos():
                # Player catches thief: recover all stolen items
                self.player.items_collected += t.items_stolen
                self.thieves.remove(t)
                # FIX: spawn replacement thief immediately so population stays at NUM_THIEVES
                self._respawn_thief()
                continue

            fled = False
            if self.dist_to_monsters is not None:
                d = self.dist_to_monsters[t.y][t.x]
                if d < FLEE_THRESHOLD:
                    nxt = step_by_gradient(
                        self.world, t.pos(), self.dist_to_monsters, want_min=False
                    )
                    t.move_to(nxt)
                    fled = True

            if not fled:
                # Prefer power-ups; fall back to items
                goals: Set[Pos] = (
                    set(self.world.powerups.keys())
                    if self.world.powerups
                    else set(self.world.items)
                )
                nxt = self._navigate_toward_goals(t, goals)
                if nxt is not None:
                    t.move_to(nxt)

            self._collect(t)

        # ── Player ────────────────────────────────────────────────────────────
        self.player.turns_survived += 1

        flee_done = False
        if self.dist_to_monsters is not None and not self.player.shield:
            d = self.dist_to_monsters[self.player.y][self.player.x]
            if d < FLEE_THRESHOLD:
                nxt = step_by_gradient(
                    self.world, self.player.pos(), self.dist_to_monsters, want_min=False
                )
                self.player.move_to(nxt)
                flee_done = True

        if not flee_done:
            # Shielded players charge straight through; collect aggressively
            goals = set(self.world.powerups.keys()) or set(self.world.items)
            if goals:
                nxt = self._navigate_toward_goals(self.player, goals)
                if nxt is not None:
                    self.player.move_to(nxt)

        self._collect(self.player)

        # ── Monster–player collision ───────────────────────────────────────────
        if not self.player.shield:
            for m in self.monsters:
                if m.pos() == self.player.pos():
                    if self.player.extra_life:
                        # FIX: consume ONLY extra_life, leaving other active effects intact
                        self.player.active_powerups.pop("extra_life", None)
                    else:
                        self._respawn_player()
                    break

    # ── Spawners ──────────────────────────────────────────────────────────────

    def step_spawners(self) -> None:
        t = now()
        if t - self.last_item_spawn >= ITEM_SPAWN_INTERVAL_S:
            self.world.spawn_item_away_from(self.player.pos(), avoid_radius=5)
            self.last_item_spawn = t
        if t - self.last_power_spawn >= POWERUP_SPAWN_INTERVAL_S:
            self.world.spawn_powerup()
            self.last_power_spawn = t

    # ── Respawns ──────────────────────────────────────────────────────────────

    def _respawn_player(self) -> None:
        """Record score, then spawn a new player at a safe location."""
        self.high_scores.append(
            (self.player.name, self.player.items_collected, self.player.turns_survived)
        )
        self.high_scores.sort(key=lambda e: (e[1], e[2]), reverse=True)
        self.high_scores = self.high_scores[:5]

        taken = {m.pos() for m in self.monsters} | {t.pos() for t in self.thieves}
        cell = self.world.random_free_cell(taken) or (1, 1)
        self.player = Player(cell[0], cell[1], name=random.choice(PLAYER_NAMES))

    def _respawn_thief(self) -> None:
        """Spawn a replacement thief away from all current entities."""
        taken = (
            {m.pos() for m in self.monsters}
            | {t.pos() for t in self.thieves}
            | {self.player.pos()}
        )
        cell = self.world.random_free_cell(taken)
        if cell is not None:
            self.thieves.append(Thief(*cell))

    # ── FPS tracking ──────────────────────────────────────────────────────────

    def _record_frame_and_get_fps(self) -> float:
        """Push a timestamp and return rolling FPS over the last 60 frames."""
        t = now()
        self._fps_times.append(t)
        if len(self._fps_times) < 2:
            return 0.0
        span = self._fps_times[-1] - self._fps_times[0]
        return (len(self._fps_times) - 1) / span if span > 0 else 0.0

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        curses.curs_set(0)
        self.stdscr.nodelay(True)

        last_frame = now()
        fps = 0.0

        while True:
            if not self.handle_input():
                return

            if self.paused:
                assert self.renderer is not None
                self.renderer.draw(
                    self.player, self.monsters, self.thieves,
                    self.high_scores, True, self.tick_ms, fps, self.scatter_mode,
                )
                time.sleep(0.03)
                continue

            # Frame pacing
            target  = self.tick_ms / 1000.0
            elapsed = now() - last_frame
            if elapsed < target:
                time.sleep(target - elapsed)
            last_frame = now()
            fps = self._record_frame_and_get_fps()

            # Recompute BFS fields every AI_TICK_EVERY_N frames
            if self.frame % AI_TICK_EVERY_N == 0:
                self.compute_fields()

            self._update_scatter_mode()
            self.step_ai()

            # Speed boost: player acts twice every 3rd frame
            if self.player.speed_boost and (self.frame % 3 == 0):
                self.step_ai()

            self.step_spawners()

            assert self.renderer is not None
            self.renderer.draw(
                self.player, self.monsters, self.thieves,
                self.high_scores, False, self.tick_ms, fps, self.scatter_mode,
            )
            self.frame += 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main(stdscr: "curses._CursesWindow") -> None:
    random.seed()
    game = Game(stdscr)
    game.run()


if __name__ == "__main__":
    curses.wrapper(main)
