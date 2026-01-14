#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Floating-point rounding PoC (didactic, single-script, colored output)

Goal
----
Show *several* realistic ways IEEE-754 binary floating point can change program behavior.
This is not "Python being bad"—Python's float is an IEEE-754 binary64 double, like JS Number.

What you will see
-----------------
1) Decimal representation: 0.1 cannot be represented exactly.
2) Equality trap: looping by 0.1 never hits exactly 10.0, so a naive reward never triggers.
3) Threshold drift: an event scheduled for t >= 10.0 can fire one tick later than expected.
4) Accumulation: summing many small values depends on order; a borderline comparison can flip.
5) Quantization drift: repeatedly rounding in a loop (e.g., UI display or currency) changes outcome.
6) Real-world pattern: "charge user 0.01 repeatedly" (float vs Decimal vs integer cents).
7) Correct patterns: epsilon comparisons, fixed-point integers, Decimal.

Run
---
  python3 float_didactic_poc.py

Notes
-----
- ANSI colors work in most terminals. If yours does not, you will still get the content.
- The script is intentionally verbose and explanatory.
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal, getcontext

getcontext().prec = 50  # High precision for decimal demonstrations


# -----------------------------
# Minimal ANSI color utilities
# -----------------------------
USE_COLOR = sys.stdout.isatty()

