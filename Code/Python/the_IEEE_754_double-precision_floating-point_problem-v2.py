#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Didactic PoC: RNG + floats + asynchrony + network serialization + security pitfalls (single script)

This script demonstrates, in a *single process*, several real-world failure modes:

A) "Same seed" myth with floating-point-derived seeds:
   - Seeding RNG from float timestamps / latencies can reduce entropy and create collisions.

B) Network / JSON float serialization causing RNG divergence:
   - One side rounds a float (e.g., JSON with 3 decimals), the other keeps full precision.
   - If that float influences the seed or RNG consumption, you get desync and fairness issues.

C) Asynchrony / scheduling changing RNG consumption order:
   - Two async tasks consume the same RNG in different interleavings -> different outcomes.
   - This is a determinism risk (and can become a security issue if clients can influence ordering).

D) Security: time-seeded PRNG is guessable:
   - Given a few observed outputs, a time-window brute force can recover the seed.
   - This is why Mersenne Twister / `random` is not suitable for security.
   - Use `secrets` (CSPRNG) for security tokens, nonces, session IDs, cryptographic randomness.

Run:
  python3 rng_float_async_net_poc.py

Notes:
- ANSI colors require a terminal; output remains readable without colors.
- This is a defensive educational demo, not guidance to attack real systems.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple


# -----------------------------
# Minimal ANSI color utilities
# -----------------------------
USE_COLOR = sys.stdout.isatty()

