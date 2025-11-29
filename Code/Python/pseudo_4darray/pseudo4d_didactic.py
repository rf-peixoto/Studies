import math
import random
from typing import Dict, Tuple, List

import numpy as np
import matplotlib.pyplot as plt


Number = float


# ================================================================
# 1. Pseudo-4D field
# ================================================================
class Pseudo4DField:
    """
    Pseudo-4D array: 3D volumes indexed by an extra parameter w.

    Storage:
      - We store a finite set of 3D layers at integer w indices: V_k[x,y,z].

    Access modes:
      1) Discrete:     get_discrete(x,y,z,w_int)
      2) Interpolated: get_interpolated(x,y,z,w_float)

    Interpolated mode models "4D" as:
        A(x,y,z,w) = (1-alpha) * V_floor(x,y,z) + alpha * V_ceil(x,y,z)
        where alpha = w - floor(w).

    So the 4th dimension is NOT a fully stored axis; it is a parameter that
    blends between 3D volumes.
    """

    def __init__(self, shape_xyz: Tuple[int, int, int]):
        self.X, self.Y, self.Z = shape_xyz
        # layers[w] = 3D numpy array of shape (X,Y,Z)
        self.layers: Dict[int, np.ndarray] = {}

    # ------------------ internal helpers -------------------------

    def _check_bounds(self, x: int, y: int, z: int) -> None:
        if not (0 <= x < self.X and 0 <= y < self.Y and 0 <= z < self.Z):
            raise IndexError(
                f"(x,y,z)=({x},{y},{z}) out of bounds for shape ({self.X},{self.Y},{self.Z})"
            )

    def _ensure_layer(self, w_int: int) -> None:
        if w_int not in self.layers:
            self.layers[w_int] = np.zeros((self.X, self.Y, self.Z), dtype=float)

    # ------------------ discrete API -----------------------------

    def set_layer(self, w_int: int, data: np.ndarray) -> None:
        """
        Set the entire layer at integer w = w_int.
        """
        if data.shape != (self.X, self.Y, self.Z):
            raise ValueError(
                f"Layer shape mismatch: got {data.shape}, expected ({self.X},{self.Y},{self.Z})"
            )
        self.layers[w_int] = data.astype(float)

    def get_discrete(self, x: int, y: int, z: int, w_int: int) -> Number:
        """
        Read from an exact integer w index. Missing layers are treated as zeros.
        """
        self._check_bounds(x, y, z)
        if w_int not in self.layers:
            return 0.0
        return float(self.layers[w_int][x, y, z])

    def available_layers(self) -> List[int]:
        return sorted(self.layers.keys())

    # ------------------ interpolated API -------------------------

    def get_interpolated(self, x: int, y: int, z: int, w: float) -> Number:
        """
        Read from a continuous w:

          If w is an integer, this is just an exact layer lookup.
          Otherwise, linearly interpolates between floor(w) and ceil(w).
        """
        self._check_bounds(x, y, z)

        w_floor = math.floor(w)
        w_ceil = math.ceil(w)
        if w_floor == w_ceil:
            return self.get_discrete(x, y, z, w_floor)

        alpha = w - w_floor  # 0 < alpha < 1
        v0 = self.get_discrete(x, y, z, w_floor)
        v1 = self.get_discrete(x, y, z, w_ceil)
        return (1.0 - alpha) * v0 + alpha * v1

    # ------------------ secret embedding -------------------------

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
        Hide a secret such that:

            get_interpolated(x,y,z,w_target) == secret

        Idea:
          - Choose a random value v0 for layer w_floor.
          - Solve for v1 in layer w_ceil so that the interpolation at w_target
            yields exactly 'secret'.

        Anyone who does not know the correct w_target will see apparently
        meaningless numbers at other w.
        """
        self._check_bounds(x, y, z)

        if w_floor == w_ceil:
            raise ValueError("w_floor and w_ceil must be different")

        if not (w_floor <= w_target <= w_ceil):
            raise ValueError("w_target must be between w_floor and w_ceil")

        # ensure layers exist
        self._ensure_layer(w_floor)
        self._ensure_layer(w_ceil)

        # interpolation coefficient between these two layers
        alpha = (w_target - w_floor) / (w_ceil - w_floor)

        # random base value at w_floor
        v0 = random.uniform(-50.0, 50.0)

        # solve for v1 in: (1-alpha)*v0 + alpha*v1 = secret
        v1 = (secret - (1.0 - alpha) * v0) / alpha

        self.layers[w_floor][x, y, z] = v0
        self.layers[w_ceil][x, y, z] = v1


# ================================================================
# 2. Helper functions to build simple 3D shapes
# ================================================================

def make_sphere(shape_xyz: Tuple[int, int, int], radius_ratio: float = 0.35) -> np.ndarray:
    """
    Sphere of ones in the middle, zeros elsewhere.
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


