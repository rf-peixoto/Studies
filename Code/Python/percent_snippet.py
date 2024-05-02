def calc_change(o, n):
    if o == 0:
        raise ValueError("Old value cannot be zero.")
    c = ((n - o) / o) * 100
    print(f"{'+ ' if c > 0 else '- '}{abs(c):.2f}%")
