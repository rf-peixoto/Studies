#!/usr/bin/env python3
"""
mycelium.py — Fungal Colony Simulation

Architecture
============
The map is a 96×24 grid of cells.  Each cell is NOT a single fungus
object—it is a patch of substrate that may be colonised by up to four
competing species simultaneously.  State is stored as flat Python lists
for cache-friendliness; all indexing is row-major (i = y*W + x).

Biological model (simplified but grounded)
==========================================
  nutrients   How much soluble nutrient is available 0–1.
              Substrate slowly regenerates nutrients up to its cap.
  moisture    Water content 0–1.  Diffuses slowly; each substrate type
              has a natural resting level.
  enzymes     Extracellular enzyme pool 0–2.  Secreted by living mycelium;
              breaks substrate into nutrients; decays each turn.
  toxins      Chemical inhibitor pool 0–1.  Secreted by toxic species;
              diffuses into neighbours; kills / inhibits non-resistant species.
  biomass[s]  Mycelium density of species s in this cell, 0–10.
              Grows when nutrients are available; decays from maintenance
              cost, toxin exposure, and competition.  Dead biomass returns
              a fraction of nutrients to the soil.

Four species
============
  Saprotroph  (GREEN)    Balanced decomposer.  Secretes many enzymes,
                         exploits all substrate types.  Mid growth speed.
  Parasitic   (RED)      Fast-growing.  Steals biomass from adjacent cells
                         of other species rather than decomposing substrate.
  Network     (CYAN)     Slow but resilient.  Shares nutrients across
                         connected mycelial strands (mycorrhizal model).
                         Long-range spore dispersal.
  Toxic       (MAGENTA)  Chemical warfare specialist.  Floods its territory
                         with toxins; fully immune to own exudate.  Other
                         species cannot colonise a heavily toxic zone.

Rock-paper-scissors dynamic
============================
  Saprotroph  → beaten by Parasitic (which steals its accumulated biomass)
  Parasitic   → beaten by Toxic     (which poisons the thief)
  Toxic       → beaten by Network   (which dilutes toxins via nutrient sharing
                                     and tolerates low-level pollution)
  Network     → beaten by Saprotroph (better enzyme production, outcompetes
                                      on raw nutrient extraction)

Fruiting bodies
===============
When a colony accumulates enough biomass and meets moisture/nutrient
thresholds, it probabilistically forms a fruiting body ('&').  After 18
turns the fruiting body sporulates: spores are scattered in random
directions up to the species' range, seeding new colonies.

Controls
========
  q   quit
  p   pause / resume
  r   new world
  +   drop a deadwood patch at a random location
  1-4 inject a spore burst of species 0-3 at a random location
"""

import collections
import curses
import math
import random
import time

# ─── World dimensions & timing ───────────────────────────────────────────────
W    = 96
H    = 24
TICK = 0.11        # seconds between update steps

# ─── Substrate table ─────────────────────────────────────────────────────────
# key → (max_nutrients, regen_per_turn, natural_moisture, display_char)
SUBSTRATE = {
    '.': (0.40, 0.0018, 0.30, '.'),   # bare soil       — baseline
    '#': (1.00, 0.0007, 0.18, '#'),   # deadwood        — richest, slow regen
    '~': (0.38, 0.0026, 0.85, '~'),   # wetland         — moisture source
    '*': (0.65, 0.0130, 0.38, '*'),   # leaf litter     — fast nutrient cycling
    'R': (0.00, 0.0000, 0.04, ' '),   # bare rock       — sterile, impassable
}