def c(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def H(text: str) -> str:      # header
    return c(text, "1;36")    # bold cyan

def OK(text: str) -> str:
    return c(text, "1;32")    # bold green

def WARN(text: str) -> str:
    return c(text, "1;33")    # bold yellow

def BAD(text: str) -> str:
    return c(text, "1;31")    # bold red

def DIM(text: str) -> str:
    return c(text, "2")       # dim

def SEP(title: str) -> None:
    bar = "─" * 86
    print()
    print(H(bar))
    print(H(title))
    print(H(bar))


def show(label: str, value) -> None:
    print(f"{label:<34} {value}")


# -----------------------------
# Helper: seed mixing
# -----------------------------
def seed_from_material(material: str) -> int:
    """
    Convert arbitrary string material to a 64-bit seed via SHA-256.
    This is deterministic but does NOT make the underlying PRNG cryptographically secure.
    It only demonstrates how seeds are derived in practice.
    """
    h = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


# =========================================================
# A) Float-derived seeds: collisions and entropy reduction
# =========================================================
def demo_a_float_seed_collisions() -> None:
    SEP("A) Float-derived seeds: collisions and entropy reduction")

    print("Common bad pattern: seed = int(time.time() * 1000) or similar.")
    print("This *appears* high-resolution, but in practice it can collide and is guessable.")

    # Simulate "timestamps" that differ at sub-millisecond scale.
    # Many systems cannot reliably provide that entropy, and float representation can blur it.
    base = 1700000000.123456  # fixed reference for reproducibility (seconds)
    offsets = [i * 1e-7 for i in range(0, 50)]  # 0..4.9 microseconds

    seeds_ms = []
    seeds_us = []
    for off in offsets:
        t = base + off
        seeds_ms.append(int(t * 1000))       # milliseconds
        seeds_us.append(int(t * 1_000_000))  # microseconds

    unique_ms = len(set(seeds_ms))
    unique_us = len(set(seeds_us))

    show("Total samples", len(offsets))
    show("Unique seeds (ms)", unique_ms)
    show("Unique seeds (µs)", unique_us)

    print()
    if unique_ms < len(offsets):
        print(BAD("Observation:") + " multiple distinct times collapsed to the same millisecond seed.")
        print("If you seed per request/event, collisions can repeat 'random' sequences.")
    else:
        print(WARN("Observation:") + " here milliseconds did not collide, but collisions are common in real workloads.")

    print()
    print("Also, time-derived seeds are highly predictable: an observer often knows the approximate time.")


# =========================================================
# B) Network serialization rounding causes RNG divergence
# =========================================================
def demo_b_network_json_rounding_divergence() -> None:
    SEP("B) Network/JSON float rounding: same event, different seed, divergent RNG")

    print("Scenario: a client sends a float (latency, timestamp, position, etc.) via JSON.")
    print("One side rounds to 3 decimals for compactness; the other keeps full precision.")
    print("If that float influences RNG seed/consumption, clients desynchronize.")

    # A float with many decimals that cannot be represented exactly in binary
    latency = 0.12345678901234568  # representative float
    show("Original float repr()", repr(latency))

    # Sender encodes with rounding (common: format to 3 decimals)
    payload_sender = {"latency": float(f"{latency:.3f}")}
    wire = json.dumps(payload_sender)  # what travels
    show("JSON on wire", wire)

    # Receiver parses that rounded value
    payload_receiver = json.loads(wire)
    latency_recv = payload_receiver["latency"]
    show("Received float repr()", repr(latency_recv))

    # Now both derive seeds from "latency" (a fragile design, used only for demonstration)
    seed_sender = seed_from_material(f"seed|latency={latency!r}")
    seed_receiver = seed_from_material(f"seed|latency={latency_recv!r}")

    show("Derived seed (sender)", seed_sender)
    show("Derived seed (receiver)", seed_receiver)
    print()

    rng_sender = random.Random(seed_sender)
    rng_receiver = random.Random(seed_receiver)

    # Compare a short stream of outputs
    out_sender = [rng_sender.randrange(0, 1000000) for _ in range(5)]
    out_receiver = [rng_receiver.randrange(0, 1000000) for _ in range(5)]

    show("Sender RNG outputs", out_sender)
    show("Receiver RNG outputs", out_receiver)

    if out_sender != out_receiver:
        print()
        print(BAD("Result:") + " RNG divergence caused solely by network rounding.")
        print("In a game: client-side prediction, loot drops, crits, recoil patterns, etc. can desync.")
        print("In security: anything derived from such seeds becomes unreliable and potentially predictable.")
    else:
        print()
        print(WARN("Result:") + " outputs matched here, but do not rely on this; the design remains fragile.")

    print()
    print(OK("Mitigation patterns:"))
    print("- Do not derive RNG seeds from floats coming from the network.")
    print("- If you must send numeric state, send integers (e.g., microseconds as int) or canonical strings.")
    print("- For fairness/security: use server-authoritative RNG or cryptographic commit-reveal (outlined later).")


# =========================================================
# C) Asynchrony changes RNG consumption order (single script)
# =========================================================
@dataclass
class Event:
    name: str
    delay: float  # seconds
    draws: int    # how many RNG draws this event consumes

async def consume_rng(rng: random.Random, ev: Event, log: List[Tuple[str, List[int]]]) -> None:
    await asyncio.sleep(ev.delay)
    draws = [rng.randrange(0, 1000) for _ in range(ev.draws)]
    log.append((ev.name, draws))

async def run_schedule(seed: int, events: List[Event]) -> List[Tuple[str, List[int]]]:
    rng = random.Random(seed)
    log: List[Tuple[str, List[int]]] = []
    tasks = [asyncio.create_task(consume_rng(rng, ev, log)) for ev in events]
    await asyncio.gather(*tasks)
    return log

def demo_c_async_rng_interleaving() -> None:
    SEP("C) Asynchrony: RNG consumption order depends on scheduling, causing different outcomes")

    print("Scenario: multiple async events share one PRNG instance.")
    print("Even with the same seed, event ordering determines which event receives which random values.")
    print("If clients can influence timing/order (network jitter, message batching), outcomes can differ.")

    seed = 4242424242

    # Two schedules: same events, slightly different timing.
    # In real systems, this can come from jitter, IO timing, or task scheduling.
    schedule_1 = [
        Event("hit_check", 0.010, 2),
        Event("loot_roll", 0.020, 3),
        Event("crit_roll", 0.015, 1),
    ]
    schedule_2 = [
        Event("hit_check", 0.010, 2),
        Event("loot_roll", 0.015, 3),  # swapped timing with crit_roll
        Event("crit_roll", 0.020, 1),
    ]

    log1 = asyncio.run(run_schedule(seed, schedule_1))
    log2 = asyncio.run(run_schedule(seed, schedule_2))

    show("Seed", seed)
    print()
    print(H("Schedule 1 event->draws:"))
    for name, draws in sorted(log1, key=lambda x: x[0]):
        show(f"  {name}", draws)

    print()
    print(H("Schedule 2 event->draws:"))
    for name, draws in sorted(log2, key=lambda x: x[0]):
        show(f"  {name}", draws)

    # Compare by event name
    map1 = {n: d for n, d in log1}
    map2 = {n: d for n, d in log2}

    print()
    diffs = [n for n in map1.keys() if map1[n] != map2[n]]
    if diffs:
        print(BAD("Result:") + " same seed, different timing => different per-event randomness.")
        show("Events affected", diffs)
        print()
        print(OK("Mitigation patterns:"))
        print("- Do not share one PRNG across async tasks for gameplay-critical decisions.")
        print("- Allocate deterministic substreams: e.g., derive per-event RNG from (seed, event_id, tick).")
        print("- Or centralize RNG draws in a single deterministic loop (authoritative simulation).")
    else:
        print(WARN("Result:") + " no event differences observed (unlikely), but the risk remains in general.")


# =========================================================
# D) Security: time-seeded PRNG is guessable (seed recovery demo)
# =========================================================
def demo_d_time_seed_guessability() -> None:
    SEP("D) Security: time-seeded PRNG is guessable (seed recovery in a narrow window)")

    print("Demonstration: if a system seeds PRNG with current time (ms), the seed space is small.")
    print("Given a few observed outputs and an approximate time window, the seed can be recovered.")
    print(DIM("This is why Python's 'random' (Mersenne Twister) is unsuitable for security."))

    # Simulate a victim system: seed derived from "current ms"
    # We use a fixed reference time for repeatability.
    victim_time_ms = 1_700_000_000_123  # pretend "now" in ms (fixed)
    victim_seed = victim_time_ms

    victim_rng = random.Random(victim_seed)

    # Victim produces a few tokens (e.g., nonces, reset codes, game session keys) -- bad practice.
    observed = [victim_rng.randrange(0, 10_000_000) for _ in range(4)]
    show("Observed outputs (attacker sees)", observed)

    # Attacker knows approximate time within +/- 2000 ms
    window = 2000
    start = victim_time_ms - window
    end = victim_time_ms + window

    print()
    show("Attacker search window (ms)", f"{start} .. {end}  (size={end-start+1})")

    recovered = None
    for candidate_seed in range(start, end + 1):
        r = random.Random(candidate_seed)
        trial = [r.randrange(0, 10_000_000) for _ in range(4)]
        if trial == observed:
            recovered = candidate_seed
            break

    print()
    if recovered is None:
        print(WARN("Result:") + " seed not recovered (unexpected in this controlled demo).")
    else:
        show("Recovered seed (ms)", recovered)
        show("Matches victim seed?", recovered == victim_seed)
        print()
        print(BAD("Security conclusion:") + " time-seeded PRNG outputs are guessable.")

    print()
    print(OK("Correct security primitives:"))
    print("- Use `secrets.token_bytes()` / `secrets.randbelow()` for tokens, nonces, session IDs.")
    print("- Do not use `random` for anything security-relevant.")
    print()
    print(OK("Correct fairness patterns for networked RNG:"))
    print("- Server-authoritative RNG for game outcomes; clients receive results, not seeds.")
    print("- If you need transparency/fairness, use commit-reveal:")
    print("  1) Server commits to a secret (hash) before the event.")
    print("  2) After the event, server reveals the secret; clients verify the hash.")
    print("  3) Outcome derived from H(secret || event_id || public_salt).")


# =========================================================
# E) A robust deterministic pattern: per-event RNG substream
# =========================================================
def demo_e_deterministic_substreams() -> None:
    SEP("E) Deterministic and async-safe RNG substreams (defensive design pattern)")

    print("If you need determinism across network/async boundaries, do not consume a shared RNG ad hoc.")
    print("Instead, derive per-event RNG from stable identifiers:")
    print("  rng_event = Random( SHA256(master_seed || tick || event_id) )")
    print("Then each event draws from its own substream, independent of scheduling order.")

    master_seed = 123456789
    tick = 9001
    event_ids = ["hit_check", "loot_roll", "crit_roll"]

    outputs = {}
    for eid in event_ids:
        seed = seed_from_material(f"{master_seed}|{tick}|{eid}")
        r = random.Random(seed)
        outputs[eid] = [r.randrange(0, 1000) for _ in range(5)]

    show("master_seed", master_seed)
    show("tick", tick)
    print()
    for eid in event_ids:
        show(f"{eid} draws", outputs[eid])

    print()
    print(OK("Property:") + " event results are stable even if async ordering changes.")
    print(WARN("Important:") + " this improves determinism, not cryptographic security.")
    print("For security-sensitive randomness, still use CSPRNG (`secrets`) or cryptographic constructions.")


def main() -> None:
    print(H("RNG + Floats + Asynchrony + Network + Security (Didactic PoC)"))
    print(DIM("Python float behaves like JS Number (IEEE-754 binary64). The security issues are language-agnostic."))

    demo_a_float_seed_collisions()
    demo_b_network_json_rounding_divergence()
    demo_c_async_rng_interleaving()
    demo_d_time_seed_guessability()
    demo_e_deterministic_substreams()

    print()
    print(H("Summary (practical rules):"))
    print("1) Do not seed PRNG from floats, timestamps, or network-derived decimals.")
    print("2) Do not use `random` for security. Use `secrets`.")
    print("3) Avoid shared PRNG consumption across async tasks; use deterministic substreams or a single loop.")
    print("4) For multiplayer fairness: server-authoritative RNG, or commit-reveal for verifiability.")


if __name__ == "__main__":
    main()
