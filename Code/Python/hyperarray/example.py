from hyperarray import HyperArray, DimensionConfig, DimensionRole, TrapAccessError


def demo():
    # Logical size: small for demonstration
    X, Y, Z = 4, 4, 4

    # Define three "universes"
    dims = [
        DimensionConfig(name="real",  role=DimensionRole.REAL),
        DimensionConfig(name="decoy", role=DimensionRole.DECOY),
        DimensionConfig(name="trap",  role=DimensionRole.TRAP),
    ]

    # Create hyperarray with random key
    ha = HyperArray(dims=(X, Y, Z), dimensions=dims, enable_trap_exception=True)

    print("Dimensions:")
    for d in ha.list_dimensions():
        print(f"  - {d.name} ({d.role.value})")
    print()

    # Write some data in REAL dimension
    ha.set_dimension("real")
    ha.set(1, 1, 1, "SECRET_PAYLOAD")
    ha.set(2, 2, 2, 1337)

    # Write decoy data in DECOY dimension at the SAME logical coordinates
    ha.set_dimension("decoy")
    ha.set(1, 1, 1, "HARmless dummy")
    ha.set(2, 2, 2, 0)

    # Optionally fill some random noise in decoy dimension
    ha.set(0, 0, 0, "RANDOM_NOISE")

    # Try TRAP access (should raise if enable_trap_exception=True)
    ha.set_dimension("trap")
    try:
        ha.set(1, 1, 1, "TRAP_VALUE")
    except TrapAccessError as e:
        print(f"[TRAP] Caught trap write: {e}")

    # Read from different dimensions
    print("\nReading (1,1,1) in REAL:")
    ha.set_dimension("real")
    print("  ->", ha.get(1, 1, 1))

    print("\nReading (1,1,1) in DECOY:")
    ha.set_dimension("decoy")
    print("  ->", ha.get(1, 1, 1))

    print("\nTrying to read (1,1,1) in TRAP:")
    ha.set_dimension("trap")
    try:
        print("  ->", ha.get(1, 1, 1))
    except TrapAccessError as e:
        print(f"  [TRAP] Caught trap read: {e}")

    # Dump logical content per dimension
    print("\nLogical view of REAL dimension:")
    print(ha.dump_dimension("real"))

    print("\nLogical view of DECOY dimension:")
    print(ha.dump_dimension("decoy"))

    # Show raw physical storage
    print("\nRaw physical storage (addr -> value):")
    raw = ha.dump_storage_raw()
    for addr, val in list(raw.items())[:10]:  # print at most 10 entries
        print(f"  {hex(addr)} -> {repr(val)}")

    # Show access log
    print("\nAccess log:")
    for entry in ha.get_access_log():
        op, dim_name, x, y, z, addr = entry
        print(f"  {op} {dim_name} @ ({x},{y},{z}) -> {hex(addr)}")


if __name__ == "__main__":
    demo()
