from __name__ import annotations
from typing import Dict, Tuple, List, Union, Optional
import math
import random

import numpy as np
import matplotlib.pyplot as plt


Number = Union[int, float]


class Pseudo4DField:
    """
    Pseudo-4D array: 3D data with a 'w' parameter.

    - Storage: a finite set of 3D layers (volumes) indexed by integer w: V_k[x][y][z].
    - Discrete access:           get_discrete(x, y, z, w_int)
    - Continuous interpolation:  get_interpolated(x, y, z, w_float)
    - Geometric access:          get_geometric(x, y, z, w_float)

    Interpolation model:
        A(x,y,z,w) = (1 - alpha) * V_floor + alpha * V_ceil,
        where alpha = w - floor(w).

    Geometric model:
        A_geo(x,y,z,w) = V_base( R_w(x,y,z) ),
        where R_w rotates (x,y) around the center by an angle derived from w.
    """

    def __init__(self, shape_xyz: Tuple[int, int, int]):
        self.X, self.Y, self.Z = shape_xyz
        # layers[w_int] = 3D numpy array [X, Y, Z]
        self.layers: Dict[int, np.ndarray] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _check_bounds(self, x: int, y: int, z: int) -> None:
        if not (0 <= x < self.X and 0 <= y < self.Y and 0 <= z < self.Z):
            raise IndexError(
                f"Index (x,y,z)=({x},{y},{z}) out of bounds "
                f"for shape ({self.X},{self.Y},{self.Z})"
            )

    def _ensure_layer(self, w_int: int) -> None:
        if w_int in self.layers:
            return
        self.layers[w_int] = np.zeros((self.X, self.Y, self.Z), dtype=float)

    # ------------------------------------------------------------------
    # discrete interface
    # ------------------------------------------------------------------

    def set_discrete(self, x: int, y: int, z: int, w_int: int, value: Number) -> None:
        """
        Set value at integer layer w_int (direct 4D cell, no interpolation).
        """
        self._check_bounds(x, y, z)
        self._ensure_layer(w_int)
        self.layers[w_int][x, y, z] = value

    def get_discrete(self, x: int, y: int, z: int, w_int: int) -> Number:
        """
        Get value at integer layer w_int. If layer is missing, returns 0.
        """
        self._check_bounds(x, y, z)
        if w_int not in self.layers:
            return 0.0
        return self.layers[w_int][x, y, z]

    def set_layer(self, w_int: int, data: np.ndarray) -> None:
        """
        Replace entire layer at w_int with given 3D data (numpy array [X, Y, Z]).
        """
        if data.shape != (self.X, self.Y, self.Z):
            raise ValueError(
                f"Layer shape mismatch: got {data.shape}, "
                f"expected ({self.X}, {self.Y}, {self.Z})"
            )
        self.layers[w_int] = data.astype(float)

    def available_layers(self) -> List[int]:
        return sorted(self.layers.keys())

    # ------------------------------------------------------------------
    # interpolated access (pseudo-4D via blending)
    # ------------------------------------------------------------------

    def get_interpolated(self, x: int, y: int, z: int, w: float) -> Number:
        """
        Get value at (x,y,z,w) with w as a continuous parameter.

        If w is an integer, returns that discrete layer directly.
        Otherwise, linearly interpolates between floor(w) and ceil(w).

        Layers that do not exist are treated as zeros.
        """
        self._check_bounds(x, y, z)

        w_floor = math.floor(w)
        w_ceil = math.ceil(w)
        if w_floor == w_ceil:
            return self.get_discrete(x, y, z, w_floor)

        alpha = w - w_floor  # in (0,1)
        v0 = self.get_discrete(x, y, z, w_floor)
        v1 = self.get_discrete(x, y, z, w_ceil)
        return (1.0 - alpha) * v0 + alpha * v1

    # ------------------------------------------------------------------
    # geometric access (pseudo-4D via coordinate transform)
    # ------------------------------------------------------------------

    def get_geometric(
        self,
        x: int,
        y: int,
        z: int,
        w: float,
        base_layer: int = 0,
        center: Optional[Tuple[float, float]] = None,
    ) -> Number:
        """
        Get value using a geometric interpretation of w:

            - w ∈ [0,1] is mapped to an angle θ = 2π * w.
            - (x,y) is rotated around center by θ.
            - The base layer 'base_layer' is sampled at the rotated coordinates.

        This does NOT interpolate between layers; it treats 4th dimension as
        "how much we rotate the 3D data before looking at it".
        """
        if base_layer not in self.layers:
            return 0.0

        # Default rotation center: middle of the X,Y grid
        if center is None:
            cx = (self.X - 1) / 2.0
            cy = (self.Y - 1) / 2.0
        else:
            cx, cy = center

        self._check_bounds(x, y, z)

        # Map w to angle
        theta = 2.0 * math.pi * (w % 1.0)
        c = math.cos(theta)
        s = math.sin(theta)

        # Rotate around center in XY-plane
        dx = x - cx
        dy = y - cy
        xr = c * dx - s * dy + cx
        yr = s * dx + c * dy + cy

        # Nearest-neighbor sampling in base layer
        xi = int(round(xr))
        yi = int(round(yr))
        if not (0 <= xi < self.X and 0 <= yi < self.Y):
            return 0.0  # rotated point falls outside

        return float(self.layers[base_layer][xi, yi, z])

    # ------------------------------------------------------------------
    # "Hidden value" embedding
    # ------------------------------------------------------------------

    def hide_secret(
        self,
        x: int,
        y: int,
        z: int,
        w_target: float,
        secret: Number,
        w_floor: int,
        w_ceil: int,
    ) -> None:
        """
        Embed a secret so that:

            get_interpolated(x,y,z,w_target) == secret

        but at other w values the value looks like noise.

        We choose random v0 at layer w_floor and compute v1 at layer w_ceil
        such that the interpolation at w_target yields 'secret'.

        This is obviously reversible if you know the scheme, but it
        demonstrates how one value can depend sensitively on w.
        """
        self._check_bounds(x, y, z)

        if w_floor == w_ceil:
            raise ValueError("w_floor and w_ceil must be different")

        if not (w_floor <= w_target <= w_ceil):
            raise ValueError("w_target must be between w_floor and w_ceil")

        alpha = (w_target - w_floor) / (w_ceil - w_floor)

        # Make sure the layers exist
        self._ensure_layer(w_floor)
        self._ensure_layer(w_ceil)

        # Pick a random base value at floor layer
        v0 = random.uniform(-10.0, 10.0)

        # Solve for v1 in: (1-alpha)*v0 + alpha*v1 = secret
        v1 = (secret - (1.0 - alpha) * v0) / alpha

        self.layers[w_floor][x, y, z] = v0
        self.layers[w_ceil][x, y, z] = v1


