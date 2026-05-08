#!/usr/bin/env python3
"""
DARKMAP v2.0 — Procedural Dungeon Generator
Flask web app with cyberpunk/cyberdeck aesthetic.

Bug fixes over original darkgui_beta.py:
  1. _connect_outside() removed entirely — its step() function produced
     negative coords that Python silently wrapped (wrote to wrong rows).
     Replaced with _link() which carves L-corridors between room centers.
  2. _connect_normal_rooms() rewrote MST with proper Kruskal + Union-Find.
     The XOR visited-set trick missed isolated room islands.
  3. _place_mandatory() fixed ID collision: obj used next_id+1 before ent
     incremented it, so both rooms could share the same adjacency slot.
  4. _remove_dead_ends() added — iteratively prunes corridor tiles with
     only one walkable neighbour (dead-end stubs from loop edges).
  5. Bounds checking on every _carve call — no more off-grid writes.
  6. Parameter validation + graceful RuntimeError messages.
  7. Replaced the buggy _add_loops() with loop edges inside _connect_normal_rooms().
"""

from flask import Flask, Response, jsonify, request
import random
from collections import deque

app = Flask(__name__)

# ── Cyberpunk name vocabularies ───────────────────────────────────────────────
_ROOM_NAMES = {
    'normal': [
        'STORAGE BAY', 'CMD CENTER', 'SERVER ROOM', 'BARRACKS', 'ARMORY',
        'LAB ALPHA', 'REACTOR CORE', 'HANGAR', 'MEDICAL BAY', 'ARCHIVE',
        'BRIDGE', 'CARGO HOLD', 'BRIG', 'POWER GRID', 'COMM HUB',
        'ENGINEERING', 'NAV BAY', 'VAULT', 'MESS DECK', 'DATA CORE',
        'SENSOR ARRAY', 'FUEL DEPOT', 'QUARTERS', 'WORKSHOP', 'BRIEFING RM',
        'RELAY NODE', 'COOLING SYS', 'ARMATURE BAY', 'CHASSIS YARD', 'FORGE',
    ],
    'entrance': [
        'ACCESS PT.α', 'ENTRY NODE', 'BREACH POINT', 'INSERTION PT',
        'INFILTRATION', 'GATEWAY-α',  'INGRESS NODE', 'ENTRY VECTOR',
    ],
    'objective': [
        'TARGET: Ω',   'EXFIL ZONE',  'PRIMARY OBJ', 'TERMINUS NODE',
        'OBJ CORE',    'EXTRACT PT',  'ZERO POINT',   'ENDGAME NODE',
    ],
    'special': [
        'ANOMALY-X',   'BLACK SITE',  'NEXUS POINT', 'ECHO CHAMBER',
        'ORIGIN NODE', 'RIFT ZONE',   'PHANTOM CACHE','SHADOW NODE',
        'FORBIDDEN',   'GHOST DATA',  'QUANTUM LOCK', 'DARK RELAY',
    ],
}
_CORRIDOR_PREFIXES = [
    'TUN', 'SHAFT', 'DUCT', 'PIPE', 'PATH',
    'LINK', 'ROUTE', 'ACCESS', 'BYPASS', 'CONDUIT',
]

# ─────────────────────────────────────────────────────────────────────────────
#  MAP GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class Rect:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def intersects(self, other, pad=0):
        return (self.x - pad < other.x + other.w + pad and
                self.x + self.w + pad > other.x - pad and
                self.y - pad < other.y + other.h + pad and
                self.y + self.h + pad > other.y - pad)