def make_cube(shape_xyz: Tuple[int, int, int], side_ratio: float = 0.5) -> np.ndarray:
    """
    Centered cube of ones, zeros elsewhere.
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


def make_diagonal_noise(shape_xyz: Tuple[int, int, int]) -> np.ndarray:
    """
    A simple 'diagonal' structure plus noise, to break symmetry.
    """
    X, Y, Z = shape_xyz
    vol = np.random.rand(X, Y, Z) * 0.15  # base noise

    length = min(X, Y, Z)
    for i in range(length):
        x = i
        y = i
        z = i
        vol[x, y, z] += 0.8  # bright diagonal
    vol = np.clip(vol, 0.0, 1.0)
    return vol


# ================================================================
# 3. Demo: build field, hide secret, visualize
# ================================================================

def demo():
    # ------------------------------------------------------------------
    # 3.1. Create pseudo-4D field and three key layers (integer w)
    # ------------------------------------------------------------------
    shape = (24, 24, 24)
    field = Pseudo4DField(shape)

    # Three "keyframes" in w:
    #   w=0: sphere
    #   w=1: cube
    #   w=2: diagonal noisy structure
    sphere = make_sphere(shape, radius_ratio=0.33)
    cube   = make_cube(shape, side_ratio=0.55)
    diag   = make_diagonal_noise(shape)

    field.set_layer(0, sphere)
    field.set_layer(1, cube)
    field.set_layer(2, diag)

    print("Available discrete layers (integer w):", field.available_layers())

    # ------------------------------------------------------------------
    # 3.2. Hide a secret at a particular (x,y,z,w*)
    # ------------------------------------------------------------------
    secret_value = 1337.0
    # Choose some arbitrary coordinate in the volume
    x_s, y_s, z_s = 5, 12, 7

    # We hide the secret between w=0 and w=1 at a non-integer w*
    w_floor = 0
    w_ceil  = 1
    w_star  = 0.61  # only this w will yield ~secret_value at (x_s, y_s, z_s)

    field.hide_secret(
        x=x_s,
        y=y_s,
        z=z_s,
        w_target=w_star,
        secret=secret_value,
        w_floor=w_floor,
        w_ceil=w_ceil,
    )

    print(f"\nSecret hidden at (x,y,z) = ({x_s},{y_s},{z_s}), between layers w={w_floor} and w={w_ceil}")
    print(f"Correct w* = {w_star:.3f}, secret = {secret_value}")

    # ------------------------------------------------------------------
    # 3.3. Show how the secret looks when you sample at different w
    # ------------------------------------------------------------------
    print("\nSampling interpolated value at the secret coordinates for several w:")
    test_ws = [0.0, 0.3, w_star, 0.9, 1.0, 1.5, 2.0]
    for w in test_ws:
        val = field.get_interpolated(x_s, y_s, z_s, w)
        print(f"  A({x_s},{y_s},{z_s}, w={w:4.2f}) = {val:8.3f}")

    # We'll also make a dense plot of value(w) in [0,2] at that same coordinate
    w_dense = np.linspace(0, 2, 400)
    values_dense = np.array([field.get_interpolated(x_s, y_s, z_s, w) for w in w_dense])

    # ------------------------------------------------------------------
    # 3.4. Visualize 2D slices for multiple w
    # ------------------------------------------------------------------
    # We'll look at the central z-slice and see how it changes with w.
    z_slice = shape[2] // 2
    w_samples = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]

    fig, axes = plt.subplots(1, len(w_samples), figsize=(3 * len(w_samples), 3))
    fig.suptitle(f"Pseudo-4D: interpolated slices at z={z_slice}")

    for ax, w in zip(axes, w_samples):
        slice_2d = np.zeros((shape[0], shape[1]), dtype=float)
        for x in range(shape[0]):
            for y in range(shape[1]):
                slice_2d[x, y] = field.get_interpolated(x, y, z_slice, w)

        im = ax.imshow(slice_2d.T, origin="lower", cmap="magma", vmin=0.0, vmax=1.0)
        ax.set_title(f"w = {w:.2f}")
        ax.set_xticks([])
        ax.set_yticks([])

        # Mark the (x_s, y_s) where the secret coordinate is (same z)
        if z_slice == z_s:
            ax.scatter([x_s], [y_s], s=20, c="cyan", marker="o", edgecolors="black")

    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.6)
    plt.tight_layout()
    plt.show()

    # ------------------------------------------------------------------
    # 3.5. Plot how the hidden value changes with w
    # ------------------------------------------------------------------
    fig2, ax2 = plt.subplots(figsize=(7, 4))
    ax2.plot(w_dense, values_dense, label="A(x_s, y_s, z_s, w)")
    ax2.axvline(w_star, color="lime", linestyle="--", label=f"w* = {w_star:.3f}")
    ax2.axhline(secret_value, color="red", linestyle=":", label=f"secret = {secret_value}")
    ax2.scatter([w_star], [secret_value], color="red", zorder=5)

    ax2.set_xlabel("w (continuous 'dimension')")
    ax2.set_ylabel("Value at (x_s, y_s, z_s)")
    ax2.set_title("Hidden value as a function of w")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    demo()