# ----------------------------------------------------------------------
# Helper functions to generate demo volumes
# ----------------------------------------------------------------------

def make_sphere_volume(shape_xyz: Tuple[int, int, int], radius_ratio: float = 0.4) -> np.ndarray:
  """
  Create a 3D volume with a sphere of ones centered in the volume,
  zeros elsewhere. radius_ratio controls radius vs min dimension.
  """
  X, Y, Z = shape_xyz
  cx = (X - 1) / 2.0
  cy = (Y - 1) / 2.0
  cz = (Z - 1) / 2.0
  r = min(X, Y, Z) * radius_ratio

  vol = np.zeros((X, Y, Z), dtype=float)
  for x in range(X):
      for y in range(Y):
          for z in range(Z):
              dx = x - cx
              dy = y - cy
              dz = z - cz
              if dx*dx + dy*dy + dz*dz <= r*r:
                  vol[x, y, z] = 1.0
  return vol


def make_cube_volume(shape_xyz: Tuple[int, int, int], side_ratio: float = 0.6) -> np.ndarray:
  """
  Create a 3D volume with a centered cube of ones, zeros elsewhere.
  side_ratio controls cube side vs min dimension.
  """
  X, Y, Z = shape_xyz
  side = int(min(X, Y, Z) * side_ratio)
  side = max(1, side)
  x0 = (X - side) // 2
  y0 = (Y - side) // 2
  z0 = (Z - side) // 2

  vol = np.zeros((X, Y, Z), dtype=float)
  vol[x0:x0+side, y0:y0+side, z0:z0+side] = 1.0
  return vol