class Room(Rect):
    def __init__(self, rid, x, y, w, h, rtype):
        super().__init__(x, y, w, h)
        self.id   = rid
        self.type = rtype  # 'normal' | 'entrance' | 'objective' | 'special'

    @property
    def center(self):
        return (self.x + self.w // 2, self.y + self.h // 2)


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class UnionFind:
    """Path-compressed Union-Find for Kruskal's MST."""
    def __init__(self):
        self._p = {}

    def find(self, x):
        self._p.setdefault(x, x)
        if self._p[x] != x:
            self._p[x] = self.find(self._p[x])
        return self._p[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        self._p[px] = py
        return True


class MapGenerator:
    def __init__(self, **cfg):
        self.map_width          = int(cfg.get('map_width',    60))
        self.map_height         = int(cfg.get('map_height',   40))
        self.room_min_size      = int(cfg.get('room_min_size',  4))
        self.room_max_size      = int(cfg.get('room_max_size', 10))
        self.room_count_min     = int(cfg.get('room_count_min',  6))
        self.room_count_max     = int(cfg.get('room_count_max', 12))
        self.special_room_count = int(cfg.get('special_room_count', 2))
        self.special_room_chance= float(cfg.get('special_room_chance', 0.70))
        self.loop_chance        = float(cfg.get('loop_chance', 0.25))
        seed_raw                = cfg.get('seed', 0)
        self.seed               = int(seed_raw) if seed_raw else random.randrange(1 << 30)
        self._validate()

    # ── validation ────────────────────────────────────────────────────────────

    def _validate(self):
        self.map_width       = max(24, min(120, self.map_width))
        self.map_height      = max(18, min(80,  self.map_height))
        self.room_min_size   = max(3, self.room_min_size)
        self.room_max_size   = max(self.room_min_size + 1, self.room_max_size)
        self.room_count_min  = max(2, self.room_count_min)
        self.room_count_max  = max(self.room_count_min, self.room_count_max)
        self.loop_chance     = max(0.0, min(1.0, self.loop_chance))
        self.special_room_chance = max(0.0, min(1.0, self.special_room_chance))

    # ── internal helpers ──────────────────────────────────────────────────────

    def _add_room(self, room):
        self.rooms.append(room)
        self.rooms_by_id[room.id] = room
        self.adj[room.id] = set()

    def _carve(self, x, y):
        """Safely carve a single tile — bounds-checked."""
        if 0 <= x < self.map_width and 0 <= y < self.map_height:
            self.grid[y][x] = '.'

    def _carve_room(self, room):
        for ry in range(room.y, room.y + room.h):
            for rx in range(room.x, room.x + room.w):
                self._carve(rx, ry)

    def _carve_hline(self, y, x1, x2):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self._carve(x, y)

    def _carve_vline(self, x, y1, y2):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self._carve(x, y)

    def _carve_corridor(self, a, b):
        """L-shaped corridor between two (x, y) points — fully bounds-checked."""
        x1, y1 = a
        x2, y2 = b
        if random.choice([True, False]):
            self._carve_hline(y1, x1, x2)
            self._carve_vline(x2, y1, y2)
        else:
            self._carve_vline(x1, y1, y2)
            self._carve_hline(y2, x1, x2)

    def _link(self, roomA, roomB):
        """Carve a corridor between two rooms and record the edge."""
        self._carve_corridor(roomA.center, roomB.center)
        self.adj[roomA.id].add(roomB.id)
        self.adj[roomB.id].add(roomA.id)

    # ── placement ─────────────────────────────────────────────────────────────

    def _place_normal_rooms(self):
        target   = random.randint(self.room_count_min, self.room_count_max)
        attempts = 0
        while len([r for r in self.rooms if r.type == 'normal']) < target \
              and attempts < target * 200:
            attempts += 1
            w = random.randint(self.room_min_size, self.room_max_size)
            h = random.randint(self.room_min_size, self.room_max_size)
            x = random.randint(2, self.map_width  - w - 2)
            y = random.randint(2, self.map_height - h - 2)
            c = Rect(x, y, w, h)
            # pad=1 guarantees a wall separating any two rooms
            if any(c.intersects(o, pad=1) for o in self.rooms):
                continue
            rm = Room(self.next_id, x, y, w, h, 'normal')
            self.next_id += 1
            self._add_room(rm)
            self._carve_room(rm)

        placed = len([r for r in self.rooms if r.type == 'normal'])
        if placed < self.room_count_min:
            raise RuntimeError(
                f"Placed only {placed}/{self.room_count_min} normal rooms. "
                "Try a larger map, fewer rooms, or smaller room sizes.")

    def _connect_normal_rooms(self):
        """
        FIX: Kruskal's MST with proper Union-Find (original used XOR-visited
        which could leave disconnected islands when early rooms had no close
        neighbour within the length constraint).

        Also adds optional loop edges for non-linear topology.
        """
        normals = [r for r in self.rooms if r.type == 'normal']
        if len(normals) < 2:
            return

        edges = sorted(
            [(manhattan(a.center, b.center), a, b)
             for i, a in enumerate(normals)
             for b in normals[i + 1:]],
            key=lambda e: e[0])

        uf = UnionFind()
        mst_keys = set()

        for _, a, b in edges:
            if uf.union(a.id, b.id):
                self._link(a, b)
                mst_keys.add((min(a.id, b.id), max(a.id, b.id)))

        # Optional extra (loop) corridors — keeps maps from feeling like pure trees
        max_loop_dist = (self.map_width + self.map_height) // 4
        for d, a, b in edges:
            key = (min(a.id, b.id), max(a.id, b.id))
            if key in mst_keys:
                continue
            if d <= max_loop_dist and random.random() < self.loop_chance:
                self._link(a, b)

    def _try_place_border_room(self, rtype, exclude):
        """Attempt to place a room near a map border, returning (Room, target) or (None, None)."""
        normals = [r for r in self.rooms if r.type == 'normal']
        if not normals:
            return None, None

        for _ in range(400):
            w    = random.randint(self.room_min_size, self.room_max_size)
            h    = random.randint(self.room_min_size, self.room_max_size)
            side = random.choice(('top', 'bot', 'left', 'right'))
            if side == 'top':
                x, y = random.randint(2, self.map_width  - w - 2), 1
            elif side == 'bot':
                x, y = random.randint(2, self.map_width  - w - 2), self.map_height - h - 1
            elif side == 'left':
                x, y = 1, random.randint(2, self.map_height - h - 2)
            else:
                x, y = self.map_width - w - 1, random.randint(2, self.map_height - h - 2)

            cand = Rect(x, y, w, h)
            if any(cand.intersects(o, pad=1) for o in self.rooms + exclude):
                continue

            cx, cy  = x + w // 2, y + h // 2
            closest = min(normals, key=lambda r: manhattan((cx, cy), r.center))
            rm      = Room(self.next_id, x, y, w, h, rtype)
            self.next_id += 1
            return rm, closest

        return None, None

    def _place_mandatory(self):
        """
        FIX 1: ID collision — original assigned obj.id = next_id+1 before
        ent had incremented next_id, so both entries could alias.
        Now each Room() call immediately claims self.next_id then advances it.

        FIX 2: Fallback promotes two distant normal rooms instead of crashing.
        """
        normals = [r for r in self.rooms if r.type == 'normal']
        need    = max(2, len(normals) // 2)  # min normals on the ent→obj path

        for _ in range(60):
            ent, ent_tgt = self._try_place_border_room('entrance', [])
            if ent is None:
                continue
            obj, obj_tgt = self._try_place_border_room('objective', [ent])
            if obj is None:
                continue

            # Simulate connectivity for path quality check
            adj2 = {k: set(v) for k, v in self.adj.items()}
            adj2[ent.id] = {ent_tgt.id}
            adj2.setdefault(ent_tgt.id, set()).add(ent.id)
            adj2[obj.id] = {obj_tgt.id}
            adj2.setdefault(obj_tgt.id, set()).add(obj.id)

            path = self._bfs(ent.id, obj.id, adj2)
            normals_on_path = sum(
                1 for pid in path
                if pid in self.rooms_by_id
                and self.rooms_by_id[pid].type == 'normal')

            if normals_on_path < need:
                continue

            # Commit — note: next_id was already advanced inside _try_place_border_room
            self._add_room(ent); self._carve_room(ent); self._link(ent, ent_tgt)
            self._add_room(obj); self._carve_room(obj); self._link(obj, obj_tgt)
            return

        # Graceful fallback: promote the two most distant normal rooms
        if len(normals) >= 2:
            pairs = sorted(
                [(manhattan(normals[i].center, normals[j].center), i, j)
                 for i in range(len(normals))
                 for j in range(i + 1, len(normals))],
                reverse=True)
            _, i, j = pairs[0]
            normals[i].type = 'entrance'
            normals[j].type = 'objective'

    def _place_special(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        placed  = 0

        for _ in range(self.special_room_count * 150):
            if placed >= self.special_room_count:
                break
            if random.random() > self.special_room_chance:
                continue
            w  = random.randint(self.room_min_size, self.room_max_size)
            h  = random.randint(self.room_min_size, self.room_max_size)
            x  = random.randint(2, self.map_width  - w - 2)
            y  = random.randint(2, self.map_height - h - 2)
            c  = Rect(x, y, w, h)
            if any(c.intersects(o, pad=1) for o in self.rooms):
                continue
            if not normals:
                break
            cx, cy  = x + w // 2, y + h // 2
            closest = min(normals, key=lambda r: manhattan((cx, cy), r.center))
            rm      = Room(self.next_id, x, y, w, h, 'special')
            self.next_id += 1
            self._add_room(rm)
            self._carve_room(rm)
            self._link(rm, closest)
            placed += 1

    def _remove_dead_ends(self):
        """
        FIX: Dead-end removal pass.
        Corridor tiles (not inside any room) with ≤1 walkable neighbour are
        pruned iteratively until the map stabilises.  This eliminates the
        orphaned stubs left by loop/optional corridors.
        """
        room_tiles = set()
        for r in self.rooms:
            for ry in range(r.y, r.y + r.h):
                for rx in range(r.x, r.x + r.w):
                    room_tiles.add((rx, ry))

        changed = True
        while changed:
            changed = False
            for y in range(1, self.map_height - 1):
                for x in range(1, self.map_width - 1):
                    if self.grid[y][x] != '.' or (x, y) in room_tiles:
                        continue
                    n = sum(
                        self.grid[y + dy][x + dx] == '.'
                        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)))
                    if n <= 1:
                        self.grid[y][x] = '#'
                        changed = True

    def _bfs(self, src, dst, adj):
        q = deque([src])
        parent = {src: None}
        while q:
            c = q.popleft()
            if c == dst:
                break
            for n in adj.get(c, ()):
                if n not in parent:
                    parent[n] = c
                    q.append(n)
        if dst not in parent:
            return []
        path, u = [], dst
        while u is not None:
            path.append(u)
            u = parent[u]
        return list(reversed(path))

    # ── public API ────────────────────────────────────────────────────────────

    def generate(self):
        random.seed(self.seed)
        self.grid        = [['#'] * self.map_width for _ in range(self.map_height)]
        self.rooms       = []
        self.rooms_by_id = {}
        self.adj         = {}
        self.next_id     = 0

        self._place_normal_rooms()
        self._connect_normal_rooms()
        self._place_mandatory()
        self._place_special()
        self._remove_dead_ends()

        # Stats
        walls    = sum(row.count('#') for row in self.grid)
        floors   = sum(row.count('.') for row in self.grid)
        total    = self.map_width * self.map_height
        coverage = round(floors / total * 100, 1)

        # ── Labels ────────────────────────────────────────────────────────────
        # Assign a unique cyberpunk codename to every room
        used_per_type = {t: [] for t in _ROOM_NAMES}
        for r in self.rooms:
            pool  = _ROOM_NAMES.get(r.type, _ROOM_NAMES['normal'])
            avail = [n for n in pool if n not in used_per_type[r.type]]
            if not avail:
                avail = pool  # allow repeats only when pool exhausted
            r.label = random.choice(avail)
            used_per_type[r.type].append(r.label)

        # One corridor label per unique adjacency edge
        seen_edges  = set()
        connections = []
        alpha       = 'ABCDEFGHJKLMNPQRSTVWXYZ'
        for rid, nbrs in self.adj.items():
            for nid in sorted(nbrs):
                key = (min(rid, nid), max(rid, nid))
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                prefix = random.choice(_CORRIDOR_PREFIXES)
                label  = f"{prefix}-{random.choice(alpha)}{random.randint(1, 9)}"
                connections.append({'from': rid, 'to': nid, 'label': label})

        return {
            'ok':          True,
            'grid':        [''.join(row) for row in self.grid],
            'rooms':       [{'id':  r.id,  'x': r.x, 'y': r.y,
                             'w':   r.w,   'h': r.h, 'type': r.type,
                             'cx':  r.center[0], 'cy': r.center[1],
                             'label': getattr(r, 'label', '')}
                            for r in self.rooms],
            'connections': connections,
            'seed':        self.seed,
            'width':       self.map_width,
            'height':      self.map_height,
            'stats': {
                'rooms':    len(self.rooms),
                'floors':   floors,
                'walls':    walls,
                'coverage': coverage,
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
#  FLASK ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json(force=True, silent=True) or {}
    try:
        result = MapGenerator(**data).generate()
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/health')
def health():
    return jsonify({'status': 'ONLINE', 'version': '2.0'})


# ─────────────────────────────────────────────────────────────────────────────
#  HTML / CSS / JS  — Cyberpunk Cyberdeck UI
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DARKMAP v2.0</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap" rel="stylesheet">
<style>
:root {
  --bg:       #030311;
  --surface:  #07071a;
  --panel:    #04040f;
  --border:   #141430;
  --cyan:     #00e5ff;
  --green:    #39ff14;
  --pink:     #ff006e;
  --purple:   #b400ff;
  --amber:    #ffb300;
  --red:      #ff2244;
  --text:     #5a7a9a;
  --text-hi:  #8ab8d0;
  --dim:      #1a2a3a;
  --mono:     'Share Tech Mono', 'Courier New', monospace;
  --vt:       'VT323', monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--text-hi);
  font-family: var(--mono);
  font-size: 13px;
  overflow: hidden;
}

/* ── SCANLINE OVERLAY ─────────────────────────────────── */
body::after {
  content: '';
  position: fixed; inset: 0;
  background: repeating-linear-gradient(
    transparent, transparent 2px,
    rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px
  );
  pointer-events: none;
  z-index: 9000;
}

/* ── LAYOUT ──────────────────────────────────────────── */
#app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* ── HEADER ──────────────────────────────────────────── */
#header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 6px 16px;
  background: var(--panel);
  border-bottom: 1px solid var(--cyan);
  box-shadow: 0 0 20px rgba(0,229,255,0.15);
  flex-shrink: 0;
}

#header .logo {
  font-family: var(--vt);
  font-size: 28px;
  color: var(--cyan);
  text-shadow: 0 0 12px var(--cyan), 0 0 30px rgba(0,229,255,0.4);
  letter-spacing: 3px;
}

#header .subtitle {
  font-size: 11px;
  color: var(--text);
  letter-spacing: 2px;
}

