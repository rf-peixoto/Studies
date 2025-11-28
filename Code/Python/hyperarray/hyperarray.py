import os
import enum
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any, Dict, Tuple, Optional, Iterable


class DimensionRole(enum.Enum):
    REAL = "real"
    DECOY = "decoy"
    TRAP = "trap"


class TrapAccessError(RuntimeError):
    """Raised when accessing a TRAP dimension (optional behaviour)."""
    pass


@dataclass(frozen=True)
class DimensionConfig:
    name: str
    role: DimensionRole


class HyperArray:
    """
    HyperArray: keyed, dimension-aware, sparse hypercube with obfuscating layout.

    - Logical indices: (x, y, z)  -> user-visible
    - Hidden dimension: D         -> internal state (selected via set_dimension)
    - Physical storage: dict[addr] where addr = PRF_K(D, x, y, z)

    This PoC demonstrates:
      * Hidden dimension state.
      * Keyed, pseudorandom physical layout (using BLAKE2b as PRF-like).
      * Distinct dimension roles (REAL / DECOY / TRAP).
      * Sparse hypercube semantics (only touched cells exist).
      * Introspection helpers for analysis and reverse-engineering experimentation.
    """

    def __init__(
        self,
        dims: Tuple[int, int, int],
        dimensions: Iterable[DimensionConfig],
        key: Optional[bytes] = None,
        enable_trap_exception: bool = True,
        access_log: bool = True,
    ) -> None:
        """
        :param dims: logical shape (X, Y, Z)
        :param dimensions: iterable of DimensionConfig (at least one must be REAL)
        :param key: optional 32-byte secret; if None, a random key is generated
        :param enable_trap_exception: if True, accessing a TRAP dimension raises TrapAccessError
        :param access_log: if True, record all accesses for later inspection
        """
        self._dims = dims
        self._X, self._Y, self._Z = dims

        dims_list = list(dimensions)
        if not dims_list:
            raise ValueError("At least one dimension must be defined")

        if not any(d.role == DimensionRole.REAL for d in dims_list):
            raise ValueError("At least one dimension must have role=REAL")

        self._dim_configs: Dict[str, DimensionConfig] = {d.name: d for d in dims_list}
        self._dim_ids: Dict[str, int] = {name: idx for idx, name in enumerate(self._dim_configs)}
        self._id_to_name: Dict[int, str] = {idx: name for name, idx in self._dim_ids.items()}

        self._current_dim_id: int = 0  # default to first defined dimension
        self._key: bytes = key if key is not None else os.urandom(32)
        self._enable_trap_exception = enable_trap_exception
        self._access_log_enabled = access_log

        # Physical storage: addr -> value
        self._storage: Dict[int, Any] = {}

        # Optional log of accesses for experiments / RE
        # Each entry: (op, dim_name, x, y, z, addr)
        self._access_log = []  # type: ignore[var-annotated]

    # ----------------------------------------------------------------------
    # Public API: dimension management
    # ----------------------------------------------------------------------

    @property
    def shape(self) -> Tuple[int, int, int]:
        """Return logical shape as (X, Y, Z)."""
        return self._dims

    @property
    def current_dimension(self) -> str:
        """Return the name of the current active dimension."""
        return self._id_to_name[self._current_dim_id]

    def list_dimensions(self) -> Iterable[DimensionConfig]:
        """Return all configured dimensions."""
        return list(self._dim_configs.values())

    def get_dimension_role(self, dim_name: str) -> DimensionRole:
        return self._dim_configs[dim_name].role

    def set_dimension(self, dim_name: str) -> None:
        """Switch the active dimension (hidden state)."""
        if dim_name not in self._dim_ids:
            raise KeyError(f"Unknown dimension: {dim_name}")
        self._current_dim_id = self._dim_ids[dim_name]

    # ----------------------------------------------------------------------
    # Public API: core operations
    # ----------------------------------------------------------------------

    def set(self, x: int, y: int, z: int, value: Any) -> None:
        """Write value at (x, y, z) in the current dimension."""
        self._check_bounds(x, y, z)
        dim_name = self.current_dimension
        role = self.get_dimension_role(dim_name)

        if role == DimensionRole.TRAP:
            if self._enable_trap_exception:
                raise TrapAccessError(f"Write in TRAP dimension '{dim_name}' at {(x, y, z)}")
            # Else: silently allow but still store/log

        addr = self._addr(self._current_dim_id, x, y, z)
        self._storage[addr] = value
        self._log_access("SET", dim_name, x, y, z, addr)

    def get(self, x: int, y: int, z: int, default: Any = None) -> Any:
        """Read value at (x, y, z) in the current dimension."""
        self._check_bounds(x, y, z)
        dim_name = self.current_dimension
        role = self.get_dimension_role(dim_name)

        if role == DimensionRole.TRAP:
            if self._enable_trap_exception:
                raise TrapAccessError(f"Read in TRAP dimension '{dim_name}' at {(x, y, z)}")
            # Else: fall through and return whatever is stored (or default)

        addr = self._addr(self._current_dim_id, x, y, z)
        self._log_access("GET", dim_name, x, y, z, addr)
        return self._storage.get(addr, default)

    def exists(self, x: int, y: int, z: int) -> bool:
        """Return True if a cell is explicitly stored in the current dimension."""
        self._check_bounds(x, y, z)
        addr = self._addr(self._current_dim_id, x, y, z)
        return addr in self._storage

    # ----------------------------------------------------------------------
    # Introspection helpers
    # ----------------------------------------------------------------------

    def iter_logical_cells(self, dim_name: Optional[str] = None):
        """
        Iterate over non-empty logical cells in a given dimension (or current dimension if None).

        Yields tuples (x, y, z, value).
        """
        if dim_name is None:
            dim_id = self._current_dim_id
            dim_name = self.current_dimension
        else:
            if dim_name not in self._dim_ids:
                raise KeyError(f"Unknown dimension: {dim_name}")
            dim_id = self._dim_ids[dim_name]

        # For introspection we must brute-force scan logical space
        X, Y, Z = self._dims
        for x in range(X):
            for y in range(Y):
                for z in range(Z):
                    addr = self._addr(dim_id, x, y, z)
                    if addr in self._storage:
                        yield (x, y, z, self._storage[addr])

    def dump_dimension(self, dim_name: Optional[str] = None) -> Dict[Tuple[int, int, int], Any]:
        """
        Return a mapping {(x, y, z): value} for all populated cells in the given dimension.
        """
        result: Dict[Tuple[int, int, int], Any] = {}
        for x, y, z, v in self.iter_logical_cells(dim_name):
            result[(x, y, z)] = v
        return result

    def dump_storage_raw(self) -> Dict[int, Any]:
        """
        Return the raw physical storage (addr -> value).

        In an actual memory dump scenario, this is essentially what an attacker would see:
        random-looking addresses with no direct visible link to (D, x, y, z).
        """
        # Expose a shallow copy to avoid accidental modification
        return dict(self._storage)

    def get_access_log(self):
        """
        Return the recorded access log as a list of entries:
        (op, dim_name, x, y, z, addr)
        """
        return list(self._access_log)

    # ----------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------

    def _log_access(self, op: str, dim_name: str, x: int, y: int, z: int, addr: int) -> None:
        if not self._access_log_enabled:
            return
        self._access_log.append((op, dim_name, x, y, z, addr))

    def _check_bounds(self, x: int, y: int, z: int) -> None:
        if not (0 <= x < self._X and 0 <= y < self._Y and 0 <= z < self._Z):
            raise IndexError(f"Index {(x, y, z)} out of bounds for shape {self._dims}")

    def _addr(self, dim_id: int, x: int, y: int, z: int) -> int:
        """
        Compute a pseudorandom 64-bit address from (dim_id, x, y, z, key).

        This is NOT cryptographically proven, but is sufficient for PoC-style
        obfuscation of physical layout.

        Using BLAKE2b as a PRF-like keyed function:
            addr = int( BLAKE2b(key=K, data=dim||x||y||z, digest_size=8) )
        """
        # 4 bytes each is sufficient for reasonable shapes
        payload = (
            dim_id.to_bytes(4, "little", signed=False) +
            x.to_bytes(4, "little", signed=False) +
            y.to_bytes(4, "little", signed=False) +
            z.to_bytes(4, "little", signed=False)
        )
        h = blake2b(payload, key=self._key, digest_size=8)
        return int.from_bytes(h.digest(), "little", signed=False)