# ----------------------------------------------------------------------
# Demo / PoC
# ----------------------------------------------------------------------

def demo():
  # 1) Build pseudo-4D field with 2 layers: w=0 (sphere) and w=1 (cube)
  shape = (24, 24, 24)
  field = Pseudo4DField(shape)

  sphere = make_sphere_volume(shape, radius_ratio=0.35)
  cube = make_cube_volume(shape, side_ratio=0.5)
  field.set_layer(0, sphere)
  field.set_layer(1, cube)

  print("Available layers:", field.available_layers())

  # 2) Visualize interpolation for a mid-Z slice
  z_mid = shape[2] // 2
  w_values = [0.0, 0.25, 0.5, 0.75, 1.0]

  fig, axes = plt.subplots(1, len(w_values), figsize=(3 * len(w_values), 3))
  fig.suptitle("Interpolated pseudo-4D slice at z = %d" % z_mid)

  for ax, w in zip(axes, w_values):
      slice_2d = np.zeros((shape[0], shape[1]), dtype=float)
      for x in range(shape[0]):
          for y in range(shape[1]):
              slice_2d[x, y] = field.get_interpolated(x, y, z_mid, w)

      im = ax.imshow(slice_2d.T, origin="lower", cmap="magma", vmin=0, vmax=1)
      ax.set_title(f"w = {w:.2f}")
      ax.set_xticks([])
      ax.set_yticks([])

  fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.6)
  plt.tight_layout()
  plt.show()

  # 3) Demonstrate geometric pseudo-4D: rotate base layer 0
  fig2, axes2 = plt.subplots(1, len(w_values), figsize=(3 * len(w_values), 3))
  fig2.suptitle("Geometric pseudo-4D slice (rotation of base layer 0)")

  for ax, w in zip(axes2, w_values):
      slice_2d = np.zeros((shape[0], shape[1]), dtype=float)
      for x in range(shape[0]):
          for y in range(shape[1]):
              slice_2d[x, y] = field.get_geometric(x, y, z_mid, w, base_layer=0)

      im = ax.imshow(slice_2d.T, origin="lower", cmap="magma", vmin=0, vmax=1)
      ax.set_title(f"w = {w:.2f}")
      ax.set_xticks([])
      ax.set_yticks([])

  fig2.colorbar(im, ax=axes2.ravel().tolist(), shrink=0.6)
  plt.tight_layout()
  plt.show()

  # 4) Hide a secret value at a specific (x,y,z,w)
  secret_value = 1337.0
  x_s, y_s, z_s = 5, 10, 7
  w_target = 0.618  # only this w should yield the clean secret
  w_floor = 0
  w_ceil = 1

  field.hide_secret(x_s, y_s, z_s, w_target, secret_value, w_floor, w_ceil)

  print("\n--- Secret embedding demo ---")
  print(f"Secret embedded at (x,y,z) = ({x_s},{y_s},{z_s}), w* = {w_target:.3f}")

  test_ws = [0.0, 0.25, w_target, 0.75, 1.0]
  for w in test_ws:
      val = field.get_interpolated(x_s, y_s, z_s, w)
      print(f"A({x_s},{y_s},{z_s}, w={w:.3f}) = {val:.4f}")

  print("\nObserve: only at w ≈ %.3f the value ~= %.1f; other w values look unrelated." %
        (w_target, secret_value))


if __name__ == "__main__":
  demo()