#header .status-badge {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--green);
  text-shadow: 0 0 8px var(--green);
}

.blink-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
  animation: blink 1.2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.1; }
}

/* ── MAIN BODY ───────────────────────────────────────── */
#body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── SIDEBAR / CONTROL DECK ──────────────────────────── */
#sidebar {
  width: 230px;
  flex-shrink: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--dim) var(--panel);
}

#sidebar::-webkit-scrollbar { width: 4px; }
#sidebar::-webkit-scrollbar-track { background: var(--panel); }
#sidebar::-webkit-scrollbar-thumb { background: var(--dim); }

.deck-title {
  font-family: var(--vt);
  font-size: 20px;
  color: var(--cyan);
  text-shadow: 0 0 10px var(--cyan);
  padding: 10px 14px 6px;
  letter-spacing: 2px;
  border-bottom: 1px solid var(--border);
}

.section {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-size: 10px;
  letter-spacing: 3px;
  color: var(--text);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title::before {
  content: '▸';
  color: var(--cyan);
  font-size: 10px;
}

.field {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
}

.field label {
  font-size: 11px;
  color: var(--text);
  width: 100px;
  flex-shrink: 0;
  white-space: nowrap;
}

.field input[type="number"],
.field input[type="text"] {
  background: #07071c;
  border: 1px solid var(--dim);
  color: var(--cyan);
  font-family: var(--mono);
  font-size: 12px;
  width: 100%;
  padding: 3px 6px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.field input:focus {
  border-color: var(--cyan);
  box-shadow: 0 0 6px rgba(0,229,255,0.3);
}

.field input[type="number"]::-webkit-inner-spin-button { opacity: 0.4; }

/* seed row with button */
.seed-row {
  display: flex;
  gap: 4px;
}

.seed-row input { flex: 1; min-width: 0; }

/* ── BUTTONS ─────────────────────────────────────────── */
.btn {
  background: transparent;
  border: 1px solid var(--dim);
  color: var(--text-hi);
  font-family: var(--mono);
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
  letter-spacing: 1px;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn:hover {
  border-color: var(--cyan);
  color: var(--cyan);
  box-shadow: 0 0 8px rgba(0,229,255,0.25);
}

.btn:active { transform: scale(0.97); }

.btn-icon {
  padding: 4px 7px;
  font-size: 14px;
  line-height: 1;
}

.btn-generate {
  width: calc(100% - 28px);
  margin: 10px 14px;
  background: rgba(0,229,255,0.05);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  font-family: var(--vt);
  font-size: 22px;
  padding: 8px;
  letter-spacing: 3px;
  text-shadow: 0 0 10px var(--cyan);
  box-shadow: 0 0 12px rgba(0,229,255,0.15), inset 0 0 12px rgba(0,229,255,0.05);
  cursor: pointer;
  transition: all 0.2s;
  display: block;
}

.btn-generate:hover {
  background: rgba(0,229,255,0.12);
  box-shadow: 0 0 24px rgba(0,229,255,0.35), inset 0 0 16px rgba(0,229,255,0.08);
}

.btn-generate:disabled {
  color: var(--dim);
  border-color: var(--dim);
  box-shadow: none;
  text-shadow: none;
  cursor: not-allowed;
}

/* ── LAYER TOGGLES ───────────────────────────────────── */
.layer-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  cursor: pointer;
  user-select: none;
}

.layer-row input[type="checkbox"] {
  display: none;
}

.layer-check {
  width: 14px; height: 14px;
  border: 1px solid var(--dim);
  display: flex; align-items: center; justify-content: center;
  font-size: 10px;
  flex-shrink: 0;
  transition: all 0.15s;
}

.layer-row input:checked + .layer-check {
  border-color: var(--cyan);
  color: var(--cyan);
}

.layer-label {
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.layer-swatch {
  width: 10px; height: 10px;
  border-radius: 1px;
  flex-shrink: 0;
}

/* ── ZOOM BAR ────────────────────────────────────────── */
.zoom-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
}

.zoom-bar label { font-size: 10px; color: var(--text); letter-spacing: 2px; }
.zoom-bar span  { font-size: 13px; color: var(--cyan); min-width: 28px; text-align: center; }

/* ── LEGEND ──────────────────────────────────────────── */
.legend {
  padding: 8px 14px;
  font-size: 10px;
  color: var(--text);
  line-height: 1.8;
}

.legend-item {
  display: flex; align-items: center; gap: 6px;
}

/* ── EXPORT BUTTONS ──────────────────────────────────── */
.export-row {
  display: flex;
  gap: 6px;
  padding: 8px 14px;
  border-top: 1px solid var(--border);
  margin-top: auto;
}

.export-row .btn { flex: 1; font-size: 10px; }

/* ── CANVAS AREA ─────────────────────────────────────── */
#canvas-area {
  flex: 1;
  overflow: auto;
  position: relative;
  background: #020209;
  scrollbar-width: thin;
  scrollbar-color: var(--dim) #020209;
}

#canvas-area::-webkit-scrollbar { width: 6px; height: 6px; }
#canvas-area::-webkit-scrollbar-track { background: #020209; }
#canvas-area::-webkit-scrollbar-thumb { background: var(--dim); }

#canvas-wrapper {
  display: inline-block;
  padding: 24px;
  min-width: 100%;
  min-height: 100%;
  cursor: crosshair;
}