def c(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def H(text: str) -> str:   # header
    return c(text, "1;36")  # bold cyan

def OK(text: str) -> str:
    return c(text, "1;32")  # bold green

def WARN(text: str) -> str:
    return c(text, "1;33")  # bold yellow

def BAD(text: str) -> str:
    return c(text, "1;31")  # bold red

def DIM(text: str) -> str:
    return c(text, "2")     # dim

def SEP(title: str) -> None:
    bar = "─" * 78
    print()
    print(H(bar))
    print(H(f"{title}"))
    print(H(bar))


def show_value(label: str, value) -> None:
    # repr shows the "real" float; str shows the rounded human display.
    if isinstance(value, float):
        print(f"{label:<28} str={value}   repr={value!r}")
    else:
        print(f"{label:<28} {value}")


# -----------------------------
# 1) Representation basics
# -----------------------------
def demo_representation_basics() -> None:
    SEP("1) Representation: why 0.1 + 0.2 looks 'wrong'")

    a = 0.1
    b = 0.2
    s = a + b

    show_value("a", a)
    show_value("b", b)
    show_value("a + b", s)
    show_value("Expected (decimal) 0.3", 0.3)

    print()
    print("Binary floating point cannot represent 0.1 exactly, therefore the stored value is")
    print("the nearest representable binary fraction. This is *normal* IEEE-754 behavior.")
    print(WARN("Important:") + " printing often hides errors by rounding for display.")
    print("For a sharper view, print with many digits:")

    print(f"0.1 + 0.2 with 17 digits: {s:.17f}")
    print(f"0.3       with 17 digits: {0.3:.17f}")
    print(f"Difference (s - 0.3)     : {(s - 0.3):.17f}")


# -----------------------------
# 2) Equality trap
# -----------------------------
def demo_equality_trap() -> None:
    SEP("2) Equality trap: 'give reward when x == 10.0'")

    dt = 0.1
    target = 10.0
    x = 0.0

    hit = None
    for step in range(1, 2000):
        x += dt
        if x == target:  # BAD PRACTICE
            hit = step
            break

    if hit is None:
        print(BAD("Result:") + " x never became exactly 10.0 within 2000 steps.")
    else:
        print(OK("Result:") + f" x hit exactly 10.0 at step {hit} (this is uncommon).")

    print()
    print("However, x gets extremely close to 10.0 around step 100.")
    # Show the value at step 100
    x2 = 0.0
    for _ in range(100):
        x2 += dt
    show_value("x after 100 steps", x2)
    print(f"x2 == 10.0 ? {x2 == 10.0}")

    print()
    eps = 1e-12
    print("Safer comparison for continuous values:")
    print(f"Use abs(x - target) < eps, for example eps={eps:g}")
    print(f"abs(x2 - 10.0)      = {abs(x2 - target)!r}")
    print(f"Within eps?          {abs(x2 - target) < eps}")


# -----------------------------
# 3) Event scheduling drift
# -----------------------------
def demo_event_scheduling_drift() -> None:
    SEP("3) Event scheduling drift: 'fire at t >= 10.0'")

    dt = 0.1
    target = 10.0
    t = 0.0

    fired_step = None
    for step in range(1, 2000):
        t += dt
        if t >= target:
            fired_step = step
            break

    expected_step = int(target / dt)  # mathematically 100
    print(f"Mathematically expected step: {expected_step}")
    print(f"Actual float step           : {fired_step}")
    show_value("t at fire", t)
    print(f"t - target                  : {(t - target)!r}")

    print()
    print("This can matter in games when rewards/attacks/cooldowns tick on exact boundaries.")
    print("It is not random: it is deterministic. But it can cause off-by-one tick behavior.")


# -----------------------------
# 4) Summation order matters
# -----------------------------
def demo_summation_order() -> None:
    SEP("4) Summation order: same numbers, different result near a threshold")

    # Construct values where order impacts rounding (classic numerical stability issue).
    # Add a huge number with many tiny numbers. Tiny increments can be lost depending on order.
    big = 1e16
    smalls = [1.0] * 10_000  # 10k ones

    # Sum in a "bad" order: big first, then smalls.
    s1 = big
    for v in smalls:
        s1 += v

    # Sum in a "better" order: smalls first, then big.
    s2 = sum(smalls) + big

    show_value("big", big)
    show_value("sum(smalls)", sum(smalls))
    show_value("s1 = big + smalls", s1)
    show_value("s2 = smalls + big", s2)
    print()
    print("In exact arithmetic, s1 and s2 would be equal.")
    print("In floating-point, some small increments may not change the accumulator once it is large enough.")

    # Now show a threshold comparison that can flip
    threshold = big + 9_999  # one less than the full addition
    print()
    show_value("threshold", threshold)
    print(f"s1 >= threshold ? {s1 >= threshold}")
    print(f"s2 >= threshold ? {s2 >= threshold}")

    if (s1 >= threshold) != (s2 >= threshold):
        print(BAD("Branch difference detected:") + " order changed a comparison outcome.")
    else:
        print(WARN("No branch flip here,") + " but the numeric discrepancy is real and measurable.")

    print()
    print("Mitigation: use numerically stable summation where relevant (e.g., math.fsum).")
    s3 = math.fsum([big] + smalls)
    show_value("math.fsum([big]+smalls)", s3)


# -----------------------------
# 5) Quantization drift (common in UI/currency)
# -----------------------------
def demo_quantization_drift() -> None:
    SEP("5) Quantization drift: rounding every step (UI display / currency bug pattern)")

    # Pattern: updating a value, then rounding it for display/storage each tick.
    # This is a frequent real-world bug: repeated rounding changes the trajectory.
    dt = 1/3  # intentionally awkward in binary and decimal
    x_raw = 0.0
    x_rounded_each_step = 0.0

    for _ in range(300):
        x_raw += dt
        x_rounded_each_step = round(x_rounded_each_step + dt, 2)  # forcing 2 decimals each step

    show_value("x_raw (no per-step rounding)", x_raw)
    show_value("x_rounded_each_step (2dp)", x_rounded_each_step)
    print()
    diff = x_rounded_each_step - round(x_raw, 2)
    print(f"Difference after 300 steps (rounded_each_step - round(raw,2)) = {diff!r}")
    print(WARN("Lesson:") + " rounding strategy (when/how often) is part of your algorithm.")


# -----------------------------
# 6) Real-world money example: float vs Decimal vs integer cents
# -----------------------------
def demo_money_like_behavior() -> None:
    SEP("6) Money-like example: repeated charges of 0.01")

    n = 100_000
    charge_float = 0.01
    balance_float = 0.0
    for _ in range(n):
        balance_float += charge_float

    # Decimal
    charge_dec = Decimal("0.01")
    balance_dec = Decimal("0.00")
    for _ in range(n):
        balance_dec += charge_dec

    # Integer cents
    charge_cents = 1
    balance_cents = 0
    for _ in range(n):
        balance_cents += charge_cents

    expected = n * 0.01  # mathematically 1000.0
    print(f"n charges: {n}")
    print(f"Expected:  {expected} (mathematical)")

    show_value("balance_float", balance_float)
    show_value("balance_dec  ", balance_dec)
    show_value("balance_cents", balance_cents)

    print()
    print("If you do a check like 'balance == 1000.0', float may fail; Decimal/integer will not.")
    print(f"float balance == 1000.0 ? {balance_float == 1000.0}")
    print(f"Decimal balance == 1000 ? {balance_dec == Decimal('1000.00')}")
    print(f"cents balance == 100000  ? {balance_cents == 100_000}")

    print()
    print(OK("Practical guidance:"))
    print("- Use integers (cents) for money-like values.")
    print("- Use Decimal if you truly need base-10 exactness and accept the performance cost.")
    print("- Use floats for physics/graphics, but never rely on exact equality for thresholds.")


# -----------------------------
# 7) A compact “game-ish” scenario: reward timing difference
# -----------------------------
def demo_gameish_reward_timing() -> None:
    SEP("7) Game-ish scenario: reward timing depends on float comparison")

    # Scenario:
    # - You add 0.1 "energy" per tick.
    # - At energy >= 10.0, you grant a reward and reset energy to 0.
    #
    # A naive equality check can completely break the reward system.
    # A naive threshold check may delay by one tick.
    # This can be perceived as unfair if timing matters (cooldowns, i-frames, etc.).

    dt = 0.1
    target = 10.0

    # (A) BAD: equality check
    energy = 0.0
    reward_tick_eq = None
    for tick in range(1, 500):
        energy += dt
        if energy == target:  # BAD
            reward_tick_eq = tick
            break

    # (B) Better: threshold check, but show possible off-by-one tick
    energy = 0.0
    reward_tick_ge = None
    for tick in range(1, 500):
        energy += dt
        if energy >= target:
            reward_tick_ge = tick
            break

    # (C) Correct: fixed-point tenths
    energy_tenths = 0
    dt_tenths = 1
    target_tenths = 100
    reward_tick_fixed = None
    for tick in range(1, 500):
        energy_tenths += dt_tenths
        if energy_tenths >= target_tenths:
            reward_tick_fixed = tick
            break

    print("Reward tick using energy == 10.0 :", BAD(str(reward_tick_eq)) if reward_tick_eq is None else str(reward_tick_eq))
    print("Reward tick using energy >= 10.0 :", str(reward_tick_ge))
    print("Reward tick using fixed-point    :", str(reward_tick_fixed))

    print()
    if reward_tick_eq is None:
        print(BAD("Equality check failed completely:") + " a player would never receive the reward.")
    if reward_tick_ge != reward_tick_fixed:
        print(WARN("Threshold timing mismatch:") + " float triggered on a different tick than fixed-point.")
        print("This can be a gameplay-relevant difference when tick boundaries are meaningful.")
    else:
        print(OK("Threshold matched fixed-point here,") + " but do not infer that equality is safe.")

    print()
    print("Recommended rule for gameplay thresholds:")
    print(" - Use fixed-point for authoritative counters/timers (ticks, ms, frames).")
    print(" - Use floats for rendering/physics, then quantize state as needed.")


def main() -> None:
    print(H("IEEE-754 Floating-Point Didactic PoC (Python float == JS Number behavior)"))
    print(DIM("Tip: run in a terminal for colors. The content remains valid without colors."))

    demo_representation_basics()
    demo_equality_trap()
    demo_event_scheduling_drift()
    demo_summation_order()
    demo_quantization_drift()
    demo_money_like_behavior()
    demo_gameish_reward_timing()

    print()
    print(H("Done."))
    print("If you want to dig deeper next, the most educational extension is:")
    print(" - compare float64 vs float32 drift (using numpy), and/or")
    print(" - demonstrate catastrophic cancellation and stable reformulations.")


if __name__ == "__main__":
    main()
