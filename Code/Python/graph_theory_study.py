# This was vibecoded

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sliding Puzzle Graph — Tkinter 3D Wireframe (offline, single file)

Controls
- Left-drag: orbit
- Right-drag: pan
- Wheel: zoom
- Click a node: fills Source (first) then Target (second)
- Buttons: Generate, Run Layout, Reset View, Compute Route (BFS/A*), Clear Route

Notes
- Layout is O(N^2) per iteration. Keep Node limit ≲ 1500–2000 for responsiveness.
"""

import math
import time
import random
import tkinter as tk
from tkinter import ttk, messagebox

# -------------------------
# Utilities / RNG (seeded)
# -------------------------
def seeded_random(seed: str | None):
    if not seed:
        rnd = random.Random()
        return rnd.random
    h = 2166136261
    for ch in seed:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF

    def _rand():
        nonlocal h
        h ^= (h << 13) & 0xFFFFFFFF
        h ^= (h >> 17) & 0xFFFFFFFF
        h ^= (h << 5) & 0xFFFFFFFF
        return (h & 0xFFFFFFFF) / 4294967296.0

    return _rand

def key_of(state):
    return ",".join(str(x) for x in state)

def parse_state(s: str):
    try:
        return [int(x.strip()) for x in s.split(",")]
    except Exception:
        return None

# -------------------------
# Sliding Puzzle Mechanics
# -------------------------
def goal_state(rows, cols):
    n = rows * cols
    return [i + 1 for i in range(n - 1)] + [0]

def idx_to_rc(i, cols):
    return (i // cols, i % cols)

def rc_to_idx(r, c, cols):
    return r * cols + c

def neighbors(state, rows, cols):
    zi = state.index(0)
    zr, zc = idx_to_rc(zi, cols)
    out = []
    for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
        nr, nc = zr + dr, zc + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            ni = rc_to_idx(nr, nc, cols)
            s2 = state[:]
            s2[zi] = s2[ni]
            s2[ni] = 0
            out.append(s2)
    return out

def manhattan(state, rows, cols):
    total = 0
    for i, v in enumerate(state):
        if v == 0:
            continue
        r, c = divmod(i, cols)
        gr, gc = divmod(v - 1, cols)
        total += abs(r - gr) + abs(c - gc)
    return total

def scramble_from_goal(rows, cols, steps, rnd):
    s = goal_state(rows, cols)
    for _ in range(steps):
        nbrs = neighbors(s, rows, cols)
        s = nbrs[int(rnd() * len(nbrs))]
    return s

# -------------------------
# Graph Construction
# -------------------------
def build_graph(start, rows, cols, limit, include_returns=True):
    adj: dict[str, list[str]] = {}
    seen: set[str] = set()
    nodes: list[list[int]] = []

    sk = key_of(start)
    seen.add(sk)
    queue = [start]
    adj[sk] = []
    nodes.append(start)

    while queue and len(seen) < limit:
        u = queue.pop(0)
        uk = key_of(u)
        outs = neighbors(u, rows, cols)
        for v in outs:
            vk = key_of(v)
            adj.setdefault(uk, []).append(vk)
            if vk not in seen and len(seen) < limit:
                seen.add(vk)
                queue.append(v)
                adj.setdefault(vk, [])
                nodes.append(v)
            if not include_returns:
                rev = adj.get(vk)
                if rev and uk in rev:
                    rev.remove(uk)

    return adj, nodes

# -------------------------
# Shortest Paths
# -------------------------
def reconstruct(parent: dict[str, str | None], t: str):
    path = []
    cur = t
    while cur is not None:
        path.append(cur)
        cur = parent.get(cur)
    path.reverse()
    return path

def bfs_path(adj: dict[str, list[str]], s: str, t: str):
    if s not in adj or t not in adj:
        return []
    parent = {s: None}
    seen = {s}
    dq = [s]
    while dq:
        u = dq.pop(0)
        if u == t:
            return reconstruct(parent, u)
        for v in adj.get(u, []):
            if v not in seen:
                seen.add(v)
                parent[v] = u
                dq.append(v)
    return []

def astar_path(adj: dict[str, list[str]], s: str, t: str, rows: int, cols: int):
    if s not in adj or t not in adj:
        return []
    def H(k: str):
        return manhattan(parse_state(k), rows, cols)

    g = {s: 0}
    f = {s: H(s)}
    parent = {s: None}
    open_set = {s}
    pq = [(s, f[s])]

    def push(k, score):
        pq.append((k, score))
        pq.sort(key=lambda x: x[1])

    while pq:
        u, _ = pq.pop(0)
        if u not in open_set:
            continue
        open_set.remove(u)
        if u == t:
            return reconstruct(parent, u)
        for v in adj.get(u, []):
            tentative = g[u] + 1
            if tentative < g.get(v, 10**15):
                g[v] = tentative
                fv = tentative + H(v)
                f[v] = fv
                parent[v] = u
                open_set.add(v)
                push(v, fv)
    return []

# -------------------------
# 3D Camera & Math
# -------------------------
def v_add(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def v_sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def v_mul(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def v_dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def v_cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def v_norm(a): return math.sqrt(a[0]*a[0]+a[1]*a[1]+a[2]*a[2])
def v_normalize(a):
    n = v_norm(a)
    return (a[0]/n, a[1]/n, a[2]/n) if n > 1e-12 else (0.0, 0.0, 0.0)

class Camera:
    def __init__(self):
        self.target = (0.0, 0.0, 0.0)
        self.radius = 18.0
        self.theta = math.pi/6
        self.phi = math.pi/4
        self.fov = math.radians(60.0)
        self.aspect = 1.0

    def get_pos(self):
        x = self.target[0] + self.radius * math.cos(self.phi) * math.cos(self.theta)
        y = self.target[1] + self.radius * math.sin(self.phi)
        z = self.target[2] + self.radius * math.cos(self.phi) * math.sin(self.theta)
        return (x, y, z)

    def get_basis(self):
        eye = self.get_pos()
        fwd = v_normalize(v_sub(self.target, eye))
        up = (0.0, 1.0, 0.0)
        side = v_normalize(v_cross(fwd, up))
        uvec = v_cross(side, fwd)
        return eye, fwd, side, uvec

    def project(self, p, width, height):
        eye, fwd, side, uvec = self.get_basis()
        rel = v_sub(p, eye)
        x = v_dot(rel, side)
        y = v_dot(rel, uvec)
        z = v_dot(rel, fwd)  # positive in front
        if z <= 0:
            return None
        tan = math.tan(self.fov/2.0)
        nx = x / (z * tan * self.aspect)
        ny = y / (z * tan)
        sx = int((nx * 0.5 + 0.5) * width)
        sy = int((1.0 - (ny * 0.5 + 0.5)) * height)
        return sx, sy, z

# -------------------------
# FR Layout in 3D
# -------------------------
def fr3d_layout(adj: dict[str, list[str]], nodes: list[list[int]], iters=700, k=1.4, cooling=0.95, seed=""):
    rnd = seeded_random(seed or "")
    pos: dict[str, list[float]] = { key_of(s): [rnd()-0.5, rnd()-0.5, rnd()-0.5] for s in nodes }

    # unique undirected edge list
    seen_edges = set()
    for u, outs in adj.items():
        for v in outs:
            a = (u, v) if u < v else (v, u)
            seen_edges.add(a)
    edges = list(seen_edges)

    def repulse_mag(d2, k2):
        if d2 <= 1e-12: return 0.0
        return k2 / math.sqrt(d2)

    def attract_mag(d, kk):
        return (d*d) / kk

    t = 0.12
    k2 = k * k
    keys = list(adj.keys())
    for _ in range(iters):
        disp = {u: [0.0, 0.0, 0.0] for u in keys}

        # O(N^2) repulsion
        for i in range(len(keys)):
            u = keys[i]
            pu = pos[u]
            for j in range(i+1, len(keys)):
                v = keys[j]
                pv = pos[v]
                dx = pu[0]-pv[0]; dy=pu[1]-pv[1]; dz=pu[2]-pv[2]
                d2 = dx*dx + dy*dy + dz*dz
                m = repulse_mag(d2, k2)
                if m > 0.0:
                    inv = 1.0 / math.sqrt(d2)
                    fx = dx * inv * m; fy = dy * inv * m; fz = dz * inv * m
                    du = disp[u]; dv = disp[v]
                    du[0]+=fx; du[1]+=fy; du[2]+=fz
                    dv[0]-=fx; dv[1]-=fy; dv[2]-=fz

        # attraction
        for (u,v) in edges:
            pu = pos[u]; pv = pos[v]
            dx = pv[0]-pu[0]; dy = pv[1]-pu[1]; dz = pv[2]-pu[2]
            d2 = dx*dx + dy*dy + dz*dz
            d = math.sqrt(d2) if d2 > 1e-12 else 1e-6
            m = attract_mag(d, k)
            fx = (dx/d) * m; fy = (dy/d) * m; fz = (dz/d) * m
            du = disp[u]; dv = disp[v]
            du[0]+=fx; du[1]+=fy; du[2]+=fz
            dv[0]-=fx; dv[1]-=fy; dv[2]-=fz

        # apply with temperature cap + mild contraction
        for u, d in disp.items():
            dx, dy, dz = d
            norm = math.sqrt(dx*dx + dy*dy + dz*dz)
            if norm > 0:
                s = min(t, norm) / norm
                p = pos[u]
                p[0] += dx*s; p[1] += dy*s; p[2] += dz*s
        t *= cooling
        for u in keys:
            p = pos[u]
            p[0] *= 0.998; p[1] *= 0.998; p[2] *= 0.998

    return pos

# -------------------------
# Tkinter Application
# -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sliding Puzzle Graph — Tkinter 3D Wireframe (Offline)")
        self.geometry("1200x800")
        self.minsize(1000, 650)

        # Left control panel
        self.sidebar = ttk.Frame(self, padding=8)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        # Right: canvas
        self.canvas = tk.Canvas(self, bg="#0a0f14", highlightthickness=0)
        self.canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # State variables
        self.rows = tk.IntVar(value=2)
        self.cols = tk.IntVar(value=2)
        self.scramble = tk.IntVar(value=12)
        self.limit = tk.IntVar(value=800)
        self.seed = tk.StringVar(value="")
        self.include_returns = tk.BooleanVar(value=True)

        self.iters = tk.IntVar(value=200)
        self.k = tk.DoubleVar(value=1.4)
        self.cooling = tk.DoubleVar(value=0.95)

        self.node_size = tk.DoubleVar(value=4.0)
        self.edge_width = tk.DoubleVar(value=1.5)
        self.edge_alpha = tk.DoubleVar(value=0.7)  # note: Tk canvas doesn't do alpha for lines; kept for API consistency
        self.show_edges = tk.BooleanVar(value=True)
        self.path_width = tk.DoubleVar(value=5.0)
        self.glow_path = tk.BooleanVar(value=True)

        self.algo = tk.StringVar(value="bfs")
        self.src_state = tk.StringVar(value="")
        self.dst_state = tk.StringVar(value="")

        # Camera / world
        self.camera = Camera()
        self.world_scale = 20.0

        # Data
        self.current_adj: dict[str, list[str]] | None = None
        self.current_nodes: list[list[int]] | None = None
        self.current_pos: dict[str, list[float]] | None = None
        self.state_keys: list[str] = []
        self.index_by_key: dict[str, int] = {}
        self.path_keys: list[str] | None = None

        # Build UI
        self._build_controls()
        self._bind_canvas_events()

        # Build initial graph (after the window is on screen)
        self.after(100, self.generate_graph)
        # Start render loop
        self.after(16, self._render_loop)

    # ---- UI creation ----
    def _section(self, parent, title):
        frm = ttk.Labelframe(parent, text=title, padding=6)
        frm.pack(fill=tk.X, pady=6)
        return frm

    def _build_controls(self):
        # Generator
        gen = self._section(self.sidebar, "Generator")
        self._labeled_spin(gen, "Rows", self.rows, 2, 5, 1)
        self._labeled_spin(gen, "Cols", self.cols, 2, 5, 1)
        self._labeled_spin(gen, "Scramble moves", self.scramble, 0, 300, 1)
        self._labeled_spin(gen, "Node limit", self.limit, 20, 5000, 10)
        self._labeled_entry(gen, "Random seed", self.seed)
        self._labeled_check(gen, "Include return edges", self.include_returns)

        btn_row = ttk.Frame(gen); btn_row.pack(fill=tk.X, pady=4)
        ttk.Button(btn_row, text="Generate", command=self.generate_graph).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_row, text="Reset View", command=self.reset_view).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Layout
        lay = self._section(self.sidebar, "Layout (3D Force-Directed)")
        self._labeled_spin(lay, "Iterations", self.iters, 50, 4000, 50)
        self._labeled_float(lay, "k (edge length)", self.k, 0.1, 5.0, 0.05)
        self._labeled_float(lay, "Cooling (0.90–0.99)", self.cooling, 0.90, 0.99, 0.005)
        ttk.Button(lay, text="Run Layout", command=self.run_layout).pack(fill=tk.X, pady=4)

        # Styling
        sty = self._section(self.sidebar, "Styling")
        self._labeled_float(sty, "Node size (px)", self.node_size, 0.5, 12, 0.5)
        self._labeled_float(sty, "Edge width (px)", self.edge_width, 0.5, 4, 0.5)
        self._labeled_float(sty, "Path width (px)", self.path_width, 1.0, 10.0, 0.5)
        self._labeled_check(sty, "Show edges", self.show_edges)
        self._labeled_check(sty, "Glow path", self.glow_path)

        # Routing
        rou = self._section(self.sidebar, "Routing")
        algo_row = ttk.Frame(rou); algo_row.pack(fill=tk.X, pady=2)
        ttk.Label(algo_row, text="Algorithm").pack(side=tk.LEFT)
        ttk.OptionMenu(algo_row, self.algo, self.algo.get(), "bfs", "astar").pack(side=tk.LEFT, padx=6)

        self._labeled_entry(rou, "Source node", self.src_state)
        self._labeled_entry(rou, "Target node", self.dst_state)

        rbtns = ttk.Frame(rou); rbtns.pack(fill=tk.X, pady=4)
        ttk.Button(rbtns, text="Compute Route", command=self.compute_route).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(rbtns, text="Clear Route", command=self.clear_route).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Goal/Start labels
        self.goal_var = tk.StringVar(value="–")
        self.start_var = tk.StringVar(value="–")
        meta = self._section(self.sidebar, "Meta")
        ttk.Label(meta, text="Goal:").pack(anchor=tk.W)
        ttk.Label(meta, textvariable=self.goal_var, foreground="#66d9ef").pack(anchor=tk.W)
        ttk.Label(meta, text="Start:").pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(meta, textvariable=self.start_var, foreground="#a6e22e").pack(anchor=tk.W)

        # Status
        self.stats_var = tk.StringVar(value="nodes: 0 • edges: 0 • layout: 0 ms")
        st = self._section(self.sidebar, "Stats")
        ttk.Label(st, textvariable=self.stats_var).pack(anchor=tk.W)

        # Theme
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

    def _labeled_spin(self, parent, label, var, mn, mx, step):
        row = ttk.Frame(parent); row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        sp = ttk.Spinbox(row, textvariable=var, from_=mn, to=mx, increment=step, width=10)
        sp.pack(side=tk.LEFT)

    def _labeled_float(self, parent, label, var, mn, mx, step):
        row = ttk.Frame(parent); row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        ent = ttk.Spinbox(row, textvariable=var, from_=mn, to=mx, increment=step, width=10)
        ent.pack(side=tk.LEFT)

    def _labeled_entry(self, parent, label, var):
        row = ttk.Frame(parent); row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        ent = ttk.Entry(row, textvariable=var, width=24)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _labeled_check(self, parent, label, var):
        chk = ttk.Checkbutton(parent, text=label, variable=var)
        chk.pack(anchor=tk.W, pady=2)

    # ---- Canvas interactions ----
    def _bind_canvas_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag_left)
        self.canvas.bind("<ButtonPress-3>", self._on_mouse_down)
        self.canvas.bind("<B3-Motion>", self._on_mouse_drag_right)
        self.canvas.bind("<ButtonRelease-1>", lambda e: None)
        self.canvas.bind("<ButtonRelease-3>", lambda e: None)
        self.canvas.bind("<Button-1>", self._on_click_select)
        self.canvas.bind("<MouseWheel>", self._on_wheel)     # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._zoom(+1))  # Linux
        self.canvas.bind("<Button-5>", lambda e: self._zoom(-1))  # Linux
        self._last_x = None
        self._last_y = None

    def _on_mouse_down(self, event):
        self._last_x, self._last_y = event.x, event.y

    def _on_mouse_drag_left(self, event):
        if self._last_x is None:
            self._last_x, self._last_y = event.x, event.y
            return
        dx = event.x - self._last_x
        dy = event.y - self._last_y
        self._last_x, self._last_y = event.x, event.y
        self.camera.theta -= dx * 0.005
        self.camera.phi += dy * 0.005
        self.camera.phi = max(0.05, min(math.pi - 0.05, self.camera.phi))

    def _on_mouse_drag_right(self, event):
        if self._last_x is None:
            self._last_x, self._last_y = event.x, event.y
            return
        dx = event.x - self._last_x
        dy = event.y - self._last_y
        self._last_x, self._last_y = event.x, event.y

        s = self.camera.radius * 0.002
        _, _, side, uvec = self.camera.get_basis()
        t = self.camera.target
        self.camera.target = (
            t[0] - side[0]*dx*s + uvec[0]*dy*s,
            t[1] - side[1]*dx*s + uvec[1]*dy*s,
            t[2] - side[2]*dx*s + uvec[2]*dy*s,
        )

    def _on_wheel(self, event):
        delta = 1 if event.delta > 0 else -1
        self._zoom(delta)

    def _zoom(self, direction):
        f = math.pow(1.12, -direction)  # direction +1 zoom in => smaller radius
        self.camera.radius = max(3.0, min(200.0, self.camera.radius * f))

    def _on_click_select(self, event):
        if self.current_adj is None or self.current_pos is None:
            return
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        best = None
        best_d2 = (self.node_size.get() * 8.0) ** 2

        for k in self.state_keys:
            p = self.current_pos.get(k)
            if p is None:
                continue
            P = self.camera.project((p[0]*self.world_scale, p[1]*self.world_scale, p[2]*self.world_scale), w, h)
            if P is None:
                continue
            x, y, _ = P
            dx = x - event.x
            dy = y - event.y
            d2 = dx*dx + dy*dy
            if d2 < best_d2:
                best_d2 = d2
                best = k
        if best:
            if not self.src_state.get():
                self.src_state.set(best)
            elif not self.dst_state.get():
                self.dst_state.set(best)
            else:
                self.dst_state.set(best)

    # ---- Build / layout / frame ----
    def generate_graph(self):
        rows = self.rows.get()
        cols = self.cols.get()
        scramble = self.scramble.get()
        limit = self.limit.get()
        seed = self.seed.get()
        include_returns = self.include_returns.get()

        rnd = seeded_random(seed or "")
        start = scramble_from_goal(rows, cols, scramble, rnd)
        goal = goal_state(rows, cols)

        self.goal_var.set(key_of(goal))
        self.start_var.set(key_of(start))

        adj, nodes = build_graph(start, rows, cols, limit, include_returns)
        # layout
        t0 = time.perf_counter()
        pos = fr3d_layout(adj, nodes, iters=self.iters.get(), k=self.k.get(), cooling=self.cooling.get(), seed=seed or "")
        t1 = time.perf_counter()

        self.current_adj = adj
        self.current_nodes = nodes
        self.current_pos = pos
        self.state_keys = list(adj.keys())
        self.index_by_key = {k:i for i, k in enumerate(self.state_keys)}
        self.path_keys = None

        self._update_stats((t1 - t0) * 1000.0)
        # preset source/target
        self.src_state.set(key_of(start))
        self.dst_state.set(key_of(goal))
        # frame camera
        self.reset_view()

    def run_layout(self):
        if self.current_adj is None or self.current_nodes is None:
            return
        t0 = time.perf_counter()
        self.current_pos = fr3d_layout(self.current_adj, self.current_nodes,
                                       iters=self.iters.get(),
                                       k=self.k.get(),
                                       cooling=self.cooling.get(),
                                       seed=self.seed.get() or "")
        t1 = time.perf_counter()
        self._update_stats((t1 - t0) * 1000.0)
        self.path_keys = None
        self.reset_view()

    def compute_route(self):
        if self.current_adj is None:
            return
        s = self.src_state.get().strip()
        t = self.dst_state.get().strip()
        if s not in self.current_adj or t not in self.current_adj:
            messagebox.showwarning("Not in graph", "Source or target is not part of the current graph.")
            return
        if self.algo.get() == "astar":
            path = astar_path(self.current_adj, s, t, self.rows.get(), self.cols.get())
        else:
            path = bfs_path(self.current_adj, s, t)
        if not path or len(path) < 2:
            messagebox.showinfo("No path", "No route found within the explored graph. Increase node limit or reduce scramble.")
            return
        self.path_keys = path

    def clear_route(self):
        self.path_keys = None

    def reset_view(self):
        if not self.current_pos or not self.current_adj:
            return
        # Bounding sphere
        cx = cy = cz = 0.0
        n = 0
        for k in self.current_adj.keys():
            p = self.current_pos[k]
            cx += p[0]; cy += p[1]; cz += p[2]; n += 1
        if n == 0:
            return
        cx /= n; cy /= n; cz /= n
        r2 = 0.0
        for k in self.current_adj.keys():
            p = self.current_pos[k]
            dx = p[0]-cx; dy = p[1]-cy; dz = p[2]-cz
            d2 = dx*dx + dy*dy + dz*dz
            if d2 > r2:
                r2 = d2
        radius = math.sqrt(r2) * self.world_scale
        self.camera.target = (cx*self.world_scale, cy*self.world_scale, cz*self.world_scale)
        fit = max(12.0, radius * 3.2)  # a little further to be safe
        self.camera.radius = fit
        self.camera.theta = math.pi/6
        self.camera.phi = math.pi/4

    # ---- Rendering ----
    def _render_loop(self):
        self._draw_scene()
        self.after(16, self._render_loop)  # ~60 FPS target

    def _draw_scene(self):
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        # Always keep camera aspect up-to-date
        self.camera.aspect = w / float(h)

        self.canvas.delete("all")
        # Background
        self.canvas.create_rectangle(0, 0, w, h, fill="#0a0f14", outline="")
        # Corner axes (visibility indicator)
        self.canvas.create_line(10, h-10, 90, h-10, fill="#22c6ff", width=2)
        self.canvas.create_line(10, h-10, 10, h-90, fill="#ff4be3", width=2)

        if self.current_adj is None or self.current_pos is None:
            return

        # Project all nodes
        proj: dict[str, tuple[int,int,float]] = {}
        for k in self.state_keys:
            p = self.current_pos.get(k)
            if p is None:
                continue
            P = self.camera.project((p[0]*self.world_scale, p[1]*self.world_scale, p[2]*self.world_scale), w, h)
            if P is not None:
                proj[k] = P

        # If somehow nothing visible, try an automatic reframe once
        if not proj and self.current_adj:
            self.reset_view()
            for k in self.state_keys:
                p = self.current_pos.get(k)
                if p is None:
                    continue
                P = self.camera.project((p[0]*self.world_scale, p[1]*self.world_scale, p[2]*self.world_scale), w, h)
                if P is not None:
                    proj[k] = P

        # Edges
        if self.show_edges.get() and proj:
            lines = []
            for u, outs in self.current_adj.items():
                Pu = proj.get(u)
                if Pu is None:
                    continue
                for v in outs:
                    Pv = proj.get(v)
                    if Pv is None:
                        continue
                    z = max(Pu[2], Pv[2])
                    lines.append((z, Pu[0], Pu[1], Pv[0], Pv[1]))
            # draw far -> near
            lines.sort(key=lambda e: -e[0])
            color = "#23c0d0"
            for _, x1, y1, x2, y2 in lines:
                self.canvas.create_line(x1, y1, x2, y2, fill=color, width=self.edge_width.get(), capstyle=tk.ROUND, joinstyle=tk.ROUND)

        # Path highlight
        if self.path_keys and len(self.path_keys) > 1 and proj:
            pts = []
            ok = True
            for k in self.path_keys:
                P = proj.get(k)
                if P is None:
                    ok = False
                    break
                pts.append((P[0], P[1]))
            if ok and len(pts) >= 2:
                coords = [c for xy in pts for c in xy]
                if self.glow_path.get():
                    self.canvas.create_line(*coords, fill="#00e5ff", width=self.path_width.get()*1.6, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self.canvas.create_line(*coords, fill="#ff00e5", width=self.path_width.get(), capstyle=tk.ROUND, joinstyle=tk.ROUND)

        # Nodes (near-to-far for nicer layering)
        if proj:
            nodes_draw = [(P[2], P[0], P[1]) for k, P in proj.items()]
            nodes_draw.sort(key=lambda e: -e[0])
            r = self.node_size.get()
            for _, x, y in nodes_draw:
                # outer halo
                self.canvas.create_oval(x-r*2.6, y-r*2.6, x+r*2.6, y+r*2.6, outline="", fill="#0c2a33")
                # core
                self.canvas.create_oval(x-r, y-r, x+r, y+r, outline="", fill="#6ff2ff")

        # On-screen status
        if self.current_adj is not None:
            m = sum(len(v) for v in self.current_adj.values())
            self.canvas.create_text(12, 14, anchor="w", fill="#9ad1ff",
                                    text=f"nodes: {len(self.current_adj)}  edges: {m}",
                                    font=("TkDefaultFont", 10, "bold"))

    # ---- Helpers ----
    def _update_stats(self, layout_ms):
        if self.current_adj is None:
            self.stats_var.set("nodes: 0 • edges: 0 • layout: 0 ms")
            return
        m = sum(len(v) for v in self.current_adj.values())
        self.stats_var.set(f"nodes: {len(self.current_adj)} • edges: {m} • layout: {layout_ms:.0f} ms")


if __name__ == "__main__":
    App().mainloop()