#map-canvas {
  display: block;
  image-rendering: pixelated;
}

/* Grid overlay lines (drawn in JS, but CSS sets cursor feedback) */
#canvas-wrapper:hover #map-canvas {
  outline: 1px solid rgba(0,229,255,0.08);
}

/* ── EMPTY STATE ─────────────────────────────────────── */
#empty-state {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px;
  pointer-events: none;
}

.empty-title {
  font-family: var(--vt);
  font-size: 48px;
  color: var(--dim);
  letter-spacing: 4px;
  text-shadow: 0 0 20px rgba(20,20,48,0.8);
  animation: ghost-pulse 3s ease-in-out infinite;
}

@keyframes ghost-pulse {
  0%, 100% { opacity: 0.5; }
  50%       { opacity: 0.8; }
}

.empty-sub {
  font-size: 11px;
  letter-spacing: 3px;
  color: var(--dim);
}

/* ── FOOTER STATUS BAR ───────────────────────────────── */
#footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 4px 16px;
  background: var(--panel);
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text);
  flex-shrink: 0;
}

#footer .sep {
  color: var(--dim);
}

#status-msg {
  color: var(--text-hi);
  transition: color 0.3s;
}

#status-msg.ok     { color: var(--green);  text-shadow: 0 0 6px var(--green); }
#status-msg.error  { color: var(--red);    text-shadow: 0 0 6px var(--red);   }
#status-msg.busy   { color: var(--amber);  text-shadow: 0 0 6px var(--amber); }
#status-msg.cyan   { color: var(--cyan);   text-shadow: 0 0 6px var(--cyan);  }

#cursor-pos, #seed-display, #stats-display {
  white-space: nowrap;
}

/* ── NOTIFICATION ────────────────────────────────────── */
#notif {
  position: fixed;
  top: 60px; right: 16px;
  background: var(--panel);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  font-size: 11px;
  padding: 8px 14px;
  letter-spacing: 1px;
  box-shadow: 0 0 16px rgba(0,229,255,0.2);
  opacity: 0;
  transform: translateX(20px);
  transition: opacity 0.3s, transform 0.3s;
  pointer-events: none;
  z-index: 1000;
}
#notif.show {
  opacity: 1;
  transform: translateX(0);
}

/* ── LABEL EDITOR ────────────────────────────────────── */
#label-editor {
  position: fixed;
  z-index: 2000;
  display: none;
  background: #030318;
  border: 1px solid var(--cyan);
  box-shadow: 0 0 20px rgba(0,229,255,0.3), inset 0 0 10px rgba(0,229,255,0.04);
  padding: 8px 10px 7px;
  min-width: 220px;
}

#label-editor-header {
  font-size: 9px;
  letter-spacing: 3px;
  color: var(--cyan);
  text-shadow: 0 0 6px var(--cyan);
  margin-bottom: 6px;
}

#label-editor input {
  display: block;
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--dim);
  color: var(--cyan);
  font-family: var(--mono);
  font-size: 13px;
  letter-spacing: 1px;
  outline: none;
  padding: 2px 0 4px;
  caret-color: var(--cyan);
}

#label-editor input:focus { border-bottom-color: var(--cyan); }

#label-hint {
  font-size: 9px;
  color: var(--dim);
  letter-spacing: 1px;
  margin-top: 5px;
  line-height: 1.5;
}

/* ── GLITCH ANIMATION (on generate button press) ──── */
@keyframes glitch {
  0%   { transform: translate(0); clip-path: none; }
  10%  { transform: translate(-2px, 1px); }
  20%  { transform: translate(2px, -1px); }
  30%  { transform: translate(0); }
  100% { transform: translate(0); }
}
.glitch { animation: glitch 0.3s ease; }