# ─── Species parameters ───────────────────────────────────────────────────────
#
#  growth     Intrinsic growth rate coefficient.
#  maint      Maintenance cost per unit biomass per turn.
#  enzyme     Enzyme secretion per unit biomass.
#  nutr_eff   Nutrient uptake efficiency (higher → extracts more per unit).
#  toxin_prod Toxin secretion per unit biomass.
#  toxin_res  Fraction of toxin damage that is negated (0=fragile, 1=immune).
#  moist_opt  Optimal moisture level; growth falls off either side.
#  spore_r    Maximum spore dispersal radius when fruiting.
#  fruit_thr  Minimum biomass required to form a fruiting body.
#  steal      Fraction of neighbour biomass stolen per turn (Parasitic only).
#  share      Fraction of nutrient gradient transferred per turn (Network only).

SPECIES = [
    # 0 — Saprotroph
    dict(name='Saprotroph', char='f', cp=1,
         growth=0.88, maint=0.048, enzyme=1.90, nutr_eff=1.00,
         toxin_prod=0.04, toxin_res=0.35, moist_opt=0.55,
         spore_r=6,  fruit_thr=5.0, steal=0.00, share=0.000),

    # 1 — Parasitic
    dict(name='Parasitic',  char='p', cp=2,
         growth=1.30, maint=0.082, enzyme=0.35, nutr_eff=1.65,
         toxin_prod=0.30, toxin_res=0.62, moist_opt=0.48,
         spore_r=4,  fruit_thr=3.5, steal=0.13, share=0.000),

    # 2 — Network
    dict(name='Network',    char='n', cp=3,
         growth=0.54, maint=0.033, enzyme=0.85, nutr_eff=0.68,
         toxin_prod=0.04, toxin_res=0.55, moist_opt=0.70,
         spore_r=12, fruit_thr=5.5, steal=0.00, share=0.090),

    # 3 — Toxic
    dict(name='Toxic',      char='t', cp=4,
         growth=0.80, maint=0.058, enzyme=1.10, nutr_eff=1.10,
         toxin_prod=2.40, toxin_res=1.00, moist_opt=0.50,
         spore_r=5,  fruit_thr=5.0, steal=0.00, share=0.000),
]
NS = len(SPECIES)

# ─── Visual helpers ───────────────────────────────────────────────────────────
_SPARK = ' ▁▂▃▄▅▆▇█'


def sparkline(history, width=12):
    vals = list(history)[-width:]
    if not vals:
        return ' ' * width
    mx = max(vals) or 1e-9
    return ''.join(_SPARK[min(8, int(v / mx * 8))] for v in vals).ljust(width)


def bio_char(bm):
    """Map biomass density to an ASCII density glyph."""
    if bm < 0.5:  return ';'   # trace hyphae
    if bm < 2.0:  return ','   # sparse network
    if bm < 4.5:  return 'o'   # established colony
    if bm < 7.0:  return 'O'   # dense mycelium mat
    return '@'                  # maximum density


