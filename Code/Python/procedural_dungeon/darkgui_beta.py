#!/usr/bin/env python3
import random
import copy
from collections import deque
import tkinter as tk
from tkinter import filedialog, messagebox

# ---------- Map generation logic ----------

class Rect:
    """Axis-aligned rectangle on the grid."""
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def intersects(self, other):
        return (self.x < other.x + other.w and
                self.x + self.w > other.x and
                self.y < other.y + other.h and
                self.y + self.h > other.y)

class Room(Rect):
    """A room with an ID and type."""
    def __init__(self, id, x, y, w, h, rtype):
        super().__init__(x, y, w, h)
        self.id = id
        self.type = rtype  # 'normal', 'entrance', 'objective', 'special'

    @property
    def center(self):
        return (self.x + self.w // 2, self.y + self.h // 2)

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

class MapGenerator:
    def __init__(self, **cfg):
        self.map_width  = cfg.get('map_width', 32)
        self.map_height = cfg.get('map_height', 32)
        self.room_min_size = cfg.get('room_min_size', 3)
        self.room_max_size = cfg.get('room_max_size', 7)
        self.corridor_min_length = cfg.get('corridor_min_length', 3)
        self.corridor_max_length = cfg.get('corridor_max_length', 15)
        self.normal_room_count_min = cfg.get('normal_room_count_min', 5)
        self.normal_room_count_max = cfg.get('normal_room_count_max', 10)
        self.special_room_count   = cfg.get('special_room_count', 2)
        self.special_room_chance  = cfg.get('special_room_chance', 0.5)
        self.seed = cfg.get('seed') or random.randrange(1 << 30)

    def _add_room(self, room):
        self.rooms.append(room)
        self.rooms_by_id[room.id] = room
        self.adj[room.id] = set()

    def _carve_room(self, room):
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                self.grid[y][x] = '.'

    def _carve_corridor(self, a, b):
        x1, y1 = a; x2, y2 = b
        if random.choice([True, False]):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y1][x] = '.'
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x2] = '.'
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x1] = '.'
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y2][x] = '.'

    def _connect_outside(self, roomA, roomB):
        """Connect two rooms via exactly one corridor tile on each room's perimeter."""
        # Gather outside-adjacent tiles for roomA
        outsA = []
        for x in range(roomA.x, roomA.x + roomA.w):
            if roomA.y > 0:
                outsA.append((x, roomA.y - 1))
            if roomA.y + roomA.h < self.map_height:
                outsA.append((x, roomA.y + roomA.h))
        for y in range(roomA.y, roomA.y + roomA.h):
            if roomA.x > 0:
                outsA.append((roomA.x - 1, y))
            if roomA.x + roomA.w < self.map_width:
                outsA.append((roomA.x + roomA.w, y))

        # Gather outside-adjacent tiles for roomB
        outsB = []
        for x in range(roomB.x, roomB.x + roomB.w):
            if roomB.y > 0:
                outsB.append((x, roomB.y - 1))
            if roomB.y + roomB.h < self.map_height:
                outsB.append((x, roomB.y + roomB.h))
        for y in range(roomB.y, roomB.y + roomB.h):
            if roomB.x > 0:
                outsB.append((roomB.x - 1, y))
            if roomB.x + roomB.w < self.map_width:
                outsB.append((roomB.x + roomB.w, y))

        # Choose the closest outside tile to the other's center
        start = min(outsA, key=lambda p: manhattan(p, roomB.center))
        end   = min(outsB, key=lambda p: manhattan(p, roomA.center))

        # Carve exactly one tile for each connection
        sx, sy = start
        ex, ey = end
        self.grid[sy][sx] = '.'
        self.grid[ey][ex] = '.'

        # Compute offset one step further from each room
        def offset_outside(room, px, py):
            # Clamp to room interior
            cx = min(max(px, room.x), room.x + room.w - 1)
            cy = min(max(py, room.y), room.y + room.h - 1)
            dx, dy = px - cx, py - cy
            return (px + dx, py + dy)

        ns = offset_outside(roomA, sx, sy)
        ne = offset_outside(roomB, ex, ey)
        # Carve those tiles
        self.grid[ns[1]][ns[0]] = '.'
        self.grid[ne[1]][ne[0]] = '.'
        # Carve corridor between offset points
        self._carve_corridor(ns, ne)

        # Record adjacency
        self.adj[roomA.id].add(roomB.id)
        self.adj[roomB.id].add(roomA.id)

    def _place_normal_rooms(self):
        count = random.randint(self.normal_room_count_min, self.normal_room_count_max)
        attempts = 0
        while len([r for r in self.rooms if r.type == 'normal']) < count and attempts < count * 50:
            w = random.randint(self.room_min_size, self.room_max_size)
            h = random.randint(self.room_min_size, self.room_max_size)
            x = random.randint(1, self.map_width - w - 1)
            y = random.randint(1, self.map_height - h - 1)
            rect = Rect(x, y, w, h)
            if any(rect.intersects(o) for o in self.rooms):
                attempts += 1
                continue
            room = Room(self.next_id, x, y, w, h, 'normal')
            self.next_id += 1
            self._add_room(room)
            self._carve_room(room)
        if len([r for r in self.rooms if r.type == 'normal']) < self.normal_room_count_min:
            raise RuntimeError("Insufficient normal rooms")

    def _connect_normal_rooms(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        if not normals: return
        edges = []
        for i, a in enumerate(normals):
            for b in normals[i+1:]:
                d = manhattan(a.center, b.center)
                edges.append((d, a, b))
        edges.sort(key=lambda e: e[0])
        visited = {normals[0].id}
        mst = []
        for d, a, b in edges:
            if len(visited) == len(normals): break
            if ((a.id in visited) ^ (b.id in visited)) and self.corridor_min_length <= d <= self.corridor_max_length:
                mst.append((a, b))
                visited.add(a.id if b.id in visited else b.id)
        if len(visited) < len(normals):
            visited = {normals[0].id}; mst = []
            for d, a, b in edges:
                if len(visited) == len(normals): break
                if (a.id in visited) ^ (b.id in visited):
                    mst.append((a, b))
                    visited.add(a.id if b.id in visited else b.id)
        for a, b in mst:
            self._carve_corridor(a.center, b.center)
            self.adj[a.id].add(b.id)
            self.adj[b.id].add(a.id)

    def _add_loops(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        pairs = []
        for i, a in enumerate(normals):
            for b in normals[i+1:]:
                if b.id in self.adj[a.id]: continue
                d = manhattan(a.center, b.center)
                if self.corridor_min_length <= d <= self.corridor_max_length:
                    pairs.append((a, b))
        random.shuffle(pairs)
        loops = random.randint(0, len(normals)//2)
        for a, b in pairs[:loops]:
            self._carve_corridor(a.center, b.center)
            self.adj[a.id].add(b.id)
            self.adj[b.id].add(a.id)

    def _bfs(self, s, t, adj):
        q = deque([s])
        parent = {s: None}
        while q:
            cur = q.popleft()
            if cur == t: break
            for n in adj.get(cur, []):
                if n not in parent:
                    parent[n] = cur
                    q.append(n)
        if t not in parent: return []
        path = []
        u = t
        while u is not None:
            path.append(u)
            u = parent[u]
        return list(reversed(path))

    def _count_normals(self, path):
        return sum(1 for i in path if i in self.rooms_by_id and self.rooms_by_id[i].type == 'normal')

    def _place_mandatory(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        required = len(normals) // 2

        for _ in range(500):
            entrance = None
            # Place entrance
            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                side = random.choice(['top','bot','left','right'])
                if side == 'top':
                    x, y = random.randint(1, self.map_width-w-1), 1
                elif side == 'bot':
                    x, y = random.randint(1, self.map_width-w-1), self.map_height-h-1
                elif side == 'left':
                    x, y = 1, random.randint(1, self.map_height-h-1)
                else:
                    x, y = self.map_width-w-1, random.randint(1, self.map_height-h-1)
                exp = Rect(x-1, y-1, w+2, h+2)
                if any(exp.intersects(o) for o in self.rooms): continue
                dists = sorted(
                    [(manhattan((x+w//2,y+h//2), R.center), R) for R in normals],
                    key=lambda t: t[0]
                )
                if not dists: continue
                d, tgt = dists[0]
                if not (self.corridor_min_length <= d <= self.corridor_max_length):
                    continue
                entrance = (Room(self.next_id, x, y, w, h, 'entrance'), tgt.id)
                break
            if not entrance: continue

            objective = None
            # Place objective
            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                side = random.choice(['top','bot','left','right'])
                if side == 'top':
                    x, y = random.randint(1, self.map_width-w-1), 1
                elif side == 'bot':
                    x, y = random.randint(1, self.map_width-w-1), self.map_height-h-1
                elif side == 'left':
                    x, y = 1, random.randint(1, self.map_height-h-1)
                else:
                    x, y = self.map_width-w-1, random.randint(1, self.map_height-h-1)
                exp = Rect(x-1, y-1, w+2, h+2)
                if any(exp.intersects(o) for o in self.rooms) or exp.intersects(entrance[0]):
                    continue
                dists = sorted(
                    [(manhattan((x+w//2,y+h//2), R.center), R) for R in normals],
                    key=lambda t: t[0]
                )
                if not dists: continue
                d, tgt = dists[0]
                if not (self.corridor_min_length <= d <= self.corridor_max_length):
                    continue
                objective = (Room(self.next_id+1, x, y, w, h, 'objective'), tgt.id)
                # Check distance rule
                adj2 = copy.deepcopy(self.adj)
                adj2[entrance[0].id] = {entrance[1]}; adj2[entrance[1]].add(entrance[0].id)
                adj2[objective[0].id] = {objective[1]}; adj2[objective[1]].add(objective[0].id)
                path = self._bfs(entrance[0].id, objective[0].id, adj2)
                if self._count_normals(path) < required:
                    continue
                # Commit
                for rm, tg in (entrance, objective):
                    self._add_room(rm)
                    self._carve_room(rm)
                    self._connect_outside(rm, self.rooms_by_id[tg])
                    self.next_id += 1
                return

        raise RuntimeError("Could not place mandatory rooms")

    def _place_special(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        for _ in range(self.special_room_count):
            if random.random() > self.special_room_chance:
                continue
            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                x = random.randint(1, self.map_width-w-1)
                y = random.randint(1, self.map_height-h-1)
                rect = Rect(x, y, w, h)
                if any(rect.intersects(o) for o in self.rooms):
                    continue
                dists = sorted(
                    [(manhattan((x+w//2,y+h//2), R.center), R) for R in normals],
                    key=lambda t: t[0]
                )
                if not dists: continue
                d, tgt = dists[0]
                if not (self.corridor_min_length <= d <= self.corridor_max_length):
                    continue
                rm = Room(self.next_id, x, y, w, h, 'special')
                self.next_id += 1
                self._add_room(rm)
                self._carve_room(rm)
                self._connect_outside(rm, tgt)
                break

    def generate(self):
        random.seed(self.seed)
        self.grid = [['#'] * self.map_width for _ in range(self.map_height)]
        self.rooms = []; self.rooms_by_id = {}; self.adj = {}; self.next_id = 0

        self._place_normal_rooms()
        self._connect_normal_rooms()
        self._add_loops()
        self._place_mandatory()
        self._place_special()

        # mark entrance (1) and objective (2)
        for r in self.rooms:
            if r.type in ('entrance','objective'):
                mark = '1' if r.type == 'entrance' else '2'
                for yy in range(r.y, r.y+r.h):
                    for xx in range(r.x, r.x+r.w):
                        self.grid[yy][xx] = mark

        return self.grid

# ---------- Dark-theme GUI ----------

def draw_grid(canvas, grid, ts):
    canvas.delete("all")
    cmap = {'#':'#000000', '.':'#333333', '1':'#33aa33', '2':'#aa3333'}
    for y, row in enumerate(grid):
        for x, t in enumerate(row):
            canvas.create_rectangle(
                x*ts, y*ts, (x+1)*ts, (y+1)*ts,
                fill=cmap.get(t,'#555555'), outline=''
            )

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.bg = '#2e2e2e'; self.fg = '#ffffff'
        self.ent_bg = '#3c3f41'; self.btn_bg = '#5c5f61'; self.hl = '#4a4a4a'
        self.canvas_bg = '#212121'
        self.title("Procedural Dungeon Generator")
        self.defaults = {
            'map_width':32, 'map_height':32,
            'room_min_size':3, 'room_max_size':7,
            'corridor_min_length':3, 'corridor_max_length':15,
            'normal_room_count_min':5, 'normal_room_count_max':10,
            'special_room_count':2, 'special_room_chance':0.5,
            'tile_size':20, 'seed':''
        }
        self.entries = {}
        self.grid = None
        self._build_ui()

    def _build_ui(self):
        self.config(bg=self.bg)
        menubar = tk.Menu(self, bg=self.bg, fg=self.fg)
        filem = tk.Menu(menubar, tearoff=0, bg=self.bg, fg=self.fg)
        filem.add_command(label="Import Map...", command=self.on_import)
        filem.add_command(label="Export Map...", command=self.on_export)
        filem.add_command(label="Save Image...", command=self.on_save_image)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=filem)
        helpm = tk.Menu(menubar, tearoff=0, bg=self.bg, fg=self.fg)
        helpm.add_command(label="About", command=lambda: messagebox.showinfo("About","Procedural Dungeon Generator\nDark Theme"))
        menubar.add_cascade(label="Help", menu=helpm)
        self.config(menu=menubar)

        ctrl = tk.Frame(self, bg=self.bg)
        ctrl.pack(side='left', fill='y', padx=5, pady=5)
        row = 0
        for key, val in self.defaults.items():
            tk.Label(ctrl, text=key.replace('_',' ').title(), bg=self.bg, fg=self.fg).grid(row=row, column=0, sticky='w')
            var = tk.StringVar(value=str(val))
            ent = tk.Entry(ctrl, textvariable=var, bg=self.ent_bg, fg=self.fg, insertbackground=self.fg, relief='flat', width=8)
            ent.grid(row=row, column=1, padx=2, pady=2)
            self.entries[key] = var
            if key == 'seed':
                tk.Button(ctrl, text="🎲", command=self.on_random_seed, bg=self.btn_bg, fg=self.fg, bd=0, activebackground=self.hl).grid(row=row, column=2, padx=2)
            row += 1

        tk.Button(ctrl, text="Generate", command=self.on_generate, bg=self.btn_bg, fg=self.fg, activebackground=self.hl).grid(row=row, column=0, columnspan=3, pady=5, sticky='we')
        row += 1
        tk.Button(ctrl, text="Reset Defaults", command=self.on_reset, bg=self.btn_bg, fg=self.fg, activebackground=self.hl).grid(row=row, column=0, columnspan=3, pady=5, sticky='we')

        self.status = tk.Label(self, text="Ready", anchor='w', bg=self.bg, fg=self.fg)
        self.status.pack(side='bottom', fill='x')

        ts = int(self.defaults['tile_size'])
        w = int(self.defaults['map_width']) * ts
        h = int(self.defaults['map_height']) * ts
        self.canvas = tk.Canvas(self, width=w, height=h, bg=self.canvas_bg, highlightthickness=0)
        self.canvas.pack(side='right', padx=5, pady=5)

    def on_generate(self):
        try:
            params = {k:int(self.entries[k].get()) for k in (
                'map_width','map_height','room_min_size','room_max_size',
                'corridor_min_length','corridor_max_length',
                'normal_room_count_min','normal_room_count_max','special_room_count')}
            params['special_room_chance'] = float(self.entries['special_room_chance'].get())
            s = self.entries['seed'].get().strip()
            params['seed'] = int(s) if s else None
            ts = int(self.entries['tile_size'].get())
            gen = MapGenerator(**params)
            grid = gen.generate()
            self.grid = grid
            self.entries['seed'].set(str(gen.seed))
            self.canvas.config(width=params['map_width']*ts, height=params['map_height']*ts)
            draw_grid(self.canvas, grid, ts)
            self.title(f"Dungeon Generator – Seed: {gen.seed}")
            self.status.config(text="Map generated")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_reset(self):
        for k,v in self.defaults.items():
            self.entries[k].set(str(v))
        self.status.config(text="Defaults restored")

    def on_random_seed(self):
        s = random.randrange(1 << 30)
        self.entries['seed'].set(str(s))
        self.status.config(text="Seed randomized")

    def on_export(self):
        if not self.grid:
            messagebox.showwarning("No map", "Generate a map first")
            return
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text","*.txt")])
        if not f: return
        with open(f, 'w') as out:
            for row in self.grid:
                out.write(''.join(row) + '\n')
        messagebox.showinfo("Export", f"Map exported to {f}")

    def on_import(self):
        f = filedialog.askopenfilename(filetypes=[("Text","*.txt")])
        if not f: return
        with open(f) as inp:
            lines = [l.rstrip('\n') for l in inp]
        grid = [list(r) for r in lines]
        self.grid = grid
        ts = int(self.entries['tile_size'].get())
        self.canvas.config(width=len(grid[0])*ts, height=len(grid)*ts)
        draw_grid(self.canvas, grid, ts)
        self.status.config(text="Map imported")

    def on_save_image(self):
        if not self.grid:
            messagebox.showwarning("No map", "Generate a map first")
            return
        f = filedialog.asksaveasfilename(defaultextension=".ps", filetypes=[("PostScript","*.ps")])
        if not f: return
        self.canvas.postscript(file=f)
        messagebox.showinfo("Save Image", f"PostScript saved to {f}")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