</style>
</head>
<body>
<div id="app">

  <!-- HEADER -->
  <header id="header">
    <div class="logo">DARKMAP</div>
    <div class="subtitle">v2.0 // PROCEDURAL DUNGEON GENERATOR</div>
    <div class="status-badge">
      <div class="blink-dot"></div>
      <span id="sys-status">SYSTEM ONLINE</span>
    </div>
  </header>

  <div id="body">

    <!-- SIDEBAR -->
    <aside id="sidebar">
      <div class="deck-title">CTRL DECK</div>

      <!-- Map Dimensions -->
      <div class="section">
        <div class="section-title">MAP DIMENSIONS</div>
        <div class="field">
          <label>WIDTH</label>
          <input type="number" id="p-map_width" value="60" min="24" max="120" step="4">
        </div>
        <div class="field">
          <label>HEIGHT</label>
          <input type="number" id="p-map_height" value="40" min="18" max="80" step="2">
        </div>
      </div>

      <!-- Room Config -->
      <div class="section">
        <div class="section-title">ROOM CONFIG</div>
        <div class="field">
          <label>ROOMS MIN</label>
          <input type="number" id="p-room_count_min" value="6" min="2" max="30">
        </div>
        <div class="field">
          <label>ROOMS MAX</label>
          <input type="number" id="p-room_count_max" value="12" min="2" max="40">
        </div>
        <div class="field">
          <label>SIZE MIN</label>
          <input type="number" id="p-room_min_size" value="4" min="3" max="12">
        </div>
        <div class="field">
          <label>SIZE MAX</label>
          <input type="number" id="p-room_max_size" value="10" min="4" max="20">
        </div>
      </div>

      <!-- Generation Params -->
      <div class="section">
        <div class="section-title">GEN PARAMS</div>
        <div class="field">
          <label>SPECIALS</label>
          <input type="number" id="p-special_room_count" value="2" min="0" max="8">
        </div>
        <div class="field">
          <label>SPEC CHANCE</label>
          <input type="number" id="p-special_room_chance" value="0.7" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>LOOP CHANCE</label>
          <input type="number" id="p-loop_chance" value="0.25" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>SEED</label>
          <div class="seed-row">
            <input type="text" id="p-seed" value="" placeholder="random">
            <button class="btn btn-icon" id="btn-dice" title="Randomise seed">⚄</button>
          </div>
        </div>
      </div>

      <!-- GENERATE -->
      <button class="btn-generate" id="btn-generate">[ GENERATE ]</button>

      <!-- Layers -->
      <div class="section">
        <div class="section-title">LAYERS</div>

        <label class="layer-row" data-layer="normal">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:#1a3a6a;border:1px solid #2a5a9a"></div>
            NORMAL ROOMS
          </div>
        </label>

        <label class="layer-row" data-layer="corridor">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:#0a0a24;border:1px solid #1a1a40"></div>
            CORRIDORS
          </div>
        </label>

        <label class="layer-row" data-layer="entrance">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:#041a08;border:1px solid #00ff41"></div>
            ENTRANCE [E]
          </div>
        </label>

        <label class="layer-row" data-layer="objective">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:#1a0408;border:1px solid #ff0033"></div>
            OBJECTIVE [O]
          </div>
        </label>

        <label class="layer-row" data-layer="special">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:#12042a;border:1px solid #b400ff"></div>
            SPECIAL [S]
          </div>
        </label>

        <label class="layer-row" data-layer="labels">
          <input type="checkbox" checked>
          <div class="layer-check">✓</div>
          <div class="layer-label">
            <div class="layer-swatch" style="background:transparent;border:1px dashed #2a4a6a"></div>
            TEXT LABELS
          </div>
        </label>
      </div>

      <!-- Zoom -->
      <div class="zoom-bar">
        <label>ZOOM</label>
        <button class="btn btn-icon" id="btn-zoom-out">−</button>
        <span id="zoom-label">14px</span>
        <button class="btn btn-icon" id="btn-zoom-in">+</button>
      </div>

      <!-- Export -->
      <div class="export-row">
        <button class="btn" id="btn-export-txt">⬇ TXT</button>
        <button class="btn" id="btn-export-png">⬇ PNG</button>
        <button class="btn" id="btn-copy-seed">⧉ SEED</button>
        <button class="btn" id="btn-reset">↺ RST</button>
      </div>

    </aside>

    <!-- CANVAS AREA -->
    <section id="canvas-area">
      <div id="empty-state">
        <div class="empty-title">NO SIGNAL</div>
        <div class="empty-sub">// PRESS GENERATE TO INITIALISE MAP //</div>
      </div>
      <div id="canvas-wrapper">
        <canvas id="map-canvas"></canvas>
      </div>
    </section>

  </div>

  <!-- FOOTER -->
  <footer id="footer">
    <span id="status-msg">READY — AWAITING INPUT</span>
    <span class="sep">//</span>
    <span id="seed-display">SEED: ——————</span>
    <span class="sep">//</span>
    <span id="stats-display">ROOMS: — · COVERAGE: —%</span>
    <span class="sep">//</span>
    <span id="cursor-pos">POS: ——,——</span>
  </footer>

</div>

<!-- NOTIFICATION TOAST -->
<div id="notif"></div>

<!-- LABEL EDITOR (floating inline editor) -->
<div id="label-editor">
  <div id="label-editor-header">EDIT LABEL</div>
  <input type="text" id="label-input" maxlength="24" autocomplete="off" spellcheck="false">
  <div id="label-hint">↵ save  ·  ESC cancel</div>
</div>

<script>
'use strict';

// ── State ──────────────────────────────────────────────
let mapData   = null;
let tileSize  = 14;
const ZOOM_STEPS = [8, 10, 12, 14, 16, 20, 24, 30];
let zoomIdx   = ZOOM_STEPS.indexOf(14);

const layers = {
  normal:    true,
  corridor:  true,
  entrance:  true,
  objective: true,
  special:   true,
  labels:    true,   // ← text labels on rooms and corridors
};

// ── Custom label overrides ─────────────────────────────
// Cleared on each new generation; survive re-renders and zoom changes.
// Empty string stored = user explicitly cleared (falls back to random).
let customRoomLabels   = {};   // { roomId  → 'My Label' }
let customConnLabels   = {};   // { 'minId-maxId' → 'My Label' }
let corrLabelPositions = [];   // [{conn, key, px, py, tw, h}] rebuilt each renderMap

function connKey(a, b) { return Math.min(a, b) + '-' + Math.max(a, b); }

// ── Cyberpunk colour palette ───────────────────────────
const TILE_COLORS = {
  wall:      '#040412',
  wallAlt:   '#060618',
  corridor:  '#0d1640',  // ← was '#080a20'; much more visible now
  normal:    '#0d1a32',
  entrance:  '#041608',
  objective: '#180408',
  special:   '#0e0520',
};

const BORDER = {
  normal:    { stroke: '#1e4070', glow: null,      width: 1   },
  entrance:  { stroke: '#00ff41', glow: '#00ff41', width: 1.5 },
  objective: { stroke: '#ff0033', glow: '#ff0033', width: 1.5 },
  special:   { stroke: '#b400ff', glow: '#b400ff', width: 1.5 },
};

// Short type badge drawn inside rooms (always, regardless of label layer)
const TYPE_BADGE = { entrance: 'E', objective: 'O', special: 'S' };

// Text colours for room name labels
const LABEL_COLOR = {
  normal:    '#4a7ab0',
  entrance:  '#00cc33',
  objective: '#cc0022',
  special:   '#8800cc',
};

// ── DOM refs ───────────────────────────────────────────
const canvas  = document.getElementById('map-canvas');
const ctx     = canvas.getContext('2d');
const wrapper = document.getElementById('canvas-wrapper');
const empty   = document.getElementById('empty-state');
const genBtn  = document.getElementById('btn-generate');

// ── Status helpers ─────────────────────────────────────
function setStatus(msg, cls = '') {
  const el = document.getElementById('status-msg');
  el.textContent = msg;
  el.className   = cls;
}

function notify(msg, duration = 2000) {
  const n = document.getElementById('notif');
  n.textContent = msg;
  n.classList.add('show');
  setTimeout(() => n.classList.remove('show'), duration);
}

// ── Param collection ──────────────────────────────────
function getParams() {
  const fields = [
    'map_width','map_height',
    'room_min_size','room_max_size',
    'room_count_min','room_count_max',
    'special_room_count','special_room_chance',
    'loop_chance','seed'
  ];
  const p = {};
  for (const f of fields) {
    const el = document.getElementById('p-' + f);
    if (!el) continue;
    const v = el.value.trim();
    if (v === '') continue;
    p[f] = f === 'special_room_chance' || f === 'loop_chance' ? parseFloat(v) : (parseInt(v) || v);
  }
  return p;
}

// ── Room tile map builder ──────────────────────────────
function buildRTM(rooms) {
  const m = new Map();
  for (const r of rooms)
    for (let y = r.y; y < r.y + r.h; y++)
      for (let x = r.x; x < r.x + r.w; x++)
        m.set(x + ',' + y, r.type);
  return m;
}

