#!/usr/bin/env python3
import argparse
import random
from typing import List

def cpf_check_digits(base9: List[int]) -> List[int]:
    """
    Compute CPF check digits (d10, d11) for the first 9 digits.
    """
    # First check digit (10th digit)
    s1 = sum(d * w for d, w in zip(base9, range(10, 1, -1)))  # weights 10..2
    r1 = (s1 * 10) % 11
    d10 = 0 if r1 == 10 else r1

    # Second check digit (11th digit)
    base10 = base9 + [d10]
    s2 = sum(d * w for d, w in zip(base10, range(11, 1, -1)))  # weights 11..2
    r2 = (s2 * 10) % 11
    d11 = 0 if r2 == 10 else r2

    return [d10, d11]

def is_all_digits_equal(digits: List[int]) -> bool:
    return all(d == digits[0] for d in digits)

def format_cpf(digits11: List[int]) -> str:
    s = "".join(map(str, digits11))
    return f"{s[0:3]}.{s[3:6]}.{s[6:9]}-{s[9:11]}"

def generate_invalid_cpf(formatted: bool = False) -> str:
    """
    Generate a CPF that is structurally correct but guaranteed invalid
    (fails check digits).
    """
    while True:
        base9 = [random.randint(0, 9) for _ in range(9)]
        if is_all_digits_equal(base9):
            continue

        d10, d11 = cpf_check_digits(base9)
        cpf_digits = base9 + [d10, d11]

        # Force invalidity by flipping the last check digit to a different value.
        # This keeps the CPF "rule-shaped" but invalid by checksum.
        cpf_digits[10] = (cpf_digits[10] + random.randint(1, 9)) % 10

        # Extra safety: avoid the trivial all-equal 11-digit pattern
        if is_all_digits_equal(cpf_digits):
            continue

        return format_cpf(cpf_digits) if formatted else "".join(map(str, cpf_digits))

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a TXT file with N Brazilian CPFs that look valid but are guaranteed invalid."
    )
    parser.add_argument("n", type=int, help="Number of lines (CPFs) to generate.")
    parser.add_argument("-o", "--out", default="cpfs.txt", help="Output file path (default: cpfs.txt).")
    parser.add_argument("--formatted", action="store_true", help="Write CPFs as ###.###.###-## (default: only digits).")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducibility.")
    args = parser.parse_args()

    if args.n <= 0:
        raise SystemExit("n must be a positive integer.")

    if args.seed is not None:
        random.seed(args.seed)

    with open(args.out, "w", encoding="utf-8") as f:
        for _ in range(args.n):
            f.write(generate_invalid_cpf(formatted=args.formatted) + "\n")

if __name__ == "__main__":
    main()
