#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hashart.py — Pure-stdlib deterministic hash → visual artifact generator.

Features:
- 3D voxel identicon (OBJ+MTL)
- 2D PNG identicon (front-orthographic)
- Parametric glyph (OBJ)
- No external libraries, Python 3.x
- Filenames are <hash>.<ext>; OBJ includes "# hash: <hex>" in header
"""

import argparse
import binascii
import itertools
import math
import os
import struct
import sys
import zlib
from typing import List, Tuple, Optional

# ---------------------------
# Utilities: colors & PRNG
# ---------------------------

def _clean_hex_color(s: Optional[str], fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if not s:
        return fallback
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(ch*2 for ch in s)
    if len(s) != 6:
        return fallback
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        return fallback

def _hash_bytes_from_hex(hexstr: str) -> bytes:
    try:
        return bytes.fromhex(hexstr.strip())
    except Exception:
        raise ValueError("Input is not valid hex.")

def _u64_from_bytes(b: bytes) -> int:
    # fold arbitrary length into 64 bits via xor-chunks
    acc = 0
    for i in range(0, len(b), 8):
        chunk = b[i:i+8]
        v = int.from_bytes(chunk.ljust(8, b'\0'), 'big', signed=False)
        acc ^= v
    return acc & ((1<<64)-1)

class SplitMix64:
    """Deterministic 64-bit PRNG (platform-stable)."""
    def __init__(self, seed: int):
        self.state = seed & ((1<<64)-1)

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & ((1<<64)-1)
        z = self.state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & ((1<<64)-1)
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & ((1<<64)-1)
        return z ^ (z >> 31)

    def randrange(self, n: int) -> int:
        # unbiased modulo
        if n <= 0:
            return 0
        # rejection sampling
        limit = ((1<<64) // n) * n
        while True:
            x = self.next_u64()
            if x < limit:
                return x % n

    def random(self) -> float:
        return (self.next_u64() >> 11) * (1.0 / (1<<53))

# ---------------------------
# Bitstream from hash
# ---------------------------

class BitStream:
    def __init__(self, data: bytes):
        self.bits = []
        for byte in data:
            for i in range(8):
                self.bits.append((byte >> (7 - i)) & 1)
        self.idx = 0

    def get_bit(self) -> int:
        b = self.bits[self.idx % len(self.bits)]
        self.idx += 1
        return b

    def get_bits(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.get_bit()
        return v

# ---------------------------
# 3D Identicon generator
# ---------------------------

def build_identicon_3d(hexhash: str, grid: int = 5, extrude_max: int = 5) -> Tuple[List[Tuple[int,int,int]], int]:
    """
    Returns:
      voxels: list of (x, y, z) cube coordinates
      grid:   grid size used (odd)
    Symmetry: mirror horizontally (X) to make classic identicon; Y has no mirroring by default,
    but pattern feels symmetric due to consistent rule across rows; Z is extrusion height.
    """
    if grid % 2 == 0 or grid < 3:
        raise ValueError("grid must be odd and >= 3 (e.g., 5, 7).")

    b = _hash_bytes_from_hex(hexhash)
    bs = BitStream(b)

    cols_left = (grid + 1) // 2  # left (including middle)
    # Occupancy for left half (cols_left x grid)
    left = [[bs.get_bit() for _ in range(grid)] for _ in range(cols_left)]

    # Mirror to full grid horizontally
    occ = [[0]*grid for _ in range(grid)]
    for x in range(cols_left):
        for y in range(grid):
            bit = left[x][y]
            occ[x][y] = bit
            mirror_x = grid - 1 - x
            occ[mirror_x][y] = bit

    # Heights per cell: 1..extrude_max (0 if empty)
    voxels = []
    for x in range(grid):
        for y in range(grid):
            if occ[x][y]:
                # draw height biased away from 0 to avoid flatness
                # height determined from next bits; use 1..extrude_max
                if extrude_max <= 1:
                    h = 1
                else:
                    # Take log-ish distribution for variety; still deterministic:
                    # combine bits for value, then map to 1..extrude_max
                    raw = bs.get_bits(6)  # 0..63
                    h = 1 + (raw % extrude_max)
                for z in range(h):
                    voxels.append((x, y, z))

    return voxels, grid

# ---------------------------
# OBJ/MTL export
# ---------------------------

def _write_obj_mtl(outbase: str,
                   voxels: List[Tuple[int,int,int]],
                   grid: int,
                   hexhash: str,
                   primary_rgb: Tuple[int,int,int],
                   accent_rgb: Optional[Tuple[int,int,int]] = None,
                   voxel_size: float = 1.0) -> None:
    """
    Writes:
      <outbase>.obj and <outbase>.mtl
    Geometry: each voxel is a cube; normalized to [0, grid] in x/y and [0, H] in z, then
    later you can uniformly scale in your viewer. We keep units simple and deterministic.
    """
    # Prepare materials
    mtl_name = os.path.basename(outbase) + ".mtl"
    obj_name = outbase + ".obj"
    mtl_path = outbase + ".mtl"

    # Colors normalized 0..1
    def rgbf(c): return (c[0]/255.0, c[1]/255.0, c[2]/255.0)

    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write(f"# hash: {hexhash}\n")
        f.write("newmtl primary\n")
        r,g,b = rgbf(primary_rgb)
        f.write(f"Kd {r:.6f} {g:.6f} {b:.6f}\n")
        f.write("Ka 0.000000 0.000000 0.000000\n")
        f.write("Ks 0.000000 0.000000 0.000000\n")
        if accent_rgb:
            f.write("\nnewmtl accent\n")
            r,g,b = rgbf(accent_rgb)
            f.write(f"Kd {r:.6f} {g:.6f} {b:.6f}\n")
            f.write("Ka 0.000000 0.000000 0.000000\n")
            f.write("Ks 0.000000 0.000000 0.000000\n")

    # Simple rule: alternate materials to add subtle variety if accent exists
    use_accent = bool(accent_rgb)

    # Emit one cube per voxel
    with open(obj_name, "w", encoding="utf-8") as f:
        f.write(f"# hash: {hexhash}\n")
        f.write(f"mtllib {os.path.basename(mtl_name)}\n")

        vidx = 1
        faces = []
        # cube vertex offsets
        o = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
        # cube faces (1-based indices, per local cube)
        cube_faces = [
            (1,2,3,4),  # bottom z
            (5,6,7,8),  # top z
            (1,5,8,4),  # -x
            (2,6,7,3),  # +x
            (1,2,6,5),  # -y
            (4,3,7,8),  # +y
        ]

        for i, (x,y,z) in enumerate(voxels):
            # choose material
            if use_accent and ( (x + y + z) & 1 ):
                f.write("usemtl accent\n")
            else:
                f.write("usemtl primary\n")

            # vertices
            for dx,dy,dz in o:
                vx = (x + dx) * voxel_size
                vy = (y + dy) * voxel_size
                vz = (z + dz) * voxel_size
                f.write(f"v {vx:.6f} {vy:.6f} {vz:.6f}\n")

            # faces (relative to this cube's 8 vertices)
            for a,b_,c,d in cube_faces:
                f.write(f"f {vidx+a} {vidx+b_} {vidx+c} {vidx+d}\n")

            vidx += 8

# ---------------------------
# PNG writer (no deps)
# ---------------------------

def _write_png(outpath: str, pixels: List[List[Tuple[int,int,int,int]]]) -> None:
    """
    pixels: H rows of W tuples (R,G,B,A)
    Writes a valid PNG using zlib (no external libs).
    """
    height = len(pixels)
    width = len(pixels[0]) if height else 0

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", binascii.crc32(tag + data) & 0xffffffff)

    # IHDR
    ihdr = struct.pack(">IIBBBBB",
                       width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    # IDAT
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0
        for (r,g,b,a) in row:
            raw.extend([r & 0xff, g & 0xff, b & 0xff, a & 0xff])
    comp = zlib.compress(bytes(raw), 9)

    png = b"\x89PNG\r\n\x1a\n" + \
          chunk(b"IHDR", ihdr) + \
          chunk(b"IDAT", comp) + \
          chunk(b"IEND", b"")

    with open(outpath, "wb") as f:
        f.write(png)

def render_identicon_png(hexhash: str,
                         size_px: int = 1024,
                         grid: int = 5,
                         primary_rgb: Tuple[int,int,int] = (58,123,213),
                         bg_rgb: Tuple[int,int,int] = (10,10,10),
                         accent_rgb: Optional[Tuple[int,int,int]] = None) -> List[List[Tuple[int,int,int,int]]]:
    """
    2D front-orthographic identicon (classic symmetry), no 3D shading.
    """
    b = _hash_bytes_from_hex(hexhash)
    bs = BitStream(b)
    cols_left = (grid + 1)//2
    left = [[bs.get_bit() for _ in range(grid)] for _ in range(cols_left)]
    occ = [[0]*grid for _ in range(grid)]
    for x in range(cols_left):
        for y in range(grid):
            bit = left[x][y]
            occ[x][y] = bit
            occ[grid-1-x][y] = bit

    # Optional: small accent cross if enough 1s; deterministic toggle
    use_accent = bool(accent_rgb) and (sum(sum(r) for r in occ) % 3 == 1)

    # Raster at cell-level then upscale to pixels
    cell_px = max(1, size_px // grid)
    w = h = cell_px * grid
    pixels = [[(bg_rgb[0], bg_rgb[1], bg_rgb[2], 255) for _ in range(w)] for _ in range(h)]

    for y in range(grid):
        for x in range(grid):
            if occ[x][y]:
                for yy in range(y*cell_px, (y+1)*cell_px):
                    row = pixels[yy]
                    for xx in range(x*cell_px, (x+1)*cell_px):
                        row[xx] = (primary_rgb[0], primary_rgb[1], primary_rgb[2], 255)

    if use_accent:
        mid = grid//2
        for y in range(grid):
            for yy in range(y*cell_px, (y+1)*cell_px):
                row = pixels[yy]
                for xx in range(mid*cell_px, (mid+1)*cell_px):
                    row[xx] = (accent_rgb[0], accent_rgb[1], accent_rgb[2], 255)
        for x in range(grid):
            for yy in range(mid*cell_px, (mid+1)*cell_px):
                row = pixels[yy]
                for xx in range(x*cell_px, (x+1)*cell_px):
                    row[xx] = (accent_rgb[0], accent_rgb[1], accent_rgb[2], 255)

    # If requested size doesn't divide evenly, we can pad/crop later; for now we clip to exact w=h.
    return pixels

# ---------------------------
# Parametric glyph (OBJ)
# ---------------------------

def build_parametric_glyph(hexhash: str,
                           lat_steps: int = 64,
                           lon_steps: int = 128) -> Tuple[List[Tuple[float,float,float]], List[Tuple[int,int,int]]]:
    """
    Hash-driven harmonic sphere: r = 1 + Σ a_k sin(kθ + φ_k) sin(kφ + ψ_k)
    Returns vertices and triangular faces. Deterministic, watertight.
    """
    seed = _u64_from_bytes(_hash_bytes_from_hex(hexhash))
    rng = SplitMix64(seed)

    harmonics = 6  # reasonable richness
    amps = [0.05 + 0.15 * (rng.random()) for _ in range(harmonics)]
    phase_t = [2*math.pi*rng.random() for _ in range(harmonics)]
    phase_p = [2*math.pi*rng.random() for _ in range(harmonics)]

    verts: List[Tuple[float,float,float]] = []
    faces: List[Tuple[int,int,int]] = []

    for i in range(lat_steps+1):
        theta = math.pi * i / lat_steps  # 0..π
        for j in range(lon_steps):
            phi = 2*math.pi * j / lon_steps  # 0..2π
            r = 1.0
            for k in range(1, harmonics+1):
                r += amps[k-1] * math.sin(k*theta + phase_t[k-1]) * math.sin(k*phi + phase_p[k-1])
            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)
            verts.append((x,y,z))

    # faces
    def vid(i,j): return i*lon_steps + (j % lon_steps)
    for i in range(lat_steps):
        for j in range(lon_steps):
            v1 = vid(i, j) + 1
            v2 = vid(i+1, j) + 1
            v3 = vid(i+1, j+1) + 1
            v4 = vid(i, j+1) + 1
            faces.append((v1,v2,v3))
            faces.append((v1,v3,v4))

    return verts, faces

def write_obj_from_mesh(outbase: str,
                        hexhash: str,
                        verts: List[Tuple[float,float,float]],
                        faces: List[Tuple[int,int,int]],
                        rgb: Tuple[int,int,int]) -> None:
    mtl_path = outbase + ".mtl"
    obj_path = outbase + ".obj"
    with open(mtl_path, "w", encoding="utf-8") as m:
        m.write(f"# hash: {hexhash}\n")
        m.write("newmtl primary\n")
        r,g,b = rgb
        m.write(f"Kd {r/255.0:.6f} {g/255.0:.6f} {b/255.0:.6f}\n")
        m.write("Ka 0 0 0\nKs 0 0 0\n")
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(f"# hash: {hexhash}\n")
        f.write("mtllib " + os.path.basename(mtl_path) + "\n")
        f.write("usemtl primary\n")
        for (x,y,z) in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for (a,b,c) in faces:
            f.write(f"f {a} {b} {c}\n")

# ---------------------------
# CLI
# ---------------------------

def process_one(hexhash: str,
                fmt: str,
                style: str,
                size: int,
                grid: int,
                extrude_max: int,
                primary_color: Optional[str],
                accent_color: Optional[str],
                bg_color: Optional[str]) -> None:

    # validate hex (any length OK as long as it parses)
    _ = _hash_bytes_from_hex(hexhash)

    # default colors from hash if not provided (stable)
    hb = _hash_bytes_from_hex(hexhash)
    seed = _u64_from_bytes(hb)
    rng = SplitMix64(seed)
    def rndc():
        # pleasant-ish: avoid extremes
        return (48 + int(rng.random()*160),
                48 + int(rng.random()*160),
                48 + int(rng.random()*160))
    primary_rgb = _clean_hex_color(primary_color, rndc())
    accent_rgb  = _clean_hex_color(accent_color, None) if accent_color else None
    bg_rgb      = _clean_hex_color(bg_color, (12,12,12))

    if fmt == "obj":
        outbase = hexhash
        if style == "ident3d":
            voxels, g = build_identicon_3d(hexhash, grid=grid, extrude_max=extrude_max)
            _write_obj_mtl(outbase, voxels, g, hexhash, primary_rgb, accent_rgb)
            print(f"Wrote {outbase}.obj and {outbase}.mtl  (voxels: {len(voxels)})")
        elif style == "glyph":
            verts, faces = build_parametric_glyph(hexhash)
            write_obj_from_mesh(outbase, hexhash, verts, faces, primary_rgb)
            print(f"Wrote {outbase}.obj and {outbase}.mtl  (verts: {len(verts)}, faces: {len(faces)})")
        else:
            raise SystemExit("Unknown style for OBJ. Use 'ident3d' or 'glyph'.")
    elif fmt == "png":
        # For PNG we render 2D identicon (fast preview)
        pixels = render_identicon_png(hexhash, size_px=size, grid=grid,
                                      primary_rgb=primary_rgb,
                                      bg_rgb=bg_rgb,
                                      accent_rgb=accent_rgb)
        # ensure final image is exactly size x size:
        h = len(pixels)
        w = len(pixels[0]) if h else 0
        # Crop or pad to requested size
        target = size
        # crop
        pixels = [row[:min(w,target)] for row in pixels[:min(h,target)]]
        # pad
        while len(pixels) < target:
            pixels.append([(bg_rgb[0],bg_rgb[1],bg_rgb[2],255) for _ in range(min(w,target))])
        while any(len(row) < target for row in pixels):
            for row in pixels:
                while len(row) < target:
                    row.append((bg_rgb[0],bg_rgb[1],bg_rgb[2],255))

        outpng = f"{hexhash}.png"
        _write_png(outpng, pixels)
        print(f"Wrote {outpng}  ({target}x{target})")
    else:
        raise SystemExit("Unknown format. Use 'obj' or 'png'.")

def main():
    ap = argparse.ArgumentParser(description="Deterministic hash → identicon 3D OBJ/PNG (no deps).")
    ap.add_argument("--hash", dest="hashes", action="append", help="Hex-encoded hash (may be repeated).")
    ap.add_argument("--input-file", help="File with one hex-encoded hash per line.")
    ap.add_argument("--format", choices=["obj","png"], required=True, help="Output format.")
    ap.add_argument("--style", choices=["ident3d","glyph"], default="ident3d",
                    help="Style: 3D voxel identicon (default) or parametric glyph (OBJ only).")
    ap.add_argument("--size", type=int, default=1024, help="PNG size (square). Default 1024.")
    ap.add_argument("--grid", type=int, default=5, help="Identicon grid size (odd >=3). Default 5.")
    ap.add_argument("--extrude-max", type=int, default=5, help="Max voxel height per active cell. Default 5.")
    ap.add_argument("--primary-color", type=str, default=None, help="Hex like #RRGGBB.")
    ap.add_argument("--accent-color", type=str, default=None, help="Optional accent color #RRGGBB.")
    ap.add_argument("--bg-color", type=str, default=None, help="Background color for PNG #RRGGBB.")
    args = ap.parse_args()

    hashes: List[str] = []
    if args.hashes:
        hashes.extend(args.hashes)
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                # ignore comments
                if s.startswith("#"):
                    continue
                hashes.append(s)

    if not hashes:
        print("Provide --hash <hex> (can repeat) and/or --input-file.", file=sys.stderr)
        sys.exit(1)

    for h in hashes:
        try:
            process_one(h, args.format, args.style, args.size, args.grid, args.extrude_max,
                        args.primary_color, args.accent_color, args.bg_color)
        except Exception as e:
            print(f"[{h}] ERROR: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