// ── Canvas renderer ────────────────────────────────────
function renderMap() {
  if (!mapData) return;
  corrLabelPositions = [];   // rebuild hit areas every frame

  const { grid, rooms, width, height } = mapData;
  const ts = tileSize;

  canvas.width  = width  * ts;
  canvas.height = height * ts;

  const rtm = buildRTM(rooms);

  // ── 1. Tiles + corridor dot texture ──────────────────
  for (let y = 0; y < height; y++) {
    const row = grid[y];
    for (let x = 0; x < width; x++) {
      const ch    = row[x];
      const key   = x + ',' + y;
      const rtype = rtm.get(key);
      let color;

      if (ch === '#') {
        // Subtle wall texture
        color = ((x * 7 + y * 13) & 3) < 2 ? TILE_COLORS.wall : TILE_COLORS.wallAlt;
      } else if (!rtype) {
        // Corridor tile
        color = layers.corridor ? TILE_COLORS.corridor : TILE_COLORS.wall;
      } else {
        color = layers[rtype] ? (TILE_COLORS[rtype] || TILE_COLORS.normal) : TILE_COLORS.wall;
      }

      ctx.fillStyle = color;
      ctx.fillRect(x * ts, y * ts, ts, ts);

      // Corridor: draw a centred dot to make passages clearly distinct from walls
      if (layers.corridor && ch === '.' && !rtype && ts >= 6) {
        const ds = Math.max(1, Math.round(ts * 0.22));
        ctx.fillStyle = '#1e2b60';
        ctx.fillRect(
          Math.round(x * ts + (ts - ds) / 2),
          Math.round(y * ts + (ts - ds) / 2),
          ds, ds
        );
      }
    }
  }

  // ── 2. Subtle grid lines (only when tile ≥ 12px) ─────
  if (ts >= 12) {
    ctx.strokeStyle = 'rgba(0, 80, 160, 0.07)';
    ctx.lineWidth   = 0.5;
    for (let y = 0; y <= height; y++) {
      ctx.beginPath(); ctx.moveTo(0, y*ts); ctx.lineTo(width*ts, y*ts); ctx.stroke();
    }
    for (let x = 0; x <= width; x++) {
      ctx.beginPath(); ctx.moveTo(x*ts, 0); ctx.lineTo(x*ts, height*ts); ctx.stroke();
    }
  }

  // ── 3. Room borders ───────────────────────────────────
  ctx.save();
  for (const r of rooms) {
    if (!layers[r.type]) continue;
    const b = BORDER[r.type] || BORDER.normal;

    ctx.lineWidth   = b.width;
    ctx.strokeStyle = b.stroke;

    if (b.glow) {
      ctx.shadowColor = b.glow;
      ctx.shadowBlur  = ts >= 12 ? 10 : 5;
    } else {
      ctx.shadowBlur = 0;
    }

    ctx.strokeRect(r.x*ts + 1, r.y*ts + 1, r.w*ts - 2, r.h*ts - 2);
    ctx.shadowBlur = 0;
  }
  ctx.restore();

  // ── 4. Room labels ────────────────────────────────────
  ctx.save();
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';

  for (const r of rooms) {
    if (!layers[r.type]) continue;
    const b   = BORDER[r.type] || BORDER.normal;
    const lcl = LABEL_COLOR[r.type] || LABEL_COLOR.normal;
    const cx  = (r.x + r.w / 2) * ts;
    const cy  = (r.y + r.h / 2) * ts;
    const pw  = r.w * ts;   // pixel width of room
    const ph  = r.h * ts;   // pixel height of room

    // ── Type badge (E / O / S) — always visible when tile ≥ 10 ──
    if (ts >= 10) {
      const badge = TYPE_BADGE[r.type];
      if (badge) {
        const bsz = Math.max(9, Math.min(ts - 2, 22));
        ctx.font        = `bold ${bsz}px "Share Tech Mono", monospace`;
        ctx.fillStyle   = b.stroke;
        ctx.shadowColor = b.glow || b.stroke;
        ctx.shadowBlur  = 14;
        // If there's room for a codename too, push badge toward top edge
        const badgeY = (layers.labels && ph >= 32) ? r.y * ts + bsz * 0.8 : cy;
        ctx.fillText(badge, cx, badgeY);
        ctx.shadowBlur = 0;
      }
    }

    // ── Codename label — only when labels layer is on AND room large enough ──
    if (layers.labels && pw >= 36 && ph >= 28) {
      const nameSz  = Math.max(6, Math.min(Math.floor(ts * 0.62), 14));
      const subSz   = Math.max(5, Math.min(Math.floor(ts * 0.44), 10));
      const isCustom = customRoomLabels[r.id] !== undefined;
      const label    = isCustom ? customRoomLabels[r.id] : (r.label || '');
      const sub      = r.type.toUpperCase();
      // Custom labels glow cyan; random labels use the room's accent colour
      const labelCol = isCustom ? '#00d4ff' : lcl;

      // Codename
      ctx.font        = `bold ${nameSz}px "Share Tech Mono", monospace`;
      ctx.fillStyle   = labelCol;
      ctx.shadowColor = labelCol;
      ctx.shadowBlur  = isCustom ? 10 : 6;
      // Vertically centre; nudge slightly below badge if badge exists
      const hasBadge = !!TYPE_BADGE[r.type];
      const nameY = hasBadge ? cy + nameSz * 0.4 : cy - subSz * 0.6;
      ctx.fillText(label, cx, nameY);
      ctx.shadowBlur = 0;

      // Subtype (dimmer, smaller)
      if (ph >= 40 && r.type === 'normal') {
        ctx.font      = `${subSz}px "Share Tech Mono", monospace`;
        ctx.fillStyle = '#2a3a5a';
        ctx.fillText(sub, cx, nameY + nameSz + 2);
      }
    }
  }
  ctx.restore();

  // ── 5. Corridor labels ────────────────────────────────
  if (layers.labels && layers.corridor && ts >= 11 && mapData.connections) {
    const roomById = {};
    for (const r of rooms) roomById[r.id] = r;

    ctx.save();
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    const cfsz = Math.max(6, Math.min(Math.floor(ts * 0.55), 11));
    ctx.font   = `${cfsz}px "Share Tech Mono", monospace`;

    for (const conn of mapData.connections) {
      const fr = roomById[conn.from];
      const tr = roomById[conn.to];
      if (!fr || !tr) continue;
      // Skip if either endpoint's layer is hidden
      if (!layers[fr.type] || !layers[tr.type]) continue;

      // Find the L-bend: try both possible bend points
      const pos = findCorridorLabelPos(fr, tr, grid, rtm, width, height);
      if (!pos) continue;

      const px = (pos.x + 0.5) * ts;
      const py = (pos.y + 0.5) * ts;

      // Resolve label: custom override → generated
      const key      = connKey(conn.from, conn.to);
      const isCustom = customConnLabels[key] !== undefined;
      const dispLabel = isCustom ? customConnLabels[key] : conn.label;

      // Tiny dark background pill for readability
      const tw = ctx.measureText(dispLabel).width + 6;
      const th = cfsz * 1.4;
      ctx.fillStyle = 'rgba(4,4,18,0.85)';
      ctx.fillRect(px - tw / 2, py - th / 2, tw, th);

      ctx.fillStyle   = isCustom ? '#00d4ff' : '#2a4080';
      ctx.shadowColor = isCustom ? '#00d4ff' : '#3060c0';
      ctx.shadowBlur  = isCustom ? 8 : 4;
      ctx.fillText(dispLabel, px, py);
      ctx.shadowBlur  = 0;

      // Store position so click handler can find it
      corrLabelPositions.push({ conn, key, px, py, tw, th });
    }
    ctx.restore();
  }

  // ── 6. Corner decoration on entrance/objective ────────
  if (ts >= 12) {
    ctx.save();
    for (const r of rooms) {
      if (r.type !== 'entrance' && r.type !== 'objective') continue;
      if (!layers[r.type]) continue;
      const b   = BORDER[r.type];
      const len = Math.min(ts * 1.5, 10);

      ctx.strokeStyle = b.stroke;
      ctx.lineWidth   = 1.5;
      ctx.shadowColor = b.glow;
      ctx.shadowBlur  = 6;

      const corners = [
        [r.x*ts,            r.y*ts,             1,  1],
        [(r.x+r.w)*ts,      r.y*ts,            -1,  1],
        [r.x*ts,            (r.y+r.h)*ts,       1, -1],
        [(r.x+r.w)*ts,      (r.y+r.h)*ts,      -1, -1],
      ];
      for (const [cx, cy, dx, dy] of corners) {
        ctx.beginPath();
        ctx.moveTo(cx + dx*len, cy);
        ctx.lineTo(cx, cy);
        ctx.lineTo(cx, cy + dy*len);
        ctx.stroke();
      }
    }
    ctx.shadowBlur = 0;
    ctx.restore();
  }
}

