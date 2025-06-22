#!/usr/bin/env python3
import random
import argparse
import copy
from collections import deque

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
        cx = self.x + self.w // 2
        cy = self.y + self.h // 2
        return (cx, cy)

class MapGenerator:
    def __init__(self,
                 map_width=32,
                 map_height=32,
                 room_min_size=3,
                 room_max_size=7,
                 corridor_min_length=3,
                 corridor_max_length=15,
                 normal_room_count_min=5,
                 normal_room_count_max=10,
                 special_room_count=2,
                 special_room_chance=0.5,
                 seed=None):
        self.map_width = map_width
        self.map_height = map_height
        self.room_min_size = room_min_size
        self.room_max_size = room_max_size
        self.corridor_min_length = corridor_min_length
        self.corridor_max_length = corridor_max_length
        self.normal_room_count_min = normal_room_count_min
        self.normal_room_count_max = normal_room_count_max
        self.special_room_count = special_room_count
        self.special_room_chance = special_room_chance
        self.seed = seed if seed is not None else random.randrange(1 << 30)

    def _add_room(self, room):
        self.rooms.append(room)
        self.rooms_by_id[room.id] = room
        self.adj[room.id] = set()

    def _carve_room(self, room):
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                self.grid[y][x] = '.'

    def _carve_corridor(self, start, end):
        x1, y1 = start
        x2, y2 = end
        if random.choice([True, False]):
            # horizontal then vertical
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y1][x] = '.'
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x2] = '.'
        else:
            # vertical then horizontal
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x1] = '.'
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y2][x] = '.'

    def _place_normal_rooms(self):
        count = random.randint(self.normal_room_count_min, self.normal_room_count_max)
        attempts = 0
        while len([r for r in self.rooms if r.type == 'normal']) < count and attempts < count * 50:
            w = random.randint(self.room_min_size, self.room_max_size)
            h = random.randint(self.room_min_size, self.room_max_size)
            # enforce a 1-tile border: rooms cannot touch the outermost edge
            x = random.randint(1, self.map_width - w - 1)
            y = random.randint(1, self.map_height - h - 1)
            new_rect = Rect(x, y, w, h)
            if any(r.intersects(new_rect) for r in self.rooms):
                attempts += 1
                continue
            room = Room(self.next_room_id, x, y, w, h, 'normal')
            self.next_room_id += 1
            self._add_room(room)
            self._carve_room(room)
        if len([r for r in self.rooms if r.type == 'normal']) < self.normal_room_count_min:
            raise RuntimeError("Could not place the required number of normal rooms.")

    def _connect_normal_rooms(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        if not normals:
            return
        edges = []
        for i, r1 in enumerate(normals):
            for r2 in normals[i+1:]:
                dist = abs(r1.center[0] - r2.center[0]) + abs(r1.center[1] - r2.center[1])
                edges.append((dist, r1, r2))
        edges.sort(key=lambda e: e[0])

        visited = {normals[0].id}
        mst_edges = []
        for dist, r1, r2 in edges:
            if len(visited) == len(normals):
                break
            if ((r1.id in visited) ^ (r2.id in visited)) and self.corridor_min_length <= dist <= self.corridor_max_length:
                mst_edges.append((r1, r2))
                visited.add(r1.id if r2.id in visited else r2.id)

        if len(visited) < len(normals):
            visited = {normals[0].id}
            mst_edges = []
            for dist, r1, r2 in edges:
                if len(visited) == len(normals):
                    break
                if (r1.id in visited) ^ (r2.id in visited):
                    mst_edges.append((r1, r2))
                    visited.add(r1.id if r2.id in visited else r2.id)

        for r1, r2 in mst_edges:
            self._carve_corridor(r1.center, r2.center)
            self.adj[r1.id].add(r2.id)
            self.adj[r2.id].add(r1.id)

    def _add_loops(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        pairs = []
        for i, r1 in enumerate(normals):
            for r2 in normals[i+1:]:
                if r2.id in self.adj[r1.id]:
                    continue
                dist = abs(r1.center[0] - r2.center[0]) + abs(r1.center[1] - r2.center[1])
                if self.corridor_min_length <= dist <= self.corridor_max_length:
                    pairs.append((r1, r2))
        random.shuffle(pairs)
        loops = random.randint(0, len(normals)//2)
        for r1, r2 in pairs[:loops]:
            self._carve_corridor(r1.center, r2.center)
            self.adj[r1.id].add(r2.id)
            self.adj[r2.id].add(r1.id)

    def _bfs_path(self, start_id, end_id, adj):
        queue = deque([start_id])
        parent = {start_id: None}
        while queue:
            curr = queue.popleft()
            if curr == end_id:
                break
            for nbr in adj.get(curr, []):
                if nbr not in parent:
                    parent[nbr] = curr
                    queue.append(nbr)
        if end_id not in parent:
            return []
        path = []
        node = end_id
        while node is not None:
            path.append(node)
            node = parent[node]
        return list(reversed(path))

    def _count_normals_in_path(self, path):
        return sum(1 for rid in path
                   if rid in self.rooms_by_id and self.rooms_by_id[rid].type == 'normal')

    def _place_mandatory_rooms(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        required_normals = len(normals) // 2

        for _ in range(500):
            entrance = None
            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                edge = random.choice(['top','bottom','left','right'])
                if edge == 'top':
                    x = random.randint(1, self.map_width - w - 1)
                    y = 1
                elif edge == 'bottom':
                    x = random.randint(1, self.map_width - w - 1)
                    y = self.map_height - h - 1
                elif edge == 'left':
                    x = 1
                    y = random.randint(1, self.map_height - h - 1)
                else:
                    x = self.map_width - w - 1
                    y = random.randint(1, self.map_height - h - 1)
                rect = Rect(x, y, w, h)
                if any(r.intersects(rect) for r in self.rooms):
                    continue
                distances = [(abs((x+w//2) - r.center[0]) + abs((y+h//2) - r.center[1]), r)
                             for r in normals]
                distances.sort(key=lambda t: t[0])
                if not distances:
                    continue
                dist, target = distances[0]
                if not (self.corridor_min_length <= dist <= self.corridor_max_length):
                    continue
                entrance = (Room(self.next_room_id, x, y, w, h, 'entrance'), target.id)
                break
            if entrance is None:
                continue

            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                edge = random.choice(['top','bottom','left','right'])
                if edge == 'top':
                    x = random.randint(1, self.map_width - w - 1)
                    y = 1
                elif edge == 'bottom':
                    x = random.randint(1, self.map_width - w - 1)
                    y = self.map_height - h - 1
                elif edge == 'left':
                    x = 1
                    y = random.randint(1, self.map_height - h - 1)
                else:
                    x = self.map_width - w - 1
                    y = random.randint(1, self.map_height - h - 1)
                rect = Rect(x, y, w, h)
                if any(r.intersects(rect) for r in self.rooms) or rect.intersects(entrance[0]):
                    continue
                distances = [(abs((x+w//2) - r.center[0]) + abs((y+h//2) - r.center[1]), r)
                             for r in normals]
                distances.sort(key=lambda t: t[0])
                if not distances:
                    continue
                dist, target = distances[0]
                if not (self.corridor_min_length <= dist <= self.corridor_max_length):
                    continue
                objective = (Room(self.next_room_id+1, x, y, w, h, 'objective'), target.id)

                adj_copy = copy.deepcopy(self.adj)
                adj_copy[entrance[0].id] = {entrance[1]}
                adj_copy[entrance[1]].add(entrance[0].id)
                adj_copy[objective[0].id] = {objective[1]}
                adj_copy[objective[1]].add(objective[0].id)

                path = self._bfs_path(entrance[0].id, objective[0].id, adj_copy)
                if self._count_normals_in_path(path) >= required_normals:
                    for room, tgt in (entrance, objective):
                        self._add_room(room)
                        self._carve_room(room)
                        self._carve_corridor(room.center, self.rooms_by_id[tgt].center)
                        self.adj[room.id].add(tgt)
                        self.adj[tgt].add(room.id)
                        self.next_room_id += 1
                    return
        raise RuntimeError("Could not place mandatory rooms satisfying distance rule.")

    def _place_special_rooms(self):
        normals = [r for r in self.rooms if r.type == 'normal']
        for _ in range(self.special_room_count):
            if random.random() > self.special_room_chance:
                continue
            for _ in range(200):
                w = random.randint(self.room_min_size, self.room_max_size)
                h = random.randint(self.room_min_size, self.room_max_size)
                x = random.randint(1, self.map_width - w - 1)
                y = random.randint(1, self.map_height - h - 1)
                rect = Rect(x, y, w, h)
                if any(r.intersects(rect) for r in self.rooms):
                    continue
                distances = [(abs((x+w//2) - r.center[0]) + abs((y+h//2) - r.center[1]), r)
                             for r in normals]
                distances.sort(key=lambda t: t[0])
                if not distances:
                    continue
                dist, target = distances[0]
                if not (self.corridor_min_length <= dist <= self.corridor_max_length):
                    continue
                room = Room(self.next_room_id, x, y, w, h, 'special')
                self.next_room_id += 1
                self._add_room(room)
                self._carve_room(room)
                self._carve_corridor(room.center, target.center)
                self.adj[room.id].add(target.id)
                self.adj[target.id].add(room.id)
                break

    def generate(self):
        random.seed(self.seed)
        self.grid = [['#'] * self.map_width for _ in range(self.map_height)]
        self.rooms = []
        self.rooms_by_id = {}
        self.adj = {}
        self.next_room_id = 0

        self._place_normal_rooms()
        self._connect_normal_rooms()
        self._add_loops()
        self._place_mandatory_rooms()
        self._place_special_rooms()

        # mark entrance and objective rooms: '1' for entrance, '2' for objective
        for room in self.rooms:
            if room.type == 'entrance':
                mark = '1'
            elif room.type == 'objective':
                mark = '2'
            else:
                continue
            for y in range(room.y, room.y + room.h):
                for x in range(room.x, room.x + room.w):
                    self.grid[y][x] = mark

        return self.grid

def main():
    parser = argparse.ArgumentParser(description="Procedural dungeon map generator")
    parser.add_argument("--map-width", type=int, default=32)
    parser.add_argument("--map-height", type=int, default=32)
    parser.add_argument("--room-min-size", type=int, default=3)
    parser.add_argument("--room-max-size", type=int, default=7)
    parser.add_argument("--corridor-min-length", type=int, default=3)
    parser.add_argument("--corridor-max-length", type=int, default=15)
    parser.add_argument("--normal-room-count-min", type=int, default=5)
    parser.add_argument("--normal-room-count-max", type=int, default=10)
    parser.add_argument("--special-room-count", type=int, default=2)
    parser.add_argument("--special-room-chance", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    gen = MapGenerator(
        map_width=args.map_width,
        map_height=args.map_height,
        room_min_size=args.room_min_size,
        room_max_size=args.room_max_size,
        corridor_min_length=args.corridor_min_length,
        corridor_max_length=args.corridor_max_length,
        normal_room_count_min=args.normal_room_count_min,
        normal_room_count_max=args.normal_room_count_max,
        special_room_count=args.special_room_count,
        special_room_chance=args.special_room_chance,
        seed=args.seed,
    )
    grid = gen.generate()
    for row in grid:
        print("".join(row))
    print(f"Seed: {gen.seed}")

if __name__ == "__main__":
    main()