# ─── World ────────────────────────────────────────────────────────────────────
class World:

    def __init__(self):
        N          = W * H
        self.turn  = 0
        self.events = collections.deque(maxlen=5)

        # Per-cell environmental state (flat lists, row-major)
        self.sub   = ['.'] * N    # substrate type char
        self.nutr  = [0.0] * N    # nutrient level   0–1
        self.moist = [0.0] * N    # moisture         0–1
        self.toxin = [0.0] * N    # toxin conc.      0–1
        self.enzy  = [0.0] * N    # enzyme conc.     0–2

        # Mycelium biomass per species:  bio[s][cell]  0–10
        self.bio = [[0.0] * N for _ in range(NS)]

        # Fruiting bodies:  fruit[i] = 0 (none) or species+1
        self.fruit     = [0] * N
        self.fruit_age = [0] * N

        # Population history for sparklines
        self.pop_hist = [collections.deque([0.0] * 20, maxlen=20)
                         for _ in range(NS)]

        # Pre-compute 8-connected neighbour index lists — avoids repeated
        # bounds-checking inside the hot update loop.
        self.nb = []
        for iy in range(H):
            for ix in range(W):
                nbs = []
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx2, ny2 = ix + dx, iy + dy
                        if 0 <= nx2 < W and 0 <= ny2 < H:
                            nbs.append(ny2 * W + nx2)
                self.nb.append(nbs)

        self._generate_terrain()
        self._seed_species()

    # ── Terrain generation ────────────────────────────────────────────────────

    def _generate_terrain(self):
        N = W * H
        for i in range(N):
            self.sub[i]   = '.'
            self.nutr[i]  = random.uniform(0.08, 0.28)
            self.moist[i] = random.uniform(0.18, 0.40)

        def place(sub, count, rlo, rhi, nlo, nhi, mlo, mhi):
            for _ in range(count):
                cx = random.randint(2, W - 3)
                cy = random.randint(1, H - 2)
                r  = random.randint(rlo, rhi)
                r2 = r * r
                for py in range(max(0, cy - r), min(H, cy + r + 1)):
                    for px in range(max(0, cx - r), min(W, cx + r + 1)):
                        # Oblate ellipse (wider than tall) looks organic
                        if 0.55 * (px - cx) ** 2 + (py - cy) ** 2 <= r2:
                            i = py * W + px
                            self.sub[i]   = sub
                            self.nutr[i]  = random.uniform(nlo, nhi)
                            self.moist[i] = random.uniform(mlo, mhi)

        place('#', 7, 2, 5, 0.50, 0.92, 0.10, 0.28)   # deadwood logs
        place('~', 5, 2, 4, 0.18, 0.44, 0.68, 0.92)   # wetland patches
        place('*', 11, 1, 3, 0.38, 0.70, 0.28, 0.52)  # leaf-litter clumps
        place('R', 7, 1, 3, 0.00, 0.00, 0.00, 0.06)   # rock outcrops

    def _seed_species(self):
        """Place each species in a separate corner quadrant of the map."""
        anchors = [
            (W // 7,     H // 4),      # top-left      → Saprotroph
            (W * 6 // 7, H // 4),      # top-right     → Parasitic
            (W // 7,     H * 3 // 4),  # bottom-left   → Network
            (W * 6 // 7, H * 3 // 4), # bottom-right  → Toxic
        ]
        for s, (cx, cy) in enumerate(anchors):
            for _ in range(6):
                x = max(0, min(W - 1, cx + random.randint(-4, 4)))
                y = max(0, min(H - 1, cy + random.randint(-2, 2)))
                i = y * W + x
                if self.sub[i] != 'R':
                    self.bio[s][i] = max(self.bio[s][i],
                                         random.uniform(0.7, 2.0))

    # ── Main update step ──────────────────────────────────────────────────────

    def update(self):
        self.turn += 1
        N = W * H

        # ── 1 ▸ Nutrient regeneration + moisture tendency ─────────────────
        for i in range(N):
            sub = self.sub[i]
            if sub == 'R':
                continue
            mx, regen, nat_m, _ = SUBSTRATE[sub]
            self.nutr[i]  = min(mx, self.nutr[i] + regen)
            # Moisture drifts back toward the substrate's natural level
            self.moist[i] += 0.030 * (nat_m - self.moist[i])

        # ── 2 ▸ Moisture diffusion (every 2 turns) ────────────────────────
        if self.turn % 2 == 0:
            nm = self.moist[:]
            for i in range(N):
                if self.sub[i] == 'R':
                    continue
                nbs = self.nb[i]
                if nbs:
                    avg = sum(self.moist[j] for j in nbs) / len(nbs)
                    nm[i] = nm[i] * 0.87 + avg * 0.13
            self.moist = nm

        # ── 3 ▸ Enzyme decomposition ──────────────────────────────────────
        # Enzymes secreted by living mycelium break down organic substrate,
        # releasing nutrients that all species in the cell can exploit.
        for i in range(N):
            e = self.enzy[i]
            if e < 0.005 or self.sub[i] == 'R':
                continue
            mx = SUBSTRATE[self.sub[i]][0]
            bonus = min(e * 0.055, mx * 0.008)
            self.nutr[i]  = min(mx, self.nutr[i] + bonus)
            self.enzy[i] = max(0.0, e - 0.042)

        # ── 4 ▸ Toxin diffusion + decay (every 2 turns) ───────────────────
        if self.turn % 2 == 0:
            nt = self.toxin[:]
            for i in range(N):
                t = self.toxin[i]
                if t < 0.004:
                    continue
                nt[i] = t * 0.91            # bulk decay
                spread = t * 0.024
                nbs    = self.nb[i]
                if nbs:
                    per = spread / len(nbs)
                    for j in nbs:
                        if nt[j] < 1.0:
                            nt[j] = min(1.0, nt[j] + per)
            self.toxin = nt

        # ── 5 ▸ Biomass: maintenance, feeding, growth ─────────────────────
        # We write into nb_bio (a scratch copy) to avoid within-turn
        # feedback between neighbouring cells.
        nb_bio = [b[:] for b in self.bio]

        for i in range(N):
            if self.sub[i] == 'R':
                continue

            total_bm = sum(self.bio[s][i] for s in range(NS))

            for s in range(NS):
                bm = self.bio[s][i]
                if bm < 0.005:
                    continue
                sp = SPECIES[s]

                # Secrete enzymes and toxins proportional to biomass
                self.enzy[i]  = min(2.0, self.enzy[i]  + bm * sp['enzyme']     * 0.004)
                self.toxin[i] = min(1.0, self.toxin[i] + bm * sp['toxin_prod'] * 0.003)

                # Nutrient uptake vs maintenance demand
                maint  = bm * sp['maint']
                uptake = min(self.nutr[i], maint * sp['nutr_eff'] * 1.25)
                self.nutr[i] -= uptake
                surplus = uptake / max(1e-6, sp['nutr_eff']) - maint

                # Moisture penalty (distance from optimum)
                mf = max(0.0, 1.0 - abs(self.moist[i] - sp['moist_opt']) * 2.2)

                # Environmental toxin damage (exclude own secretion this tick)
                own_t  = bm * sp['toxin_prod'] * 0.003
                env_t  = max(0.0, self.toxin[i] - own_t)
                t_dmg  = env_t * (1.0 - sp['toxin_res']) * 0.13

                # Crowding competition from co-colonisers
                crowd  = (total_bm - bm) * 0.016

                # Net biomass change
                if surplus >= 0:
                    gain  = bm * sp['growth'] * mf * (self.nutr[i] + 0.04) * 0.30
                    delta = gain - (t_dmg + crowd) * bm
                else:
                    # Starvation — faster collapse than growth
                    delta = surplus * 1.85 - t_dmg * bm

                nb_bio[s][i] = max(0.0, min(10.0, bm + delta * 0.1))

                # Dying biomass returns organic matter to soil
                if nb_bio[s][i] < 0.005 and bm > 0.005:
                    mx_n = SUBSTRATE[self.sub[i]][0]
                    self.nutr[i] = min(mx_n, self.nutr[i] + bm * 0.22)
                    nb_bio[s][i] = 0.0

        # ── 6 ▸ Hyphal spreading ──────────────────────────────────────────
        # Living mycelium at each cell probabilistically extends hyphae into
        # the most attractive neighbouring cell (highest nutrient × moisture
        # compatibility × toxin tolerance, biased toward less-colonised ground).
        for i in range(N):
            if self.sub[i] == 'R':
                continue
            nbs = self.nb[i]
            if not nbs:
                continue

            for s in range(NS):
                bm = nb_bio[s][i]
                if bm < 0.30:
                    continue
                sp = SPECIES[s]

                # Spreading likelihood scales with biomass and growth rate
                if random.random() > sp['growth'] * min(1.0, bm * 0.6) * 0.30:
                    continue

                # Score each candidate cell
                best_j, best_sc = None, -1.0
                for j in nbs:
                    if self.sub[j] == 'R':
                        continue
                    nsc = (
                        (self.nutr[j] + 0.05)
                        * max(0.1, 1.0 - abs(self.moist[j] - sp['moist_opt']) * 2.0)
                        * max(0.0, 1.0 - self.toxin[j] * (1.0 - sp['toxin_res']))
                        # Prefer less-colonised cells (invasion front dynamic)
                        * max(0.45, 1.45 - nb_bio[s][j] * 0.18)
                    )
                    if nsc > best_sc:
                        best_sc, best_j = nsc, j

                if best_j is not None and best_sc > 0.02:
                    amt = min(bm * 0.10, 0.42)
                    nb_bio[s][best_j] = min(10.0, nb_bio[s][best_j] + amt)

        self.bio = nb_bio   # commit new biomass state

        # ── 7 ▸ Parasitic stealing ────────────────────────────────────────
        # Parasitic mycelium at each cell siphons biomass from one adjacent
        # cell of a different species, converting it to local nutrients.
        for i in range(N):
            para = self.bio[1][i]
            if para < 0.20:
                continue
            sp_p = SPECIES[1]
            for j in self.nb[i]:
                for s in (0, 2, 3):
                    v = self.bio[s][j]
                    if v < 0.12:
                        continue
                    stolen = min(v * sp_p['steal'], 0.22)
                    self.bio[s][j] -= stolen
                    mx_n = SUBSTRATE[self.sub[i]][0]
                    self.nutr[i] = min(mx_n, self.nutr[i] + stolen * 0.32)
                    break       # steal from one species per neighbour

        # ── 8 ▸ Network nutrient sharing (every 3 turns) ──────────────────
        # Network mycelium equalises nutrient gradients across connected
        # cells — a crude model of cytoplasmic streaming in mycelial cords.
        if self.turn % 3 == 0:
            for i in range(N):
                if self.bio[2][i] < 0.30:
                    continue
                for j in self.nb[i]:
                    if self.bio[2][j] < 0.12:
                        continue
                    diff = self.nutr[i] - self.nutr[j]
                    if diff > 0.012:
                        tr   = diff * SPECIES[2]['share']
                        self.nutr[i] -= tr
                        mx_n = SUBSTRATE[self.sub[j]][0]
                        self.nutr[j] = min(mx_n, self.nutr[j] + tr)

        # ── 9 ▸ Fruiting bodies ───────────────────────────────────────────
        for i in range(N):
            if self.fruit[i]:
                self.fruit_age[i] += 1
                if self.fruit_age[i] >= 18:   # mature → sporulate
                    s  = self.fruit[i] - 1
                    sp = SPECIES[s]
                    x0, y0 = i % W, i // W
                    for _ in range(random.randint(3, 9)):
                        a   = random.uniform(0.0, 2.0 * math.pi)
                        d   = random.randint(2, sp['spore_r'])
                        nx2 = max(0, min(W - 1, round(x0 + d * math.cos(a))))
                        ny2 = max(0, min(H - 1, round(y0 + d * math.sin(a))))
                        j   = ny2 * W + nx2
                        if self.sub[j] != 'R':
                            self.bio[s][j] = max(self.bio[s][j], 0.45)
                    self.events.append(
                        f"T{self.turn}: {sp['name'][:5]} spored ({x0},{y0})")
                    self.fruit[i]     = 0
                    self.fruit_age[i] = 0
            else:
                # Check fruiting conditions
                for s in range(NS):
                    sp = SPECIES[s]
                    if (self.bio[s][i]  >= sp['fruit_thr']
                            and self.moist[i] > 0.40
                            and self.nutr[i]  > 0.14
                            and random.random() < 0.0026):
                        self.fruit[i]     = s + 1
                        self.fruit_age[i] = 0
                        x0, y0 = i % W, i // W
                        self.events.append(
                            f"T{self.turn}: {sp['name'][:5]} fruiting ({x0},{y0})")
                        break

        # ── 10 ▸ Random organic deposits ─────────────────────────────────
        # Models fallen leaves, dead animals, decomposing wood, etc.
        if random.random() < 0.006:
            x = random.randint(2, W - 3)
            y = random.randint(1, H - 2)
            i = y * W + x
            if self.sub[i] not in ('R',):
                kind         = random.choice(('#', '*', '*'))
                self.sub[i]  = kind
                mx_n         = SUBSTRATE[kind][0]
                self.nutr[i] = min(mx_n, self.nutr[i] + random.uniform(0.28, 0.55))
                self.moist[i]= min(0.82, self.moist[i] + 0.22)
                self.events.append(f"T{self.turn}: Deposit ({x},{y})")

        # ── 11 ▸ Population history ────────────────────────────────────────
        for s in range(NS):
            self.pop_hist[s].append(sum(self.bio[s]))


# ─── Rendering ────────────────────────────────────────────────────────────────

def render(stdscr, world, paused):
    stdscr.erase()
    N  = W * H
    CP = curses.color_pair
    AB = curses.A_BOLD
    AD = curses.A_DIM

    sub_style = {
        '.': (5, AD),
        '#': (6, 0),
        '~': (7, AD),
        '*': (8, AD),
        'R': (5, AD),
    }

    # ── Map ───────────────────────────────────────────────────────────────────
    for y in range(H):
        base = y * W
        for x in range(W):
            i = base + x

            # Fruiting body: show '&', pulsing bold/normal every 2 turns
            if world.fruit[i]:
                s    = world.fruit[i] - 1
                age  = world.fruit_age[i]
                attr = CP(SPECIES[s]['cp']) | (AB if age % 2 == 0 else 0)
                try:
                    stdscr.addch(y, x, '&', attr)
                except curses.error:
                    pass
                continue

            # Dominant species by biomass
            max_bm, dom = 0.0, -1
            for s in range(NS):
                b = world.bio[s][i]
                if b > max_bm:
                    max_bm, dom = b, s

            if max_bm >= 0.08 and dom >= 0:
                ch   = bio_char(max_bm)
                attr = CP(SPECIES[dom]['cp'])
                if   max_bm >= 6.5: attr |= AB
                elif max_bm <  0.8: attr |= AD
                try:
                    stdscr.addch(y, x, ch, attr)
                except curses.error:
                    pass
            else:
                sub         = world.sub[i]
                pair, att   = sub_style.get(sub, (5, AD))
                ch          = SUBSTRATE[sub][3]
                try:
                    stdscr.addch(y, x, ch, CP(pair) | att)
                except curses.error:
                    pass

    # ── Stats panel ───────────────────────────────────────────────────────────
    sx  = W + 2
    cp5 = CP(5)

    hdr = f"{'PAUSED  ' if paused else ''}Turn {world.turn:>5}"
    try:
        stdscr.addstr(0, sx, hdr, cp5 | AB)
    except curses.error:
        pass

    # Species rows: name + biomass total + sparkline
    for s, sp in enumerate(SPECIES):
        bm    = sum(world.bio[s])
        line  = f"{sp['name'][:6]:<6} {min(9999, int(bm)):>4}"
        spark = sparkline(world.pop_hist[s], 12)
        cps   = CP(sp['cp'])
        try:
            stdscr.addstr(2 + s, sx, line,  cps)
            stdscr.addstr(2 + s, sx + len(line) + 1, spark, cps | AD)
        except curses.error:
            pass

    # Environmental overview
    avN = sum(world.nutr)  / N
    avM = sum(world.moist) / N
    avT = sum(world.toxin) / N
    nFr = sum(1 for f in world.fruit if f)
    try:
        stdscr.addstr(7,  sx, f"Nutri  {avN:.2f}", cp5)
        stdscr.addstr(8,  sx, f"Moist  {avM:.2f}", cp5)
        stdscr.addstr(9,  sx, f"Toxin  {avT:.3f}", cp5)
        stdscr.addstr(10, sx, f"Fruit  {nFr}",     cp5)
    except curses.error:
        pass

    # Event log
    try:
        stdscr.addstr(12, sx, "Events", cp5 | AB)
        for j, ev in enumerate(reversed(world.events)):
            if 13 + j >= H:
                break
            stdscr.addstr(13 + j, sx, ev[:20], cp5 | AD)
    except curses.error:
        pass

    # Legend (bottom of panel)
    species_legend = [
        ("f Saprotroph", 1),
        ("p Parasitic",  2),
        ("n Network",    3),
        ("t Toxic",      4),
    ]
    env_legend = [
        ("& Fruiting  @ Dense", 5, 0),
        (", Thin      ; Trace",  5, AD),
        (". Soil  # Wood",       5, AD),
        ("~ Wet   * Litter",     5, AD),
        ("  Rock  (sterile)",    5, AD),
        ("q p r + 1-4 keys",     5, 0),
    ]
    leg_start = H - len(species_legend) - len(env_legend) - 1
    row = max(leg_start, 12)
    try:
        for text, pair in species_legend:
            stdscr.addstr(row, sx, text[:20], CP(pair))
            row += 1
        for text, pair, att in env_legend:
            stdscr.addstr(row, sx, text[:20], CP(pair) | att)
            row += 1
    except curses.error:
        pass

    stdscr.refresh()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(1)
    stdscr.timeout(int(TICK * 1000))

    curses.start_color()
    curses.use_default_colors()

    # Species colours
    curses.init_pair(1, curses.COLOR_GREEN,   -1)   # Saprotroph
    curses.init_pair(2, curses.COLOR_RED,     -1)   # Parasitic
    curses.init_pair(3, curses.COLOR_CYAN,    -1)   # Network
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)   # Toxic
    # UI and substrate colours
    curses.init_pair(5, curses.COLOR_WHITE,   -1)   # UI text / soil
    curses.init_pair(6, curses.COLOR_YELLOW,  -1)   # Deadwood
    curses.init_pair(7, curses.COLOR_BLUE,    -1)   # Wetland
    curses.init_pair(8, curses.COLOR_GREEN,   -1)   # Leaf litter (dim green)

    world  = World()
    paused = False

    while True:
        render(stdscr, world, paused)
        if not paused:
            world.update()
        time.sleep(TICK)

        key = stdscr.getch()

        if key == ord('q'):
            break

        elif key == ord('p'):
            paused = not paused

        elif key == ord('r'):
            world = World()

        elif key == ord('+'):
            # Drop a deadwood patch at a random open location
            x = random.randint(2, W - 3)
            y = random.randint(1, H - 2)
            i = y * W + x
            if world.sub[i] not in ('R',):
                world.sub[i]   = '#'
                world.nutr[i]  = min(1.0, world.nutr[i] + 0.5)
                world.moist[i] = min(0.8, world.moist[i] + 0.1)
                world.events.append(f"T{world.turn}: +Wood ({x},{y})")

        elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
            # Inject a spore burst of a chosen species
            s = key - ord('1')
            x = random.randint(5, W - 6)
            y = random.randint(2, H - 3)
            for _ in range(5):
                nx2 = max(0, min(W - 1, x + random.randint(-3, 3)))
                ny2 = max(0, min(H - 1, y + random.randint(-2, 2)))
                i   = ny2 * W + nx2
                if world.sub[i] != 'R':
                    world.bio[s][i] = max(world.bio[s][i], 1.2)
            world.events.append(
                f"T{world.turn}: {SPECIES[s]['name'][:5]} injected ({x},{y})")


curses.wrapper(main)