// ── Find a corridor tile between two rooms for label placement ──
function findCorridorLabelPos(fromRoom, toRoom, grid, rtm, width, height) {
  // The L-corridor goes through either (to.cx, from.cy) or (from.cx, to.cy).
  // Try both bends, then segment midpoints, then fall back to any midpoint tile.
  const candidates = [
    { x: toRoom.cx,                               y: fromRoom.cy },
    { x: fromRoom.cx,                             y: toRoom.cy   },
    { x: Math.round((fromRoom.cx+toRoom.cx)/2),   y: fromRoom.cy },
    { x: toRoom.cx,   y: Math.round((fromRoom.cy+toRoom.cy)/2) },
    { x: Math.round((fromRoom.cx+toRoom.cx)/2),   y: toRoom.cy   },
    { x: fromRoom.cx, y: Math.round((fromRoom.cy+toRoom.cy)/2) },
    { x: Math.round((fromRoom.cx+toRoom.cx)/2),   y: Math.round((fromRoom.cy+toRoom.cy)/2) },
  ];

  for (const {x, y} of candidates) {
    if (x < 1 || x >= width-1 || y < 1 || y >= height-1) continue;
    if (grid[y][x] !== '.') continue;
    if (rtm.has(x+','+y)) continue;   // skip room tiles — corridors only
    return {x, y};
  }
  return null;
}

