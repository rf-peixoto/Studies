from __future__ import annotations
from typing import Dict, Tuple, List, Union
import math


Number = Union[int, float]


class Pseudo4DField:
    """
    Pseudo-4D array: a family of 3D volumes parameterized by w.

    - You store a finite set of 3D layers indexed by integer w: V_k[x][y][z].
    - For discrete access: A(x, y, z, w=k) returns V_k[x][y][z].
    - For continuous w: A(x, y, z, w) interpolates between neighboring layers.

    This models the idea:
      "4D = same 3D space viewed at different 'positions' along w",
    like a tesseract projection where w is a control parameter.
    """

    def __init__(self, shape_xyz: Tuple[int, int, int]):
        self.X, self.Y, self.Z = shape_xyz
        # layers[w_int] = 3D list [X][Y][Z]
        self.layers: Dict[int, List[List[List[Number]]]] = {}

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
        # initialize with zeros
        grid = [[[0.0 for _ in range(self.Z)]
                 for _ in range(self.Y)]
                for _ in range(self.X)]
        self.layers[w_int] = grid

    # ------------------------------------------------------------------
    # discrete interface: exact layers
    # ------------------------------------------------------------------

    def set_discrete(self, x: int, y: int, z: int, w_int: int, value: Number) -> None:
        """
        Set value at integer layer w_int (direct 4D cell, no interpolation).
        """
        self._check_bounds(x, y, z)
        self._ensure_layer(w_int)
        self.layers[w_int][x][y][z] = value

    def get_discrete(self, x: int, y: int, z: int, w_int: int) -> Number:
        """
        Get value at integer layer w_int. If layer is missing, returns 0.
        """
        self._check_bounds(x, y, z)
        if w_int not in self.layers:
            return 0.0
        return self.layers[w_int][x][y][z]

    # ------------------------------------------------------------------
    # continuous interface: pseudo-4D interpolation
    # ------------------------------------------------------------------

    def get(self, x: int, y: int, z: int, w: float) -> Number:
        """
        Get value at (x,y,z,w) with w as a continuous parameter.

        If w is an integer, returns that discrete layer directly.
        Otherwise, linearly interpolates between floor(w) and ceil(w).

        A(x,y,z,w) = (1-alpha) * V_floor + alpha * V_ceil
        where alpha = w - floor(w).
        """
        self._check_bounds(x, y, z)

        w_floor = math.floor(w)
        w_ceil = math.ceil(w)
        if w_floor == w_ceil:
            # exactly integer
            return self.get_discrete(x, y, z, w_floor)

        alpha = w - w_floor  # in (0,1)
        v0 = self.get_discrete(x, y, z, w_floor)
        v1 = self.get_discrete(x, y, z, w_ceil)
        return (1.0 - alpha) * v0 + alpha * v1

    # ------------------------------------------------------------------
    # optional helper: bulk set for an entire layer
    # ------------------------------------------------------------------

    def set_layer(self, w_int: int, data: List[List[List[Number]]]) -> None:
        """
        Replace entire layer at w_int with given 3D data.
        Expects shape [X][Y][Z].
        """
        if len(data) != self.X:
            raise ValueError("Layer X dimension mismatch")
        if any(len(row) != self.Y for row in data):
            raise ValueError("Layer Y dimension mismatch")
        if any(len(col) != self.Z for row in data for col in row):
            raise ValueError("Layer Z dimension mismatch")

        self.layers[w_int] = data

    # ------------------------------------------------------------------
    # convenience: inspect layers present
    # ------------------------------------------------------------------

    def available_layers(self) -> List[int]:
        return sorted(self.layers.keys())


# ----------------------------------------------------------------------
# Example usage
# ----------------------------------------------------------------------
if __name__ == "__main__":
    field = Pseudo4DField(shape_xyz=(4, 4, 4))

    # Define two layers: w=0 and w=1
    for x in range(4):
        for y in range(4):
            for z in range(4):
                # at w=0, store sum of coordinates
                field.set_discrete(x, y, z, w_int=0, value=x + y + z)
                # at w=1, store product of coordinates
                field.set_discrete(x, y, z, w_int=1, value=x * y * z)

    print("Available layers:", field.available_layers())

    x, y, z = 1, 2, 3
    for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
        val = field.get(x, y, z, w)
        print(f"A({x},{y},{z}, w={w:.2f}) = {val}")