// ── Animated "scan" entrance ──────────────────────────
function renderMapAnimated() {
  if (!mapData) return;

  const { grid, rooms, width, height } = mapData;
  const ts  = tileSize;
  const rtm = buildRTM(rooms);

  canvas.width  = width  * ts;
  canvas.height = height * ts;

  // Fill black first
  ctx.fillStyle = '#030311';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const totalRows = height;
  let   row       = 0;
  const batchSize = Math.max(1, Math.ceil(totalRows / 20));

  function step() {
    if (row >= totalRows) {
      // Final pass — borders and labels
      renderMap();
      return;
    }

    const end = Math.min(row + batchSize, totalRows);
    for (let y = row; y < end; y++) {
      const rowStr = grid[y];
      for (let x = 0; x < width; x++) {
        const ch    = rowStr[x];
        const key   = x + ',' + y;
        const rtype = rtm.get(key);
        let color;
        if (ch === '#') {
          color = ((x*7+y*13)&3) < 2 ? TILE_COLORS.wall : TILE_COLORS.wallAlt;
        } else if (!rtype) {
          color = TILE_COLORS.corridor;
        } else {
          color = TILE_COLORS[rtype] || TILE_COLORS.normal;
        }
        ctx.fillStyle = color;
        ctx.fillRect(x*ts, y*ts, ts, ts);
      }
      // Scan line highlight
      ctx.fillStyle = 'rgba(0, 229, 255, 0.05)';
      ctx.fillRect(0, end*ts - ts, width*ts, ts);
    }
    row = end;
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ── Generate ──────────────────────────────────────────
async function generate() {
  const params = getParams();
  genBtn.disabled    = true;
  genBtn.textContent = '[ COMPILING... ]';
  genBtn.classList.add('glitch');
  setStatus('INITIALISING MAP COMPILER...', 'busy');

  try {
    const res  = await fetch('/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(params),
    });
    const data = await res.json();

    if (!data.ok) {
      setStatus('ERROR: ' + data.error, 'error');
      return;
    }

    mapData = data;
    empty.style.display = 'none';

    // New map — discard all previous custom overrides
    customRoomLabels   = {};
    customConnLabels   = {};
    corrLabelPositions = [];

    // Update seed field
    document.getElementById('p-seed').value = data.seed;
    document.getElementById('seed-display').textContent = 'SEED: ' + data.seed;
    document.getElementById('stats-display').textContent =
      `ROOMS: ${data.stats.rooms} · COVERAGE: ${data.stats.coverage}%`;

    renderMapAnimated();
    setStatus(
      `MAP ONLINE // ${data.stats.rooms} ROOMS // ${data.stats.coverage}% COVERAGE`,
      'ok'
    );

  } catch (e) {
    setStatus('COMMS ERROR: ' + e.message, 'error');
  } finally {
    setTimeout(() => {
      genBtn.disabled    = false;
      genBtn.textContent = '[ GENERATE ]';
      genBtn.classList.remove('glitch');
    }, 400);
  }
}

// ── Layer toggles ─────────────────────────────────────
document.querySelectorAll('.layer-row').forEach(row => {
  const cb    = row.querySelector('input[type="checkbox"]');
  const check = row.querySelector('.layer-check');
  const lname = row.dataset.layer;

  cb.addEventListener('change', () => {
    layers[lname] = cb.checked;
    check.textContent = cb.checked ? '✓' : '';
    renderMap();
  });
});

// ── Zoom ──────────────────────────────────────────────
function setZoom(idx) {
  zoomIdx  = Math.max(0, Math.min(ZOOM_STEPS.length - 1, idx));
  tileSize = ZOOM_STEPS[zoomIdx];
  document.getElementById('zoom-label').textContent = tileSize + 'px';
  renderMap();
}

document.getElementById('btn-zoom-in') .addEventListener('click', () => setZoom(zoomIdx + 1));
document.getElementById('btn-zoom-out').addEventListener('click', () => setZoom(zoomIdx - 1));

// Mouse-wheel zoom on canvas
document.getElementById('canvas-area').addEventListener('wheel', e => {
  e.preventDefault();
  setZoom(zoomIdx + (e.deltaY < 0 ? 1 : -1));
}, { passive: false });

// ── Cursor coordinates + hover cursor ─────────────────
canvas.addEventListener('mousemove', e => {
  const rect  = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / rect.width;
  const scaleY = canvas.height / rect.height;
  const canvasX = (e.clientX - rect.left) * scaleX;
  const canvasY = (e.clientY - rect.top)  * scaleY;
  const tx = Math.floor(canvasX / tileSize);
  const ty = Math.floor(canvasY / tileSize);
  document.getElementById('cursor-pos').textContent = `POS: ${tx},${ty}`;

  // Change cursor to text-edit when hovering over any label
  let overLabel = false;
  if (mapData && layers.labels) {
    // Corridor label hit areas
    for (const lp of corrLabelPositions) {
      if (Math.abs(canvasX - lp.px) <= lp.tw / 2 + 2 &&
          Math.abs(canvasY - lp.py) <= lp.th / 2 + 2) {
        overLabel = true; break;
      }
    }
    // Room bodies (clicking anywhere inside opens the room label editor)
    if (!overLabel) {
      for (const r of mapData.rooms) {
        if (!layers[r.type]) continue;
        if (tx >= r.x && tx < r.x + r.w && ty >= r.y && ty < r.y + r.h) {
          overLabel = true; break;
        }
      }
    }
  }
  canvas.style.cursor = overLabel ? 'text' : 'crosshair';
});

canvas.addEventListener('mouseleave', () => {
  document.getElementById('cursor-pos').textContent = 'POS: ——,——';
  canvas.style.cursor = 'crosshair';
});

// ── Canvas click → open label editor ──────────────────
canvas.addEventListener('click', e => {
  if (!mapData) return;
  const rect   = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / rect.width;
  const scaleY = canvas.height / rect.height;
  const canvasX = (e.clientX - rect.left) * scaleX;
  const canvasY = (e.clientY - rect.top)  * scaleY;
  const tx = Math.floor(canvasX / tileSize);
  const ty = Math.floor(canvasY / tileSize);

  // 1. Corridor labels (small hit area — check first)
  if (layers.labels && layers.corridor) {
    for (const lp of corrLabelPositions) {
      if (Math.abs(canvasX - lp.px) <= lp.tw / 2 + 4 &&
          Math.abs(canvasY - lp.py) <= lp.th / 2 + 4) {
        const cur = customConnLabels[lp.key] !== undefined
          ? customConnLabels[lp.key] : lp.conn.label;
        showLabelEditor(e.clientX, e.clientY, 'corridor', lp.key, cur);
        return;
      }
    }
  }

  // 2. Room bodies (click anywhere inside the room)
  if (mapData.rooms) {
    for (const r of mapData.rooms) {
      if (!layers[r.type]) continue;
      if (tx >= r.x && tx < r.x + r.w && ty >= r.y && ty < r.y + r.h) {
        const cur = customRoomLabels[r.id] !== undefined
          ? customRoomLabels[r.id] : r.label;
        showLabelEditor(e.clientX, e.clientY, 'room', r.id, cur);
        return;
      }
    }
  }
});

// ── Label editor ──────────────────────────────────────
function showLabelEditor(clientX, clientY, type, id, currentValue) {
  const editor = document.getElementById('label-editor');
  const input  = document.getElementById('label-input');
  const hint   = document.getElementById('label-hint');

  editor._type = type;
  editor._id   = id;
  input.value  = currentValue || '';

  const isCustom = (type === 'room')
    ? customRoomLabels[id] !== undefined
    : customConnLabels[id] !== undefined;

  hint.textContent = isCustom
    ? '↵ save  ·  ESC cancel  ·  empty+↵ = reset to random'
    : '↵ save  ·  ESC cancel';

  // Position near click, clamped to viewport
  const EW = 240, EH = 58;
  editor.style.left    = Math.min(clientX + 8, window.innerWidth  - EW - 8) + 'px';
  editor.style.top     = Math.min(clientY + 8, window.innerHeight - EH - 8) + 'px';
  editor.style.display = 'block';

  input.select();
  input.focus();
}

function commitLabelEdit() {
  const editor = document.getElementById('label-editor');
  const val    = document.getElementById('label-input').value.trim();

  if (editor._type === 'room') {
    if (val === '') delete customRoomLabels[editor._id];   // empty → revert to random
    else            customRoomLabels[editor._id] = val;
  } else {
    if (val === '') delete customConnLabels[editor._id];
    else            customConnLabels[editor._id] = val;
  }

  editor.style.display = 'none';
  renderMap();
}

document.getElementById('label-input').addEventListener('keydown', e => {
  if (e.key === 'Enter')  { e.preventDefault(); commitLabelEdit(); }
  if (e.key === 'Escape') { document.getElementById('label-editor').style.display = 'none'; }
});

// Clicking outside the editor closes it (treating as commit)
document.addEventListener('mousedown', e => {
  const editor = document.getElementById('label-editor');
  if (editor.style.display !== 'none' && !editor.contains(e.target))
    commitLabelEdit();
});

// ── Generate button ───────────────────────────────────
genBtn.addEventListener('click', generate);

// Also trigger on Enter key from any input
document.querySelectorAll('#sidebar input').forEach(inp => {
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') generate(); });
});

// ── Random seed ───────────────────────────────────────
document.getElementById('btn-dice').addEventListener('click', () => {
  document.getElementById('p-seed').value = Math.floor(Math.random() * 0x3FFFFFFF);
});

// ── Export ────────────────────────────────────────────
document.getElementById('btn-export-txt').addEventListener('click', () => {
  if (!mapData) { notify('NO MAP — GENERATE FIRST'); return; }
  const lines = mapData.grid.join('\n');
  const blob  = new Blob([lines], { type: 'text/plain' });
  const a     = document.createElement('a');
  a.href      = URL.createObjectURL(blob);
  a.download  = `darkmap_${mapData.seed}.txt`;
  a.click();
  notify('MAP EXPORTED TO TXT');
});

document.getElementById('btn-export-png').addEventListener('click', () => {
  if (!mapData) { notify('NO MAP — GENERATE FIRST'); return; }

  // Render to a fresh offscreen canvas at current zoom so all layers are included
  // (the on-screen canvas already contains the full render, just use toBlob)
  canvas.toBlob(blob => {
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    a.download = `darkmap_${mapData.seed}.png`;
    a.click();
    URL.revokeObjectURL(a.href);
    notify('MAP EXPORTED TO PNG');
  }, 'image/png');
});

document.getElementById('btn-copy-seed').addEventListener('click', () => {
  if (!mapData) { notify('NO MAP — GENERATE FIRST'); return; }
  navigator.clipboard.writeText(String(mapData.seed));
  notify('SEED COPIED: ' + mapData.seed);
});

document.getElementById('btn-reset').addEventListener('click', () => {
  const defaults = {
    map_width: 60, map_height: 40,
    room_min_size: 4, room_max_size: 10,
    room_count_min: 6, room_count_max: 12,
    special_room_count: 2, special_room_chance: 0.7,
    loop_chance: 0.25, seed: '',
  };
  for (const [k, v] of Object.entries(defaults)) {
    const el = document.getElementById('p-' + k);
    if (el) el.value = v;
  }
  notify('DEFAULTS RESTORED');
});

// ── Initial generate on load ──────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  setTimeout(generate, 300);
});
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("╔══════════════════════════════════════╗")
    print("║  DARKMAP v2.0 — Dungeon Generator    ║")
    print("║  http://localhost:5000               ║")
    print("╚══════════════════════════════════════╝")
    app.run(debug=False, host='0.0.0.0', port=5000)
