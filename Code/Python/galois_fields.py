#!/usr/bin/env python3
"""
Galois Field Explorer — an interactive visualiser for finite fields GF(p^n).

How the field is built
----------------------
GF(p^n) = GF(p)[x] / (f(x)) where f is a monic irreducible polynomial of degree n.
Every element is a polynomial  c_{n-1} α^{n-1} + … + c_1 α + c_0  (α = class of x,
c_i in {0..p-1}).  The integer label of that element is the base-p number
c_{n-1}…c_1 c_0, so for n > 1 the integer order says nothing about multiplication.
GF(q)* (the nonzero elements) is cyclic: there is a generator g with
GF(q)* = {g^0, g^1, …, g^(q-2)}.  Laying the points out in that "power order" turns
multiplication into a rotation, which is the picture the original script was missing.

Everything here is pure Python (only tkinter for the GUI); no numpy / galois needed.

Usage
-----
  python3 galois_explorer.py                      # GUI, GF(16)
  python3 galois_explorer.py --p 3 --n 2 --op pow --k 3
  python3 galois_explorer.py --aes --op sbox      # AES field GF(2^8)
  python3 galois_explorer.py --random             # random field, like the old script
  python3 galois_explorer.py --print --p 2 --n 3  # text output, no GUI
  python3 galois_explorer.py --selftest           # check the arithmetic

Input syntax for elements (everywhere in the GUI)
-------------------------------------------------
  13   0x1b   0b1101        integer label (decimal / hex / binary)
  x^3 + x + 1   α^3+1       polynomial in α (any degree, reduced mod f)
  g^7   g                   power of the generator
  (1 1 0 1)                 coefficient vector, highest degree first
  -5                        additive inverse of element 5
Exponents k accept small expressions in q, p, n: e.g. q-2 (that is the inverse map).
"""

from __future__ import annotations

import argparse
import colorsys
import math
import random
import re
import sys
from functools import lru_cache

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:  # GUI-less Python: --print and --selftest still work
    tk = None

MAX_Q = 2048            # largest field the explorer will build
TABLE_MAX_Q = 128       # largest field drawn as a full addition/multiplication table
ELEMENT_TABLE_MAX_Q = 81
AES_MODULUS = (1, 1, 0, 1, 1, 0, 0, 0, 1)   # x^8 + x^4 + x^3 + x + 1  (0x11B), low -> high

SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
UNSUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def sup(k) -> str:
    return str(k).translate(SUP)


# ═════════════════════════════════════════════════════════════════════════════
#  Number theory
# ═════════════════════════════════════════════════════════════════════════════
def is_prime(m: int) -> bool:
    if m < 2:
        return False
    if m % 2 == 0:
        return m == 2
    i = 3
    while i * i <= m:
        if m % i == 0:
            return False
        i += 2
    return True


def factorize(m: int) -> dict:
    out, d = {}, 2
    while d * d <= m:
        while m % d == 0:
            out[d] = out.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2
    if m > 1:
        out[m] = out.get(m, 0) + 1
    return out


def factor_str(m: int) -> str:
    if m == 1:
        return "1"
    return " · ".join(f"{p}{sup(e) if e > 1 else ''}" for p, e in sorted(factorize(m).items()))


def euler_phi(m: int) -> int:
    r = m
    for p in factorize(m):
        r = r // p * (p - 1)
    return r


def mobius(m: int) -> int:
    f = factorize(m)
    if any(e > 1 for e in f.values()):
        return 0
    return -1 if len(f) % 2 else 1


def divisors(m: int) -> list:
    return [d for d in range(1, m + 1) if m % d == 0]


def prime_power(q: int):
    """Return (p, n) with q = p^n, or None."""
    if q < 2:
        return None
    p = next(d for d in range(2, q + 1) if q % d == 0)
    n, r = 0, q
    while r % p == 0:
        r //= p
        n += 1
    return (p, n) if r == 1 else None


def count_irreducible(p: int, n: int) -> int:
    """Gauss' formula for the number of monic irreducible polynomials of degree n."""
    return sum(mobius(d) * p ** (n // d) for d in divisors(n)) // n


# ═════════════════════════════════════════════════════════════════════════════
#  Polynomials over GF(p): coefficient lists, lowest degree first
# ═════════════════════════════════════════════════════════════════════════════
def ptrim(a) -> list:
    a = list(a)
    while a and a[-1] == 0:
        a.pop()
    return a


def padd(a, b, p):
    m = max(len(a), len(b))
    return ptrim([((a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0)) % p for i in range(m)])


def psub(a, b, p):
    return padd(a, [(-c) % p for c in b], p)


def pmul(a, b, p):
    if not a or not b:
        return []
    r = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                r[i + j] = (r[i + j] + x * y) % p
    return ptrim(r)


def pdivmod(a, b, p):
    a, b = ptrim(a), ptrim(b)
    if not b:
        raise ZeroDivisionError("polynomial division by zero")
    inv_lc = pow(b[-1], -1, p)
    r = list(a)
    qd = len(a) - len(b)
    if qd < 0:
        return [], r
    quo = [0] * (qd + 1)
    for k in range(qd, -1, -1):
        c = (r[k + len(b) - 1] * inv_lc) % p
        quo[k] = c
        if c:
            for j, y in enumerate(b):
                r[k + j] = (r[k + j] - c * y) % p
    return ptrim(quo), ptrim(r)


def pmod(a, b, p):
    return pdivmod(a, b, p)[1]


def ppowmod(base, e, mod, p):
    result, base = pmod([1], mod, p), pmod(base, mod, p)
    while e > 0:
        if e & 1:
            result = pmod(pmul(result, base, p), mod, p)
        base = pmod(pmul(base, base, p), mod, p)
        e >>= 1
    return result


def poly_to_str(c, var="x", compact=False) -> str:
    c = ptrim(c)
    if not c:
        return "0"
    terms = []
    for i in range(len(c) - 1, -1, -1):
        a = c[i]
        if not a:
            continue
        if i == 0:
            terms.append(str(a))
        else:
            v = var if i == 1 else var + sup(i)
            terms.append(v if a == 1 else f"{a}{v}")
    return ("+" if compact else " + ").join(terms)


def int_to_coeffs(v: int, p: int, n: int) -> list:
    return [(v // p ** i) % p for i in range(n)]


def coeffs_to_int(c, p: int) -> int:
    return sum(x * p ** i for i, x in enumerate(c))


def monic_polys(p, d):
    for v in range(p ** d):
        yield int_to_coeffs(v, p, d) + [1]


def is_irreducible(f, p) -> bool:
    f = ptrim(f)
    n = len(f) - 1
    if n < 1:
        return False
    if n == 1:
        return True
    if f[0] == 0:
        return False                      # x divides f
    for d in range(1, n // 2 + 1):       # any factorisation has a factor of degree ≤ n/2
        for g in monic_polys(p, d):
            if g[0] and not pmod(f, g, p):
                return False
    return True


def is_primitive_poly(f, p) -> bool:
    """Irreducible f is primitive iff x has order exactly p^n - 1 modulo f."""
    f = ptrim(f)
    n = len(f) - 1
    if not is_irreducible(f, p):
        return False
    q = p ** n
    if not pmod([0, 1], f, p):
        return False
    return all(ppowmod([0, 1], (q - 1) // r, f, p) != [1] for r in factorize(q - 1))


@lru_cache(maxsize=None)
def irreducible_polys(p: int, n: int) -> tuple:
    """All monic irreducible polynomials of degree n as (coeffs, is_primitive)."""
    return tuple((tuple(g), is_primitive_poly(g, p)) for g in monic_polys(p, n) if is_irreducible(g, p))


def first_primitive_poly(p: int, n: int) -> list:
    for g in monic_polys(p, n):
        if is_primitive_poly(g, p):
            return g
    raise ValueError("no primitive polynomial found")      # cannot happen


def parse_integer_poly(text: str, p: int, n: int | None = None) -> list:
    """Parse 'x^3+x+1', '2x^2 - 1', '0x11b' or '283' into GF(p) coefficients (low -> high)."""
    s = text.strip().split("★")[0].strip()
    s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group().translate(UNSUP), s)
    s = s.lower().replace(" ", "").replace("**", "^").replace("·", "*").replace("−", "-")
    s = s.replace("α", "x")
    if re.fullmatch(r"0x[0-9a-f]+", s):
        v = int(s, 16)
        return ptrim(int_to_coeffs(v, p, max(1, v.bit_length())))
    if re.fullmatch(r"0b[01]+", s):
        v = int(s, 2)
        return ptrim(int_to_coeffs(v, p, max(1, v.bit_length())))
    if re.fullmatch(r"\d+", s) and (n is None or int(s) >= p ** n):
        v = int(s)
        return ptrim(int_to_coeffs(v, p, max(1, v.bit_length())))
    coeffs = _parse_terms(s)
    out = [0] * (max(coeffs) + 1 if coeffs else 1)
    for e, c in coeffs.items():
        out[e] = c % p
    return ptrim(out)


def _parse_terms(s: str) -> dict:
    """'2x^3-x+4' -> {3: 2, 1: -1, 0: 4}.  Coefficients are plain integers."""
    if not s or not re.fullmatch(r"[0-9x^+\-*]+", s):
        raise ValueError(f"can't read “{s}” as a polynomial")
    s = s.replace("-", "+-")
    out = {}
    for term in s.split("+"):
        if term == "":
            continue
        m = re.fullmatch(r"(-?)(\d*)\*?(x(?:\^(\d+))?)?", term)
        if not m or (m.group(2) == "" and m.group(3) is None):
            raise ValueError(f"bad term “{term}”")
        c = int(m.group(2)) if m.group(2) else 1
        if m.group(1):
            c = -c
        e = 0 if m.group(3) is None else (int(m.group(4)) if m.group(4) else 1)
        out[e] = out.get(e, 0) + c
    return out


def eval_int_expr(text: str, env: dict) -> int:
    """Small safe evaluator for exponents like 'q-2' or '(q-1)//3'."""
    s = text.strip().replace("−", "-")
    if not s or not re.fullmatch(r"[0-9qpn+\-*/%() ]+", s) or "**" in s:
        raise ValueError(f"exponent “{text}”: use an integer or an expression in q, p, n (e.g. q-2)")
    s = re.sub(r"/+", "//", s)
    try:
        v = eval(s, {"__builtins__": {}}, dict(env))  # noqa: S307 — character whitelist above
    except Exception as exc:
        raise ValueError(f"exponent “{text}”: {exc}") from None
    return int(v)


# ═════════════════════════════════════════════════════════════════════════════
#  The field
# ═════════════════════════════════════════════════════════════════════════════
class FiniteField:
    """GF(p^n) with elements encoded as integers 0..q-1 (base-p coefficient digits)."""

    def __init__(self, p: int, n: int, modulus=None):
        if not is_prime(p):
            raise ValueError(f"p = {p} is not prime")
        if n < 1:
            raise ValueError("n must be ≥ 1")
        q = p ** n
        if q > MAX_Q:
            raise ValueError(f"q = {p}^{n} = {q} is larger than the limit {MAX_Q}")
        self.p, self.n, self.q = p, n, q
        if modulus is None:
            modulus = first_primitive_poly(p, n)
        modulus = ptrim([c % p for c in modulus])
        if len(modulus) - 1 != n:
            raise ValueError(f"the modulus must have degree n = {n} (got degree {len(modulus) - 1})")
        if modulus[-1] != 1:                                   # make monic
            lc = pow(modulus[-1], -1, p)
            modulus = [(c * lc) % p for c in modulus]
        if not is_irreducible(modulus, p):
            raise ValueError(f"{poly_to_str(modulus)} factors over GF({p}), "
                             "so the quotient ring has zero divisors and is NOT a field")
        self.modulus = modulus
        self.modulus_is_primitive = is_primitive_poly(modulus, p)
        self.coeffs = [tuple(int_to_coeffs(v, p, n)) for v in range(q)]
        self._pw = [p ** i for i in range(n)]

        # α = class of x.  Use it as generator if it has full order, else search.
        self.alpha = coeffs_to_int(pmod([0, 1], modulus, p), p)
        candidates = ([self.alpha] if self.alpha else []) + [v for v in range(1, q) if v != self.alpha]
        self.g = next(v for v in candidates if self._raw_full_order(v))
        self.gen_is_alpha = self.g == self.alpha
        self.gname = "α" if self.gen_is_alpha else "g"

        # exp / log tables: exp[k] = g^k, log[g^k] = k.   Multiplication = add logs.
        self.exp = [0] * (q - 1)
        self.log = [None] * q
        e = 1
        for k in range(q - 1):
            self.exp[k] = e
            self.log[e] = k
            e = self._raw_mul(e, self.g)

    # ── raw polynomial arithmetic (only used while building the tables) ──
    def _raw_mul(self, a, b):
        prod = pmul(list(self.coeffs[a]), list(self.coeffs[b]), self.p)
        return coeffs_to_int(pmod(prod, self.modulus, self.p), self.p)

    def _raw_pow(self, a, e):
        r = 1
        while e:
            if e & 1:
                r = self._raw_mul(r, a)
            a = self._raw_mul(a, a)
            e >>= 1
        return r

    def _raw_full_order(self, v):
        return v != 0 and all(self._raw_pow(v, (self.q - 1) // r) != 1 for r in factorize(self.q - 1))

    # ── field operations ──
    def add(self, a, b):
        p = self.p
        if self.n == 1:
            return (a + b) % p
        return sum(((x + y) % p) * w for x, y, w in zip(self.coeffs[a], self.coeffs[b], self._pw))

    def neg(self, a):
        p = self.p
        return sum(((-x) % p) * w for x, w in zip(self.coeffs[a], self._pw))

    def sub(self, a, b):
        return self.add(a, self.neg(b))

    def mul(self, a, b):
        if a == 0 or b == 0:
            return 0
        return self.exp[(self.log[a] + self.log[b]) % (self.q - 1)]

    def inv(self, a):
        if a == 0:
            raise ZeroDivisionError("0 has no multiplicative inverse")
        return self.exp[(-self.log[a]) % (self.q - 1)]

    def div(self, a, b):
        return self.mul(a, self.inv(b))

    def pow(self, a, k: int):
        if a == 0:
            if k == 0:
                return 1
            if k < 0:
                raise ZeroDivisionError("0 to a negative power")
            return 0
        return self.exp[(self.log[a] * k) % (self.q - 1)]

    def order(self, a):
        if a == 0:
            return None
        return (self.q - 1) // math.gcd(self.log[a], self.q - 1)

    def is_generator(self, a):
        return a != 0 and self.order(a) == self.q - 1

    def frobenius(self, a, i=1):
        return self.pow(a, self.p ** i)

    def conjugates(self, a):
        out, c = [a], self.frobenius(a)
        while c != a:
            out.append(c)
            c = self.frobenius(c)
        return out

    def minimal_poly(self, a):
        """∏ (X − c) over the conjugates of a; coefficients land in GF(p)."""
        poly = [1]
        for c in self.conjugates(a):
            new = [0] * (len(poly) + 1)
            for i, coef in enumerate(poly):
                new[i + 1] = self.add(new[i + 1], coef)
                new[i] = self.add(new[i], self.mul(self.neg(c), coef))
            poly = new
        assert all(x < self.p for x in poly), "minimal polynomial left the prime field"
        return poly

    def trace(self, a):
        s = 0
        for i in range(self.n):
            s = self.add(s, self.frobenius(a, i))
        return s

    def norm(self, a):
        return self.pow(a, (self.q - 1) // (self.p - 1)) if a else 0

    def subfield_degrees(self):
        return [d for d in range(1, self.n + 1) if self.n % d == 0]

    def smallest_subfield(self, a):
        return next(d for d in self.subfield_degrees() if self.pow(a, self.p ** d) == a)

    def is_aes(self):
        return self.p == 2 and self.n == 8 and tuple(self.modulus) == AES_MODULUS

    # ── formatting ──
    def fmt(self, a, style="int", compact=True):
        if style == "hex" and self.p == 2:
            return f"0x{a:0{max(1, (self.n + 3) // 4)}x}"
        if style == "poly":
            return poly_to_str(self.coeffs[a], "α", compact)
        if style == "vec":
            return "(" + " ".join(map(str, reversed(self.coeffs[a]))) + ")" if self.n > 1 else str(a)
        if style == "power":
            return self.power_str(a)
        return str(a)

    def power_str(self, a):
        if a == 0:
            return "0"
        k = self.log[a]
        return "1" if k == 0 else self.gname if k == 1 else self.gname + sup(k)

    def describe(self, a):
        parts = [str(a)]
        for st in (("hex",) if self.p == 2 else ()) + ("poly", "vec", "power"):
            s = self.fmt(a, st, compact=False)
            if s not in parts:
                parts.append(s)
        return "  =  ".join(parts)

    def modulus_str(self):
        return poly_to_str(self.modulus, "x")

    # ── parsing ──
    def parse(self, text: str) -> int:
        raw = str(text).strip()
        if not raw:
            raise ValueError("empty input")
        vec = re.fullmatch(r"[\(\[]\s*(\d+(?:[\s,;]+\d+)*)\s*[\)\]]", raw)
        if vec:
            digits = [int(d) for d in re.split(r"[\s,;]+", vec.group(1))]
            if len(digits) > self.n or any(d >= self.p for d in digits):
                raise ValueError(f"vector needs ≤ {self.n} digits, each < {self.p}")
            return coeffs_to_int(list(reversed(digits)), self.p)
        s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group().translate(UNSUP), raw)
        s = s.lower().replace(" ", "").replace("**", "^").replace("·", "*").replace("−", "-")
        s = s.replace("alpha", "x").replace("α", "x")
        if re.fullmatch(r"0x[0-9a-f]+", s):
            return self._check(int(s, 16))
        if re.fullmatch(r"0b[01]+", s):
            return self._check(int(s, 2))
        if re.fullmatch(r"[+-]?\d+", s):
            v = int(s)
            return self.neg(self._check(-v)) if v < 0 else self._check(v)
        m = re.fullmatch(r"g(?:\^\(?(-?\d+)\)?)?", s)
        if m:
            return self.pow(self.g, int(m.group(1)) if m.group(1) else 1)
        # polynomial in α with integer coefficients, any degree (reduced mod f)
        total = 0
        for e, c in _parse_terms(s).items():
            total = self.add(total, self.mul(c % self.p, self.pow(self.alpha, e)))
        return total

    def _check(self, v):
        if not 0 <= v < self.q:
            raise ValueError(f"{v} is not an element label (labels run 0 … {self.q - 1})")
        return v

    def parse_field_poly(self, text: str) -> dict:
        """'x^3 + 5x + 2' with coefficients given as element labels -> {exp: element}."""
        s = text.lower().replace(" ", "").replace("**", "^").replace("·", "*").replace("−", "-")
        s = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "^" + m.group().translate(UNSUP), s)
        out = {}
        for e, c in _parse_terms(s).items():
            el = self.neg(self._check(-c)) if c < 0 else self._check(c % self.q if c >= self.q else c)
            out[e] = self.add(out.get(e, 0), el)
        return out

    def eval_field_poly(self, P: dict, x: int) -> int:
        total = 0
        for e, c in P.items():
            total = self.add(total, self.mul(c, self.pow(x, e)))
        return total

    # ── step-by-step explanations ──
    def mul_steps(self, a, b):
        p, n, f = self.p, self.n, self.modulus
        A, B = list(self.coeffs[a]), list(self.coeffs[b])
        lines = [f"a(α) = {poly_to_str(A, 'α')}",
                 f"b(α) = {poly_to_str(B, 'α')}"]
        prod = pmul(ptrim(A), ptrim(B), p)
        lines.append(f"a·b before reduction (coefficients mod {p}):")
        lines.append(f"     {poly_to_str(prod, 'α')}")
        if len(prod) - 1 < n:
            lines.append(f"degree < {n}: nothing to reduce.")
        else:
            lines.append(f"reduce with f(α) = {poly_to_str(f, 'α')} = 0, i.e. "
                         f"α{sup(n)} = {poly_to_str([(-c) % p for c in f[:-1]], 'α')}:")
            r = list(prod)
            for k in range(len(r) - 1, n - 1, -1):
                c = r[k]
                if not c:
                    continue
                shift = k - n
                term = ("" if c == 1 else str(c)) + ("" if shift == 0 else ("α" if shift == 1 else "α" + sup(shift)))
                for j, y in enumerate(f):
                    r[shift + j] = (r[shift + j] - c * y) % p
                lines.append(f"   − {term or '1'}·f(α)  →  {poly_to_str(r, 'α')}")
        lines.append(f"a·b = {self.describe(self.mul(a, b))}")
        return lines

    def inverse_steps(self, a):
        """Extended Euclid on f and a(x) — the textbook way to invert (e.g. in AES)."""
        p = self.p
        if a == 0:
            return ["0 has no inverse."]
        r0, r1 = list(self.modulus), ptrim(self.coeffs[a])
        s0, s1 = [], [1]
        lines = ["Invariant: sᵢ(x)·a(x) ≡ rᵢ(x)  (mod f).  Start r₀ = f, r₁ = a."]
        while r1:
            quo, rem = pdivmod(r0, r1, p)
            lines.append(f"  {poly_to_str(r0)} = ({poly_to_str(quo)})·({poly_to_str(r1)}) + {poly_to_str(rem)}")
            s0, s1 = s1, psub(s0, pmul(quo, s1, p), p)
            r0, r1 = r1, rem
        c = r0[0]
        inv_c = pow(c, -1, p)
        res = pmod([(x * inv_c) % p for x in s0], self.modulus, p)
        lines.append(f"gcd = {c} (a nonzero constant ⇒ invertible).  s(x)·a(x) ≡ {c},")
        lines.append(f"so a⁻¹ = {c}⁻¹·s(x) = {poly_to_str(res, 'α')}")
        val = coeffs_to_int(res, p)
        lines.append(f"a⁻¹ = {self.describe(val)}   (check: a·a⁻¹ = {self.mul(a, val)})")
        return lines


# ═════════════════════════════════════════════════════════════════════════════
#  Maps x ↦ f(x) that can be drawn
# ═════════════════════════════════════════════════════════════════════════════
OPS = [
    ("mul",    "Multiply        x ↦ a·x",         ("a",)),
    ("add",    "Add             x ↦ x + a",       ("a",)),
    ("affine", "Affine          x ↦ a·x + b",     ("a", "b")),
    ("pow",    "Power           x ↦ xᵏ",          ("k",)),
    ("inv",    "Inverse         x ↦ x⁻¹ (0↦0)",   ()),
    ("frob",   "Frobenius       x ↦ xᵖ",          ()),
    ("poly",   "Polynomial      x ↦ P(x)",        ("P",)),
    ("exp",    "Exponential     i ↦ gⁱ",          ()),
    ("dlog",   "Discrete log    x ↦ log_g x",     ()),
    ("sbox",   "AES S-box       (GF(2⁸) only)",   ()),
]
OP_PARAMS = {k: v for k, _, v in OPS}


def rotl8(b, r):
    return ((b << r) | (b >> (8 - r))) & 0xFF


def aes_sbox(F: FiniteField, x: int) -> int:
    b = F.inv(x) if x else 0
    return b ^ rotl8(b, 1) ^ rotl8(b, 2) ^ rotl8(b, 3) ^ rotl8(b, 4) ^ 0x63


def build_map(F: FiniteField, op: str, a=None, b=None, k=None, P=None):
    q = F.q
    if op == "mul":
        return [F.mul(a, x) for x in range(q)]
    if op == "add":
        return [F.add(x, a) for x in range(q)]
    if op == "affine":
        return [F.add(F.mul(a, x), b) for x in range(q)]
    if op == "pow":
        return [F.pow(x, k) if (x or k >= 0) else 0 for x in range(q)]
    if op == "inv":
        return [F.inv(x) if x else 0 for x in range(q)]
    if op == "frob":
        return [F.frobenius(x) for x in range(q)]
    if op == "poly":
        return [F.eval_field_poly(P, x) for x in range(q)]
    if op == "exp":
        return [F.exp[x % (q - 1)] for x in range(q)]
    if op == "dlog":
        return [F.log[x] if x else 0 for x in range(q)]
    if op == "sbox":
        if not F.is_aes():
            raise ValueError("The AES S-box lives in GF(2⁸) with modulus x⁸+x⁴+x³+x+1. "
                             "Use “Load AES field” (Field or Crypto tab).")
        return [aes_sbox(F, x) for x in range(q)]
    raise ValueError(f"unknown map {op}")


def iterate_map(m, times):
    out = list(range(len(m)))
    for _ in range(times):
        out = [m[x] for x in out]
    return out


def analyze_map(m):
    q = len(m)
    bij = len(set(m)) == q
    fixed = [x for x in range(q) if m[x] == x]
    # weakly-connected components of the functional graph (= cycles for a permutation)
    parent = list(range(q))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for x in range(q):
        ra, rb = find(x), find(m[x])
        if ra != rb:
            parent[ra] = rb
    roots, comp = {}, [0] * q
    for x in range(q):
        comp[x] = roots.setdefault(find(x), len(roots))
    # the cycles inside the functional graph
    state, cycles = [0] * q, []
    for s in range(q):
        path, x = [], s
        while state[x] == 0:
            state[x] = 1
            path.append(x)
            x = m[x]
        if state[x] == 1:
            cycles.append(path[path.index(x):])
        for y in path:
            state[y] = 2
    cyc_type = {}
    for c in cycles:
        cyc_type[len(c)] = cyc_type.get(len(c), 0) + 1
    return {"bijective": bij, "fixed": fixed, "image": len(set(m)), "comp": comp,
            "n_comp": len(roots), "cycles": cycles, "cycle_type": dict(sorted(cyc_type.items()))}


def op_note(F, op, a=None, b=None, k=None):
    q, p = F.q, F.p
    if op == "mul":
        if a == 0:
            return "a = 0 sends everything to 0 — not a bijection."
        o = F.order(a)
        return (f"Multiplying by a permutes GF({q})*; every nonzero orbit has length ord(a) = {o}, "
                f"so there are {(q - 1) // o} of them. In the power layout this is a rotation by "
                f"log(a) = {F.log[a]} steps. Choosing a generator gives one big cycle.")
    if op == "add":
        return ("Translation. The Frobenius-free part of the structure: every orbit has length "
                f"{'1' if a == 0 else p} (= characteristic). In the grid layout it is a pure shift.")
    if op == "affine":
        return ("Affine maps a·x+b are bijective iff a ≠ 0. They are linear-ish, which is why a cipher "
                "built only from them is easy to break — AES adds the nonlinear x⁻¹.")
    if op == "pow":
        d = math.gcd(k, q - 1)
        verdict = "a bijection" if d == 1 else f"{d}-to-1 on GF({q})* (NOT a bijection)"
        return (f"gcd(k, q−1) = gcd({k}, {q - 1}) = {d}, so x ↦ xᵏ is {verdict}. Bijective power maps are "
                "the idea behind exponent ciphers (Pohlig–Hellman cipher, RSA in ℤ/N). k = q−2 gives x⁻¹, "
                f"k = p = {p} gives Frobenius, k = q gives the identity.")
    if op == "inv":
        return ("An involution: every cycle has length 1 or 2. Fixed points are 0, 1"
                + (" and −1" if p > 2 else "") + ". AES uses exactly this map as its only nonlinear step.")
    if op == "frob":
        return (f"Frobenius: (x+y)ᵖ = xᵖ + yᵖ, so it is a field automorphism. Its order is n = {F.n}; its fixed "
                f"points are exactly the prime field GF({p}); orbits are the sets of conjugates.")
    if op == "poly":
        return ("A polynomial that permutes the field is a 'permutation polynomial'. Every function "
                "GF(q)→GF(q) is a polynomial of degree < q (Lagrange interpolation).")
    if op == "exp":
        return ("The easy direction of Diffie–Hellman: k ↦ gᵏ (k read as an integer label, mod q−1). Try the "
                "integer layout: the arrows look random. That is the point — inverting it is the discrete-log problem.")
    if op == "dlog":
        return ("The hard direction: x ↦ log_g(x) as an integer (0 ↦ 0 by convention). Easy here only because "
                "the field is tiny and we stored a log table; for q ≈ 2²⁵⁶ no such table can exist.")
    if op == "sbox":
        return ("AES SubBytes: x ↦ A·x⁻¹ + 0x63 where A is a fixed GF(2)-linear map. A permutation with "
                "no fixed points and no 'opposite' fixed points (S(x) ≠ x ⊕ 0xff).")
    return ""


# ═════════════════════════════════════════════════════════════════════════════
#  Colour helpers
# ═════════════════════════════════════════════════════════════════════════════
THEMES = {
    "light": dict(bg="#ffffff", fg="#2b2b2b", edge="#1f6fd1", accent="#e8590c", circle="#c8c8c8",
                  label="#3a3a3a", muted="#9a9a9a", mark="#c2255c"),
    "dark":  dict(bg="#121418", fg="#dcdcdc", edge="#4ea1ff", accent="#ff922b", circle="#3d4148",
                  label="#c9c9c9", muted="#6b6f76", mark="#f06595"),
    "paper": dict(bg="#f6f1e4", fg="#3b3024", edge="#7a4b2a", accent="#b5361b", circle="#cbbf9f",
                  label="#4a3d2c", muted="#a8997a", mark="#2b6f77"),
}


PALETTE = ["#1f6fd1", "#d63a2f", "#2a9d3c", "#8a4fc8", "#e07b00", "#0f9fb0", "#8c564b", "#d4459b",
           "#6b7d10", "#5c6b80"]
PALETTE_DARK = ["#4ea1ff", "#ff6b5e", "#4fd16a", "#b48cff", "#ffa94d", "#3fd0e0", "#c99a7a", "#ff7ec8",
                "#c3d64a", "#9aa8bb"]


def hsv_hex(h, s=0.72, v=0.88):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def blend(c1, c2, t):
    """Mix colour c1 toward c2 by t (0 → c1, 1 → c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# ═════════════════════════════════════════════════════════════════════════════
#  GUI
# ═════════════════════════════════════════════════════════════════════════════
LAYOUTS = {"power": "Circle — power order (0 at centre)",
           "integer": "Circle — integer order",
           "grid": "Grid — coefficient vector"}
CURVES = {"straight": "Straight", "bent": "Bent (shows direction)", "hub": "Pulled to centre"}
EDGE_COLORS = {"single": "Single colour", "component": "By cycle / component", "source": "Rainbow by position",
               "length": "By edge length", "order": "By order of x"}
POINT_COLORS = {"plain": "Plain", "order": "By multiplicative order", "log": "By discrete log",
                "primitive": "Highlight generators", "subfield": "By smallest subfield"}
LABEL_FMTS = {"int": "Integer", "hex": "Hex (p = 2)", "poly": "Polynomial", "vec": "Vector", "power": "Power of g"}
PRESETS = [("GF(7)", 7, 1), ("GF(9)", 3, 2), ("GF(16)", 2, 4), ("GF(25)", 5, 2), ("GF(27)", 3, 3),
           ("GF(64)", 2, 6), ("GF(121)", 11, 2)]
PRIMES = [x for x in range(2, 200) if is_prime(x)]


class Explorer:
    def __init__(self, root, field: FiniteField, opts):
        self.root = root
        self.F = field
        self.mapping, self.analysis, self.map_desc = list(range(field.q)), {}, ""
        self.positions, self.out_dirs, self.layout_index = [], [], []
        self.center, self.R, self.pr = (0, 0), 1, 3
        self.selected, self.sel_orbit = None, []
        self.marks = {}
        self._redraw_job = self._anim_job = self._prog_job = None
        self.sweeping = False
        self._modulus_lookup = {}
        self._build_vars(opts)
        self._build_ui()
        self.on_field_changed(reset_params=False)

    # ── state ──────────────────────────────────────────────────────────────
    def _build_vars(self, o):
        S, I, D, B = tk.StringVar, tk.IntVar, tk.DoubleVar, tk.BooleanVar
        F = self.F
        self.v_p, self.v_n = S(value=str(F.p)), S(value=str(F.n))
        self.v_mod = S()
        self.v_op = S(value=o.op)
        self.v_a, self.v_b, self.v_k = S(value=o.a), S(value=o.b), S(value=o.k)
        self.v_P = S(value=o.P)
        self.v_iter = I(value=1)
        self.v_layout = S(value=o.layout)
        self.v_curve, self.v_bend = S(value="straight"), D(value=0.25)
        self.v_arrows, self.v_arrow_scale = B(value=True), D(value=1.0)
        self.v_ecolor, self.v_width, self.v_opacity = S(value="component"), D(value=1.3), D(value=0.9)
        self.v_pcolor, self.v_psize = S(value="plain"), D(value=1.0)
        self.v_labels, self.v_lfmt, self.v_lsize = B(value=F.q <= 40), S(value="int"), I(value=9)
        self.v_loops, self.v_fixed, self.v_circle, self.v_title = B(value=True), B(value=True), B(value=True), B(value=True)
        self.v_theme = S(value=o.theme)
        self.v_delay = I(value=350)
        self.v_dh_g, self.v_dh_a, self.v_dh_b = S(value="g"), S(value="6"), S(value="11")
        self.v_dh_m, self.v_dh_r, self.v_dh_mark = S(value="5"), S(value="4"), B(value=True)
        self.v_aes_x = S(value="0x53")
        self.v_ca, self.v_cb, self.v_ck = S(value="g^3"), S(value="x+1"), S(value="5")
        for v in (self.v_curve, self.v_bend, self.v_arrows, self.v_arrow_scale, self.v_ecolor, self.v_width,
                  self.v_opacity, self.v_pcolor, self.v_psize, self.v_labels, self.v_lfmt, self.v_lsize,
                  self.v_loops, self.v_fixed, self.v_circle, self.v_title, self.v_theme, self.v_layout):
            v.trace_add("write", lambda *_: self.schedule_redraw())

    # ── layout of the window ───────────────────────────────────────────────
    def _build_ui(self):
        r = self.root
        r.geometry("1360x900")
        r.minsize(980, 640)
        outer = ttk.PanedWindow(r, orient="horizontal")
        outer.pack(fill="both", expand=True)
        left = ttk.Frame(outer)
        outer.add(left, weight=3)
        self.canvas = tk.Canvas(left, highlightthickness=0, bg="white", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(left, anchor="w", padding=(8, 4))
        self.status.pack(fill="x")
        right = ttk.PanedWindow(outer, orient="vertical")
        outer.add(right, weight=1)
        self.nb = ttk.Notebook(right, width=440)
        right.add(self.nb, weight=3)
        insp = ttk.LabelFrame(right, text=" Inspector — click a point ", padding=4)
        right.add(insp, weight=2)
        self.t_insp = self._textbox(insp, 12)

        self._tab_field()
        self._tab_map()
        self._tab_style()
        self._tab_calc()
        self._tab_crypto()

        c = self.canvas
        c.bind("<Configure>", lambda e: self.schedule_redraw())
        c.bind("<Motion>", self.on_motion)
        c.bind("<Button-1>", self.on_click)
        c.bind("<Left>", lambda e: self.step_param(-1))
        c.bind("<Right>", lambda e: self.step_param(+1))
        c.bind("<Up>", lambda e: self.v_iter.set(min(64, self.v_iter.get() + 1)) or self.recompute())
        c.bind("<Down>", lambda e: self.v_iter.set(max(1, self.v_iter.get() - 1)) or self.recompute())
        c.bind("<space>", lambda e: self.toggle_sweep())
        c.bind("<Escape>", lambda e: self.select(None))
        r.bind("<Control-s>", lambda e: self.save_image())

    def _textbox(self, parent, height):
        fr = ttk.Frame(parent)
        fr.pack(fill="both", expand=True)
        t = tk.Text(fr, height=height, wrap="word", font="TkFixedFont", relief="flat", padx=6, pady=4)
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        return t

    @staticmethod
    def _set_text(t, s):
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("1.0", s)
        t.configure(state="disabled")

    def _tab_field(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Field")
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Label(row, text="p (prime)").pack(side="left")
        ttk.Combobox(row, textvariable=self.v_p, values=PRIMES, width=5).pack(side="left", padx=(4, 10))
        ttk.Label(row, text="n").pack(side="left")
        ttk.Spinbox(row, from_=1, to=12, textvariable=self.v_n, width=4).pack(side="left", padx=(4, 10))
        ttk.Button(row, text="Build GF(pⁿ)", command=self.on_build_pn).pack(side="left")
        self.l_q = ttk.Label(row, text="")
        self.l_q.pack(side="left", padx=8)

        ttk.Label(tab, text="Modulus f(x) — pick one, or type your own and press Enter:").pack(anchor="w", pady=(10, 2))
        self.cb_mod = ttk.Combobox(tab, textvariable=self.v_mod, width=48)
        self.cb_mod.pack(fill="x")
        self.cb_mod.bind("<<ComboboxSelected>>", lambda e: self.on_modulus())
        self.cb_mod.bind("<Return>", lambda e: self.on_modulus())

        pre = ttk.Frame(tab)
        pre.pack(fill="x", pady=(10, 0))
        for i, (name, p, n) in enumerate(PRESETS):
            ttk.Button(pre, text=name, width=7, command=lambda p=p, n=n: self.set_field(p, n)).grid(
                row=i // 4, column=i % 4, padx=1, pady=1, sticky="ew")
        ttk.Button(pre, text="AES GF(2⁸)", command=self.load_aes).grid(row=1, column=3, padx=1, pady=1, sticky="ew")
        ttk.Button(pre, text="🎲 Random", command=self.random_field).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(pre, text="+ table", command=lambda: self.open_table("add")).grid(row=2, column=2, sticky="ew")
        ttk.Button(pre, text="× table", command=lambda: self.open_table("mul")).grid(row=2, column=3, sticky="ew")
        for i in range(4):
            pre.columnconfigure(i, weight=1)
        ttk.Separator(tab).pack(fill="x", pady=8)
        self.t_field = self._textbox(tab, 10)

    def _tab_map(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Map")
        ops = ttk.LabelFrame(tab, text=" Draw an arrow x → f(x) for every element ", padding=4)
        ops.pack(fill="x")
        for i, (key, label, _) in enumerate(OPS):
            ttk.Radiobutton(ops, text=label, value=key, variable=self.v_op, command=self.on_op).grid(
                row=i // 2, column=i % 2, sticky="w", padx=2)
        par = ttk.LabelFrame(tab, text=" Parameters (Enter to apply) ", padding=4)
        par.pack(fill="x", pady=6)
        self.param_entries = {}
        specs = [("a", self.v_a, "element"), ("b", self.v_b, "element"),
                 ("k", self.v_k, "integer / q-2 …"), ("P", self.v_P, "e.g. x^3 + 2x + 1")]
        for r, (name, var, hint) in enumerate(specs):
            ttk.Label(par, text=f"{name} =").grid(row=r, column=0, sticky="e")
            e = ttk.Entry(par, textvariable=var, width=20)
            e.grid(row=r, column=1, sticky="ew", padx=4, pady=1)
            e.bind("<Return>", lambda ev: self.recompute())
            e.bind("<FocusOut>", lambda ev: self.recompute())
            self.param_entries[name] = e
            ttk.Label(par, text=hint, foreground="#888").grid(row=r, column=2, sticky="w")
        btns = ttk.Frame(par)
        btns.grid(row=0, column=3, rowspan=2, padx=4)
        ttk.Button(btns, text="◀", width=2, command=lambda: self.step_param(-1)).pack(side="left")
        ttk.Button(btns, text="▶", width=2, command=lambda: self.step_param(+1)).pack(side="left")
        ttk.Button(btns, text="🎲", width=3, command=self.random_param).pack(side="left")
        par.columnconfigure(1, weight=1)
        ri = ttk.Frame(par)
        ri.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(ri, text="apply the map m times, m =").pack(side="left")
        sp = ttk.Spinbox(ri, from_=1, to=64, textvariable=self.v_iter, width=4, command=self.recompute)
        sp.pack(side="left", padx=4)
        sp.bind("<Return>", lambda e: self.recompute())

        an = ttk.Frame(tab)
        an.pack(fill="x")
        self.b_sweep = ttk.Button(an, text="▶ Sweep parameter", command=self.toggle_sweep)
        self.b_sweep.pack(side="left")
        ttk.Button(an, text="✎ Draw arrows one by one", command=lambda: self.redraw(progressive=True)).pack(side="left", padx=4)
        ttk.Label(an, text="speed").pack(side="left", padx=(6, 0))
        ttk.Scale(an, from_=1200, to=20, variable=self.v_delay, orient="horizontal", length=90).pack(side="left")
        ttk.Label(tab, foreground="#777", wraplength=420, justify="left",
                  text="Inputs: 13 · 0x1b · 0b1101 · x^3+x+1 · α³+1 · g^7 · (1 1 0 1) · -5.   "
                       "Canvas keys: ←/→ step a or k, ↑/↓ iterations, space = sweep, Esc = deselect.").pack(anchor="w", pady=4)
        self.t_map = self._textbox(tab, 8)

    def _tab_style(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Style")
        g = ttk.Frame(tab)
        g.pack(fill="x")
        row = 0

        def add(label, widget):
            nonlocal row
            ttk.Label(g, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="ew", pady=2, padx=(6, 0))
            row += 1

        def combo(var, choices):
            cb = ttk.Combobox(g, state="readonly", values=list(choices.values()), width=28)
            cb.set(choices[var.get()])
            cb.bind("<<ComboboxSelected>>", lambda e: var.set(
                next(k for k, v in choices.items() if v == cb.get())))
            var.trace_add("write", lambda *_: cb.set(choices.get(var.get(), cb.get())))
            return cb

        def scale(var, lo, hi):
            return ttk.Scale(g, from_=lo, to=hi, variable=var, orient="horizontal")

        add("Point layout", combo(self.v_layout, LAYOUTS))
        add("Edge shape", combo(self.v_curve, CURVES))
        add("  bend amount", scale(self.v_bend, -0.8, 0.8))
        add("Edge colour", combo(self.v_ecolor, EDGE_COLORS))
        add("  line width", scale(self.v_width, 0.3, 5))
        add("  opacity", scale(self.v_opacity, 0.08, 1))
        add("  arrowhead size", scale(self.v_arrow_scale, 0.3, 3))
        add("Point colour", combo(self.v_pcolor, POINT_COLORS))
        add("  point size", scale(self.v_psize, 0.2, 3.5))
        add("Label format", combo(self.v_lfmt, LABEL_FMTS))
        add("  label font size", ttk.Spinbox(g, from_=6, to=22, textvariable=self.v_lsize, width=5))
        add("Theme", combo(self.v_theme, {k: k.capitalize() for k in THEMES}))
        g.columnconfigure(1, weight=1)
        chk = ttk.Frame(tab)
        chk.pack(fill="x", pady=6)
        for i, (txt, var) in enumerate([("Arrowheads", self.v_arrows), ("Labels", self.v_labels),
                                        ("Self-loops (fixed points)", self.v_loops), ("Ring fixed points", self.v_fixed),
                                        ("Outline circle", self.v_circle), ("Title on canvas", self.v_title)]):
            ttk.Checkbutton(chk, text=txt, variable=var).grid(row=i // 2, column=i % 2, sticky="w", padx=2)
        ex = ttk.LabelFrame(tab, text=" Export ", padding=4)
        ex.pack(fill="x", pady=6)
        ttk.Button(ex, text="Save picture (.svg / .eps)…", command=self.save_image).pack(side="left")
        ttk.Button(ex, text="Save map as CSV…", command=self.save_csv).pack(side="left", padx=4)
        ttk.Label(tab, foreground="#777", wraplength=420, justify="left",
                  text="Tip: ‘power order’ puts gᵏ at angle k·360°/(q−1) — multiplication becomes rotation and "
                       "xᵏ becomes the classic ‘times-table’ chord pattern. ‘Grid’ places α-coefficients on two axes — "
                       "addition becomes translation.").pack(anchor="w", pady=4)

    def _tab_calc(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Calculator")
        g = ttk.Frame(tab)
        g.pack(fill="x")
        for r, (name, var) in enumerate([("a", self.v_ca), ("b", self.v_cb), ("k", self.v_ck)]):
            ttk.Label(g, text=f"{name} =").grid(row=r, column=0, sticky="e")
            e = ttk.Entry(g, textvariable=var)
            e.grid(row=r, column=1, sticky="ew", padx=4, pady=1)
            e.bind("<Return>", lambda ev: self.calculate())
        g.columnconfigure(1, weight=1)
        b = ttk.Frame(tab)
        b.pack(fill="x", pady=4)
        ttk.Button(b, text="Calculate", command=self.calculate).pack(side="left")
        ttk.Button(b, text="Mark a, b on canvas", command=self.mark_calc).pack(side="left", padx=4)
        self.t_calc = self._textbox(tab, 20)

    def _tab_crypto(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Crypto")
        dh = ttk.LabelFrame(tab, text=" Diffie–Hellman & ElGamal in GF(q)* ", padding=4)
        dh.pack(fill="x")
        specs = [("generator g", self.v_dh_g), ("Alice secret a", self.v_dh_a), ("Bob secret b", self.v_dh_b),
                 ("message m", self.v_dh_m), ("ephemeral r", self.v_dh_r)]
        for r, (name, var) in enumerate(specs):
            ttk.Label(dh, text=name).grid(row=r, column=0, sticky="w")
            e = ttk.Entry(dh, textvariable=var, width=18)
            e.grid(row=r, column=1, sticky="ew", padx=4, pady=1)
            e.bind("<Return>", lambda ev: self.run_dh())
        dh.columnconfigure(1, weight=1)
        bb = ttk.Frame(dh)
        bb.grid(row=0, column=2, rowspan=5, sticky="n", padx=4)
        ttk.Button(bb, text="Run", command=self.run_dh).pack(fill="x")
        ttk.Button(bb, text="🎲 secrets", command=self.random_secrets).pack(fill="x", pady=2)
        ttk.Button(bb, text="Show k ↦ gᵏ", command=lambda: self.show_op("exp", "integer")).pack(fill="x")
        ttk.Checkbutton(bb, text="mark A, B, K", variable=self.v_dh_mark, command=self.run_dh).pack(anchor="w")

        aes = ttk.LabelFrame(tab, text=" AES S-box (GF(2⁸), f = x⁸+x⁴+x³+x+1) ", padding=4)
        aes.pack(fill="x", pady=6)
        ttk.Button(aes, text="Load AES field", command=self.load_aes).grid(row=0, column=0, sticky="ew")
        ttk.Label(aes, text="  x =").grid(row=0, column=1)
        e = ttk.Entry(aes, textvariable=self.v_aes_x, width=8)
        e.grid(row=0, column=2)
        e.bind("<Return>", lambda ev: self.aes_details())
        ttk.Button(aes, text="S(x) step by step", command=self.aes_details).grid(row=0, column=3, padx=4)
        ttk.Button(aes, text="S-box table", command=self.aes_table).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(aes, text="Draw S-box map", command=lambda: self.show_op("sbox", "integer")).grid(
            row=1, column=1, columnspan=3, sticky="w", padx=4)
        self.t_crypto = self._textbox(tab, 16)

    # ── field management ──────────────────────────────────────────────────
    def set_field(self, p, n, modulus=None):
        try:
            if not is_prime(p):
                raise ValueError(f"p = {p} is not prime")
            if p ** n > MAX_Q:
                raise ValueError(f"q = {p}^{n} = {p ** n} exceeds the limit of {MAX_Q} elements")
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            self.F = FiniteField(p, n, modulus)
        except ValueError as exc:
            messagebox.showerror("Can't build that field", str(exc))
            return False
        finally:
            self.root.config(cursor="")
        self.v_p.set(str(p))
        self.v_n.set(str(n))
        self.v_labels.set(self.F.q <= 40)
        self.on_field_changed(reset_params=True)
        return True

    def on_build_pn(self):
        try:
            p, n = int(self.v_p.get()), int(self.v_n.get())
        except ValueError:
            messagebox.showerror("Bad input", "p and n must be integers")
            return
        self.set_field(p, n)

    def on_modulus(self):
        F = self.F
        text = self.v_mod.get()
        coeffs = self._modulus_lookup.get(text)
        if coeffs is None:
            try:
                coeffs = parse_integer_poly(text, F.p)
            except ValueError as exc:
                messagebox.showerror("Bad modulus", str(exc))
                return
        self.set_field(F.p, F.n, list(coeffs))

    def load_aes(self):
        if self.set_field(2, 8, list(AES_MODULUS)):
            self.v_lfmt.set("hex")

    def random_field(self):
        while True:
            p = random.choice([2, 3, 5, 7, 11, 13])
            n = random.randint(1, 6)
            if 3 <= p ** n <= 512:
                break
        mod = list(random.choice(irreducible_polys(p, n))[0])
        if self.set_field(p, n, mod):
            self.v_a.set(str(random.randint(1, self.F.q - 1)))
            self.recompute()

    def on_field_changed(self, reset_params=True):
        F = self.F
        self.root.title(f"Galois Field Explorer — GF({F.q})")
        self.l_q.configure(text=f"q = {F.q}")
        polys = irreducible_polys(F.p, F.n)
        self._modulus_lookup = {}
        values = []
        for c, prim in polys:
            s = poly_to_str(c, "x") + ("   ★ primitive" if prim else "")
            self._modulus_lookup[s] = c
            values.append(s)
        self.cb_mod.configure(values=values)
        self.v_mod.set(F.modulus_str() + ("   ★ primitive" if F.modulus_is_primitive else ""))
        self._modulus_lookup.setdefault(self.v_mod.get(), tuple(F.modulus))
        if reset_params:
            self.v_a.set("g")
            self.v_b.set("1")
            self.v_k.set("2")
            self.v_P.set("x^3")
            self.v_iter.set(1)
        self.selected, self.marks = None, {}
        self._set_text(self.t_field, self.field_info())
        self._set_text(self.t_insp, "Click a point on the canvas to see everything about that element.")
        self.recompute()

    def field_info(self):
        F = self.F
        p, n, q = F.p, F.n, F.q
        L = []
        if n == 1:
            L.append(f"GF({p}) = ℤ/{p}ℤ: arithmetic mod {p}.")
            L.append(f"The modulus x − {(-F.modulus[0]) % p} just names α = {F.alpha}"
                     f"{', a primitive root mod ' + str(p) if F.gen_is_alpha else ''}.")
        else:
            L.append(f"GF({q}) = GF({p})[x] / (f),  f(x) = {F.modulus_str()}")
            sub = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
            top = f"c{str(n - 1).translate(sub)}"
            form = {2: "c₁α + c₀", 3: "c₂α² + c₁α + c₀"}.get(n, f"{top}α{sup(n - 1)} + … + c₁α + c₀")
            L.append(f"α = class of x, so f(α) = 0. Each element is {form} with every cᵢ in 0…{p - 1}.")
            L.append(f"Integer label = the base-{p} number {top}…c₁c₀ — handy, but it has no arithmetic meaning!")
            if F.modulus_is_primitive:
                L.append(f"f is PRIMITIVE ⇒ α itself generates GF({q})*.")
            else:
                L.append(f"f is irreducible but NOT primitive: ord(α) = {F.order(F.alpha)} < {q - 1}. "
                         f"Powers are written with g = {F.describe(F.g)}.")
        L.append("")
        L.append(f"characteristic p = {p}, degree n = {n}, q = {q} elements")
        L.append(f"GF({q})* is cyclic of order q−1 = {q - 1} = {factor_str(q - 1)}")
        L.append(f"generators (primitive elements): φ({q - 1}) = {euler_phi(q - 1)}")
        if n > 1:
            npr = sum(1 for _, pr in irreducible_polys(p, n) if pr)
            L.append(f"monic irreducible degree-{n} polys over GF({p}): {count_irreducible(p, n)} "
                     f"({npr} primitive) — any of them gives an isomorphic field, only labels change.")
        L.append("subfields: " + ", ".join(f"GF({p}{sup(d) if d > 1 else ''})" for d in F.subfield_degrees())
                 + "   (GF(pᵈ) ⊂ GF(pⁿ) iff d | n)")
        if q <= ELEMENT_TABLE_MAX_Q:
            L.append("")
            hx = F.p == 2
            L.append(f"{'int':>4} {'hex' if hx else '':>5} {'vector':>{2 * n + 1}}  {'power':>6}  {'ord':>4}  polynomial")
            order_by = [0] + F.exp
            for v in order_by:
                L.append(f"{v:>4} {F.fmt(v, 'hex') if hx else '':>5} {F.fmt(v, 'vec'):>{2 * n + 1}}  "
                         f"{F.power_str(v):>6}  {F.order(v) or '-':>4}  {F.fmt(v, 'poly', False)}")
            L.append("(listed in power order: each row is the previous one times " + F.gname + ")")
        return "\n".join(L)

    # ── map management ────────────────────────────────────────────────────
    def on_op(self):
        self.stop_sweep()
        self.recompute()

    def show_op(self, op, layout=None):
        self.v_op.set(op)
        if layout:
            self.v_layout.set(layout)
        self.nb.select(1)
        self.recompute()

    def current_params(self):
        F, op = self.F, self.v_op.get()
        need = OP_PARAMS[op]
        a = F.parse(self.v_a.get()) if "a" in need else None
        b = F.parse(self.v_b.get()) if "b" in need else None
        k = eval_int_expr(self.v_k.get(), {"q": F.q, "p": F.p, "n": F.n}) if "k" in need else None
        P = F.parse_field_poly(self.v_P.get()) if "P" in need else None
        return op, a, b, k, P

    def recompute(self):
        F = self.F
        op = self.v_op.get()
        for name, e in self.param_entries.items():
            e.configure(state="normal" if name in OP_PARAMS[op] else "disabled")
        try:
            op, a, b, k, P = self.current_params()
            base = build_map(F, op, a, b, k, P)
            m = max(1, int(self.v_iter.get()))
        except (ValueError, ZeroDivisionError, tk.TclError) as exc:
            self._set_text(self.t_map, f"⚠ {exc}")
            self.status.configure(text=f"⚠ {exc}")
            self.stop_sweep()
            return
        self.mapping = iterate_map(base, m)
        self.analysis = analyze_map(self.mapping)
        self.map_desc = self._formula(op, a, b, k, P) + (f"  iterated {m}×" if m > 1 else "")
        A = self.analysis
        L = [self.map_desc]
        for nm, val in (("a", a), ("b", b)):
            if val is not None:
                L.append(f"  {nm} = {F.describe(val)}   ord = {F.order(val) or '—'}")
        L.append("")
        L.append(f"bijective: {'yes — a permutation of the field' if A['bijective'] else 'no — image has ' + str(A['image']) + ' of ' + str(F.q) + ' elements'}")
        fx = A["fixed"]
        L.append(f"fixed points: {len(fx)}" + (f"  {{{', '.join(F.fmt(v, self._lab_fmt()) for v in fx[:16])}{', …' if len(fx) > 16 else ''}}}" if fx else ""))
        L.append("cycles: " + " + ".join(f"{c}×[{ln}]" for ln, c in A["cycle_type"].items())
                 + ("" if A["bijective"] else f"   ({A['n_comp']} components; other points fall into these cycles)"))
        L.append("")
        L.append(op_note(F, op, a, b, k))
        self._set_text(self.t_map, "\n".join(L))
        self.status.configure(text=f"GF({F.q}),  {self.map_desc}")
        if self.selected is not None:
            self.sel_orbit = self._orbit(self.selected)
            self.inspect(self.selected)
        self.schedule_redraw()

    def _formula(self, op, a, b, k, P):
        F = self.F
        f = lambda v: F.fmt(v, self._lab_fmt() if self._lab_fmt() != "vec" else "int")
        if op == "poly":
            terms = []
            for e, c in sorted(P.items(), reverse=True):
                if not c:
                    continue
                mono = "" if e == 0 else "x" if e == 1 else "x" + sup(e)
                terms.append(f(c) if e == 0 else mono if c == 1 else f"{f(c)}·{mono}")
            return "x ↦ " + (" + ".join(terms) or "0")
        return {"mul": lambda: f"x ↦ {f(a)}·x",
                "add": lambda: f"x ↦ x + {f(a)}",
                "affine": lambda: f"x ↦ {f(a)}·x + {f(b)}",
                "pow": lambda: f"x ↦ x^{k}" if k < 0 else f"x ↦ x{sup(k)}",
                "inv": lambda: "x ↦ x⁻¹",
                "frob": lambda: f"x ↦ x{sup(F.p)}  (Frobenius)",
                "exp": lambda: f"i ↦ {F.gname}ⁱ",
                "dlog": lambda: f"x ↦ log_{F.gname}(x)",
                "sbox": lambda: "x ↦ S-box(x)"}[op]()

    def _lab_fmt(self):
        fmt = self.v_lfmt.get()
        return "int" if fmt == "hex" and self.F.p != 2 else fmt

    def step_param(self, d):
        F, op = self.F, self.v_op.get()
        try:
            if op in ("mul", "affine"):
                a = F.parse(self.v_a.get())
                t = F.log[a] if a else -1
                self.v_a.set(str(F.exp[(t + d) % (F.q - 1)]))
            elif op == "add":
                self.v_a.set(str((F.parse(self.v_a.get()) + d) % F.q))
            elif op == "pow":
                k = eval_int_expr(self.v_k.get(), {"q": F.q, "p": F.p, "n": F.n})
                self.v_k.set(str((k + d) % F.q))
            else:
                self.v_iter.set((self.v_iter.get() - 1 + d) % 12 + 1)
        except ValueError:
            self.v_a.set("g")
        self.recompute()

    def random_param(self):
        F = self.F
        self.v_a.set(str(random.randint(1, F.q - 1)))
        self.v_b.set(str(random.randint(0, F.q - 1)))
        self.v_k.set(str(random.randint(2, F.q - 1)))
        self.recompute()

    # ── animation ─────────────────────────────────────────────────────────
    def toggle_sweep(self):
        if self.sweeping:
            self.stop_sweep()
        else:
            self.sweeping = True
            self.b_sweep.configure(text="⏸ Stop sweep")
            self._tick()

    def stop_sweep(self):
        self.sweeping = False
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        if hasattr(self, "b_sweep"):
            self.b_sweep.configure(text="▶ Sweep parameter")

    def _tick(self):
        if not self.sweeping:
            return
        self.step_param(+1)
        self._anim_job = self.root.after(max(20, int(self.v_delay.get())), self._tick)

    # ── geometry ──────────────────────────────────────────────────────────
    def compute_positions(self, W, H):
        F = self.F
        q, layout = F.q, self.v_layout.get()
        lab_room = 0
        if self.v_labels.get():
            longest = max(len(F.fmt(v, self._lab_fmt())) for v in range(q))
            lab_room = self.v_lsize.get() * (0.62 * longest + 0.8)
        top = 34 if self.v_title.get() else 14
        margin = 18 + lab_room
        pos, dirs, idx = [None] * q, [None] * q, [0] * q
        if layout in ("power", "integer"):
            cx, cy = W / 2, top / 2 + H / 2
            R = max(40, min(W, H - top) / 2 - margin)
            order = list(range(q)) if layout == "integer" else F.exp
            N = len(order)
            for t, v in enumerate(order):
                ang = -math.pi / 2 + 2 * math.pi * t / N
                pos[v] = (cx + R * math.cos(ang), cy + R * math.sin(ang))
                dirs[v] = (math.cos(ang), math.sin(ang))
                idx[v] = t / N
            if layout == "power":
                pos[0], dirs[0], idx[0] = (cx, cy), (0.0, -1.0), 0.0
            self.pr = max(1.5, min(7, R * math.pi / q * 0.38)) * self.v_psize.get()
        else:
            n, p = F.n, F.p
            rows, cols = p ** (n // 2), p ** (n - n // 2)
            s = max(4, min((W - 2 * margin) / cols, (H - top - 2 * margin) / rows))
            x0 = (W - s * cols) / 2
            y0 = top + (H - top - s * rows) / 2
            cx, cy, R = W / 2, top + (H - top) / 2, s * max(rows, cols) / 2
            for v in range(q):
                c, r = v % cols, v // cols
                pos[v] = (x0 + (c + 0.5) * s, y0 + (rows - r - 0.5) * s)   # row 0 at the bottom
                dirs[v] = (0.0, 1.0)
                idx[v] = v / q
            self.pr = max(1.5, min(7, s * 0.16)) * self.v_psize.get()
        self.positions, self.out_dirs, self.layout_index = pos, dirs, idx
        self.center, self.R = (cx, cy), R

    def _edge_path(self, x0, y0, x1, y1):
        style = self.v_curve.get()
        bend = self.v_bend.get()
        if style == "straight" or abs(bend) < 1e-3:
            return [(x0, y0), (x1, y1)]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if style == "bent":
            cx, cy = mx - (y1 - y0) * bend, my + (x1 - x0) * bend
        else:   # pulled toward the centre
            t = (bend + 0.8) / 1.6
            cx, cy = mx + (self.center[0] - mx) * t, my + (self.center[1] - my) * t
        pts = []
        for i in range(17):
            t = i / 16
            u = 1 - t
            pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1))
        return pts

    @staticmethod
    def _cut(pts, r):
        x0, y0 = pts[0]
        prev_d = 0.0
        for i in range(1, len(pts)):
            x, y = pts[i]
            d = math.hypot(x - x0, y - y0)
            if d >= r:
                px, py = pts[i - 1]
                t = (r - prev_d) / (d - prev_d) if d != prev_d else 0
                return [(px + (x - px) * t, py + (y - py) * t)] + pts[i:]
            prev_d = d
        return []

    # ── drawing ───────────────────────────────────────────────────────────
    def schedule_redraw(self):
        if self._redraw_job is None:
            self._redraw_job = self.root.after(25, self.redraw)

    def _edge_colors(self, th):
        F, m, q = self.F, self.mapping, self.F.q
        mode, base = self.v_ecolor.get(), th["edge"]
        pal = PALETTE_DARK if self.v_theme.get() == "dark" else PALETTE
        if mode == "single":
            cols = [base] * q
        elif mode == "component":
            comp = self.analysis["comp"]
            size = {}
            for v in range(q):
                size[comp[v]] = size.get(comp[v], 0) + 1
            rank = {cid: i for i, cid in enumerate(sorted(size, key=lambda cid: (-size[cid], cid)))}
            cols = [pal[rank[comp[v]]] if rank[comp[v]] < len(pal) else hsv_hex(rank[comp[v]] * 0.618, 0.7, 0.8)
                    for v in range(q)]
        elif mode == "source":
            cols = [hsv_hex(self.layout_index[v]) for v in range(q)]
        elif mode == "length":
            P = self.positions
            L = [math.dist(P[v], P[m[v]]) for v in range(q)]
            mx = max(L) or 1
            cols = [hsv_hex(0.66 - 0.66 * L[v] / mx) for v in range(q)]
        else:
            divs = divisors(q - 1)
            cols = [th["muted"] if v == 0 else hsv_hex(divs.index(F.order(v)) / len(divs)) for v in range(q)]
        op = self.v_opacity.get()
        return [blend(c, th["bg"], 1 - op) for c in cols]

    def _point_color(self, v, th):
        F, mode = self.F, self.v_pcolor.get()
        if mode == "plain" or (v == 0 and mode != "subfield"):
            return th["fg"]
        if mode == "order":
            divs = divisors(F.q - 1)
            return hsv_hex(divs.index(F.order(v)) / len(divs), 0.8, 0.85)
        if mode == "log":
            return hsv_hex(F.log[v] / (F.q - 1), 0.8, 0.9)
        if mode == "primitive":
            return th["accent"] if F.is_generator(v) else th["muted"]
        degs = F.subfield_degrees()
        return hsv_hex(degs.index(F.smallest_subfield(v)) / len(degs) + 0.1, 0.8, 0.85)

    def redraw(self, progressive=False):
        self._redraw_job = None
        if self._prog_job:
            self.root.after_cancel(self._prog_job)
            self._prog_job = None
        c, F = self.canvas, self.F
        q = F.q
        c.delete("all")
        W, H = max(c.winfo_width(), 300), max(c.winfo_height(), 300)
        th = THEMES[self.v_theme.get()]
        c.configure(bg=th["bg"])
        self.compute_positions(W, H)
        if len(self.mapping) != q:
            return
        layout = self.v_layout.get()
        cx, cy = self.center
        if self.v_circle.get() and layout != "grid":
            c.create_oval(cx - self.R, cy - self.R, cx + self.R, cy + self.R, outline=th["circle"])
        if self.v_title.get():
            c.create_text(12, 10, anchor="nw", fill=th["fg"], font=("Helvetica", 12, "bold"),
                          text=f"GF({F.q})" + (f"  mod {F.modulus_str()}" if F.n > 1 else "")
                          + f"  ·  {self.map_desc}")

        # edge styles
        cols = self._edge_colors(th)
        width = self.v_width.get()
        widths = [width] * q
        orbit = set(self.sel_orbit) if self.selected is not None else None
        if orbit is not None:
            for v in range(q):
                if v in orbit:
                    cols[v], widths[v] = th["accent"], max(2.4, width * 2)
                else:
                    cols[v] = blend(cols[v], th["bg"], 0.8)
        order = sorted(range(q), key=lambda v: v in orbit) if orbit else list(range(q))
        self._edge_style = (cols, widths)
        if progressive:
            self._draw_points(th)
            self._progressive(order, 0, max(1, q // 120))
        else:
            for v in order:
                self._draw_edge(v, cols[v], widths[v], th)
            self._draw_points(th)

    def _progressive(self, order, start, batch):
        cols, widths = self._edge_style
        th = THEMES[self.v_theme.get()]
        for v in order[start:start + batch]:
            self._draw_edge(v, cols[v], widths[v], th)
            self.canvas.tag_raise("pt")
        if start + batch < len(order):
            self._prog_job = self.root.after(max(10, int(self.v_delay.get()) // 6),
                                             lambda: self._progressive(order, start + batch, batch))
        else:
            self._prog_job = None

    def _draw_edge(self, v, color, width, th):
        c = self.canvas
        w = self.mapping[v]
        x0, y0 = self.positions[v]
        r = self.pr
        if v == w:
            if self.v_loops.get():
                ux, uy = self.out_dirs[v]
                if self.v_layout.get() == "grid":
                    ux, uy = 0.0, -1.0
                lr = max(4.0, r * 1.6)
                lx, ly = x0 + ux * (r + lr * 0.8), y0 + uy * (r + lr * 0.8)
                c.create_oval(lx - lr, ly - lr, lx + lr, ly + lr, outline=color, width=width, tags=("edge",))
            return
        x1, y1 = self.positions[w]
        pts = self._edge_path(x0, y0, x1, y1)
        pts = self._cut(pts, r + 1)
        if len(pts) < 2:
            return
        pts = self._cut(pts[::-1], r + 1.5)[::-1]
        if len(pts) < 2:
            return
        c.create_line(*[z for pt in pts for z in pt], fill=color, width=width, capstyle="round", tags=("edge",))
        if self.v_arrows.get():
            size = max(4.0, min(13.0, self.R * math.pi / self.F.q * 0.55 + 3)) * self.v_arrow_scale.get() \
                   * (0.8 + 0.2 * width)
            (fx, fy), (tx, ty) = pts[-2], pts[-1]
            seg = math.hypot(tx - fx, ty - fy)
            if seg < 1e-6 or math.dist(pts[0], pts[-1]) < size * 1.3:
                return
            ux, uy = (tx - fx) / seg, (ty - fy) / seg
            bx, by = tx - ux * size, ty - uy * size
            wd = size * 0.42
            c.create_polygon(tx, ty, bx - uy * wd, by + ux * wd, bx + uy * wd, by - ux * wd,
                             fill=color, outline="", tags=("edge",))

    def _draw_points(self, th):
        c, F = self.canvas, self.F
        r = self.pr
        fixed = set(self.analysis.get("fixed", [])) if self.v_fixed.get() else set()
        orbit = set(self.sel_orbit) if self.selected is not None else set()
        show_labels = self.v_labels.get()
        fs = self.v_lsize.get()
        lfmt = self._lab_fmt()
        for v in range(F.q):
            x, y = self.positions[v]
            col = self._point_color(v, th)
            rr = r * 1.5 if v in orbit else r
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=col,
                          outline=th["accent"] if v in fixed else col, width=2 if v in fixed else 1, tags=("pt",))
            if show_labels:
                ux, uy = self.out_dirs[v]
                d = rr + 4
                anchor = ("n" if uy > 0.38 else "s" if uy < -0.38 else "") + ("w" if ux > 0.38 else "e" if ux < -0.38 else "")
                c.create_text(x + ux * d, y + uy * d, text=F.fmt(v, lfmt), anchor=anchor or "center",
                              fill=th["accent"] if v == self.selected else th["label"],
                              font=("Helvetica", fs, "bold" if v == self.selected else "normal"), tags=("pt",))
        for v, (txt, color) in self.marks.items():
            x, y = self.positions[v]
            rr = r + 6
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline=th["mark"], width=2.5, tags=("pt",))
            c.create_text(x + rr + 2, y - rr - 2, text=txt, anchor="sw", fill=th["mark"],
                          font=("Helvetica", max(fs, 10), "bold"), tags=("pt",))

    # ── interaction ───────────────────────────────────────────────────────
    def _nearest(self, x, y):
        best, bd = None, (max(self.pr, 3) + 6) ** 2
        for v, (px, py) in enumerate(self.positions):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = v, d
        return best

    def on_motion(self, ev):
        v = self._nearest(ev.x, ev.y)
        F = self.F
        if v is None:
            self.status.configure(text=f"GF({F.q}),  {self.map_desc}")
            return
        w = self.mapping[v]
        self.status.configure(text=f"x = {F.describe(v)}     →     f(x) = {F.describe(w)}")

    def on_click(self, ev):
        self.canvas.focus_set()
        self.select(self._nearest(ev.x, ev.y))

    def select(self, v):
        self.selected = v
        if v is None:
            self.sel_orbit = []
            self._set_text(self.t_insp, "Click a point on the canvas to see everything about that element.")
        else:
            self.sel_orbit = self._orbit(v)
            self.inspect(v)
        self.schedule_redraw()

    def _orbit(self, v):
        seen, out, x = set(), [], v
        while x not in seen:
            seen.add(x)
            out.append(x)
            x = self.mapping[x]
        return out

    def inspect(self, v):
        F = self.F
        L = [f"x = {v}"]
        if F.p == 2:
            L.append(f"  hex          {F.fmt(v, 'hex')}")
        L.append(f"  vector       {F.fmt(v, 'vec')}   (coefficients of α{sup(F.n - 1)} … α⁰)")
        L.append(f"  polynomial   {F.fmt(v, 'poly', False)}")
        if v == 0:
            L.append("  0 is not a power of g; it has no inverse and no order.")
        else:
            L.append(f"  power        {F.power_str(v)}   (log_{F.gname} x = {F.log[v]})")
            o = F.order(v)
            L.append(f"  order        {o}" + ("   ★ generator of GF(q)*" if o == F.q - 1 else f"   (divides {F.q - 1})"))
            iv = F.inv(v)
            L.append(f"  inverse      {F.describe(iv)}")
        L.append(f"  −x           {F.describe(F.neg(v))}")
        L.append(f"  x^p          {F.describe(F.frobenius(v))}")
        conj = F.conjugates(v)
        L.append(f"  conjugates   {{{', '.join(F.fmt(c, self._lab_fmt()) for c in conj)}}}")
        L.append(f"  min. poly    {poly_to_str(F.minimal_poly(v), 'X')}")
        L.append(f"  trace, norm  Tr(x) = {F.trace(v)},  N(x) = {F.norm(v)}   (both in GF({F.p}))")
        d = F.smallest_subfield(v)
        L.append(f"  lives in     GF({F.p}{sup(d) if d > 1 else ''})" + ("  (prime field)" if d == 1 else ""))
        L.append("")
        orb = self.sel_orbit or self._orbit(v)
        tail = self.mapping[orb[-1]]
        lf = self._lab_fmt()
        chain = " → ".join(F.fmt(z, lf) for z in orb[:24]) + (" → …" if len(orb) > 24 else "") + f" → {F.fmt(tail, lf)}"
        L.append(f"under {self.map_desc}:")
        L.append(f"  f(x) = {F.describe(self.mapping[v])}")
        L.append(f"  orbit: {chain}")
        if tail == v:
            L.append(f"  x lies on a cycle of length {len(orb)}")
        else:
            L.append(f"  reaches a cycle after {orb.index(tail)} steps")
        self._set_text(self.t_insp, "\n".join(L))

    # ── calculator ───────────────────────────────────────────────────────
    def calculate(self):
        F = self.F
        try:
            a, b = F.parse(self.v_ca.get()), F.parse(self.v_cb.get())
            k = eval_int_expr(self.v_ck.get(), {"q": F.q, "p": F.p, "n": F.n})
        except (ValueError, ZeroDivisionError) as exc:
            self._set_text(self.t_calc, f"⚠ {exc}")
            return
        D = F.describe
        L = [f"a      = {D(a)}", f"b      = {D(b)}", ""]
        L.append(f"a + b  = {D(F.add(a, b))}")
        L.append(f"a − b  = {D(F.sub(a, b))}")
        L.append(f"a · b  = {D(F.mul(a, b))}")
        L.append(f"a / b  = {D(F.div(a, b)) if b else 'undefined (b = 0)'}")
        L.append(f"a⁻¹    = {D(F.inv(a)) if a else 'undefined'}")
        try:
            L.append(f"a^{k}{' ' * max(1, 4 - len(str(k)))}= {D(F.pow(a, k))}")
        except ZeroDivisionError as exc:
            L.append(f"a^{k}: {exc}")
        L.append(f"ord(a) = {F.order(a) or '—'},  ord(b) = {F.order(b) or '—'}")
        if F.n > 1:
            L += ["", "── a · b step by step ──"] + F.mul_steps(a, b)
            L += ["", "── a⁻¹ by the extended Euclidean algorithm ──"] + F.inverse_steps(a)
        else:
            L += ["", f"(prime field: a·b = {a}·{b} mod {F.p}; a⁻¹ via Fermat a^(p−2) or extended Euclid)"]
        L += ["", "── via logs (how the program multiplies) ──"]
        if a and b:
            la, lb = F.log[a], F.log[b]
            L.append(f"log a + log b = {la} + {lb} = {la + lb} ≡ {(la + lb) % (F.q - 1)} (mod {F.q - 1})"
                     f"  ⇒  a·b = {F.gname}{sup((la + lb) % (F.q - 1))}")
        else:
            L.append("one factor is 0, so the product is 0.")
        self._set_text(self.t_calc, "\n".join(L))

    def mark_calc(self):
        F = self.F
        try:
            a, b = F.parse(self.v_ca.get()), F.parse(self.v_cb.get())
        except ValueError as exc:
            self._set_text(self.t_calc, f"⚠ {exc}")
            return
        self.marks = {a: ("a", None), F.mul(a, b): ("a·b", None)}
        self.marks[b] = ("b" if b != a else "a=b", None)
        self.schedule_redraw()

    # ── crypto ───────────────────────────────────────────────────────────
    def random_secrets(self):
        q = self.F.q
        hi = max(2, q - 2)
        for v in (self.v_dh_a, self.v_dh_b, self.v_dh_r):
            v.set(str(random.randint(1, hi)))
        self.v_dh_m.set(str(random.randint(1, q - 1)))
        self.run_dh()

    def run_dh(self):
        F = self.F
        D = F.describe
        env = {"q": F.q, "p": F.p, "n": F.n}
        try:
            g = F.parse(self.v_dh_g.get())
            if g == 0:
                raise ValueError("g must be nonzero")
            a = eval_int_expr(self.v_dh_a.get(), env)
            b = eval_int_expr(self.v_dh_b.get(), env)
            r = eval_int_expr(self.v_dh_r.get(), env)
            m = F.parse(self.v_dh_m.get())
        except ValueError as exc:
            self._set_text(self.t_crypto, f"⚠ {exc}")
            return
        o = F.order(g)
        A, B = F.pow(g, a), F.pow(g, b)
        K1, K2 = F.pow(B, a), F.pow(A, b)
        L = ["Public: the field GF(%d) and g = %s" % (F.q, D(g)),
             f"ord(g) = {o}" + ("  ★ generator" if o == F.q - 1 else f"  — only {o} possible keys! pick a generator"),
             "",
             f"Alice: secret a = {a}  →  sends A = gᵃ = {D(A)}",
             f"Bob:   secret b = {b}  →  sends B = gᵇ = {D(B)}",
             f"Alice computes Bᵃ = {D(K1)}",
             f"Bob   computes Aᵇ = {D(K2)}",
             f"shared secret K = g^(ab) {'✓ identical' if K1 == K2 else '✗ mismatch?!'}",
             "",
             "Eve sees g, A, B. She needs a from A = gᵃ (discrete log):"]
        x, steps = 1, 0
        while x != A and steps <= o:
            x = F.mul(x, g)
            steps += 1
        L.append(f"  brute force: {steps} multiplications → a ≡ {steps % o} (mod {o})")
        big = max(factorize(o)) if o > 1 else 1
        L.append(f"  ord(g) = {factor_str(o)}. Pohlig–Hellman splits the problem along these prime factors,")
        L.append(f"  so the real cost is about √{big} (largest prime factor). Real systems therefore use")
        L.append("  huge groups whose order has a huge prime factor.")
        L += ["", "ElGamal (Bob's public key B, message m):",
              f"  m = {D(m)},  ephemeral r = {r}"]
        c1, c2 = F.pow(g, r), F.mul(m, F.pow(B, r))
        L.append(f"  ciphertext c1 = gʳ = {F.fmt(c1, self._lab_fmt())},  c2 = m·Bʳ = {F.fmt(c2, self._lab_fmt())}")
        s = F.pow(c1, b)
        dec = F.div(c2, s) if s else None
        L.append(f"  Bob: s = c1ᵇ = {F.fmt(s, self._lab_fmt())},  m = c2·s⁻¹ = "
                 f"{F.fmt(dec, self._lab_fmt()) if dec is not None else '—'} {'✓' if dec == m else '✗'}")
        self._set_text(self.t_crypto, "\n".join(L))
        if self.v_dh_mark.get():
            self.marks = {A: ("A", None), B: ("B", None)}
            self.marks[K1] = ("K" if K1 not in self.marks else self.marks[K1][0] + "=K", None)
            self.marks[g] = ("g" if g not in self.marks else self.marks[g][0] + "=g", None)
        else:
            self.marks = {}
        self.schedule_redraw()

    def aes_details(self):
        F = self.F
        if not F.is_aes():
            self._set_text(self.t_crypto, "Load the AES field first (button above).")
            return
        try:
            x = F.parse(self.v_aes_x.get())
        except ValueError as exc:
            self._set_text(self.t_crypto, f"⚠ {exc}")
            return
        b = F.inv(x) if x else 0
        bits = lambda v: f"{v:08b}"
        L = [f"x = {F.describe(x)}", "",
             "Step 1 — invert in GF(2⁸) (0 ↦ 0):",
             f"  b = x⁻¹ = {F.fmt(b, 'hex')}" + (f"   (check: x·b = {F.fmt(F.mul(x, b), 'hex')})" if x else "")]
        if x:
            L += ["  via extended Euclid:"] + ["   " + s for s in F.inverse_steps(x)[1:-1]]
        L += ["", "Step 2 — GF(2)-affine map:  s = b ⊕ (b<<<1) ⊕ (b<<<2) ⊕ (b<<<3) ⊕ (b<<<4) ⊕ 0x63",
              f"  {'b':<7} {bits(b)}"]
        for k in range(1, 5):
            L.append(f"  {'b<<<' + str(k):<7} {bits(rotl8(b, k))}")
        L.append(f"  {'0x63':<7} {bits(0x63)}")
        s = aes_sbox(F, x)
        L.append(f"  {'⊕ all':<7} {bits(s)}")
        L += ["", f"S({F.fmt(x, 'hex')}) = {F.fmt(s, 'hex')}",
              "", "Why: x⁻¹ makes S highly nonlinear (resists linear & differential cryptanalysis);",
              "the affine step removes the algebraic simplicity (and the fixed points 0, 1) of plain x⁻¹."]
        self._set_text(self.t_crypto, "\n".join(L))
        self.marks = {x: ("x", None)}
        self.marks[s] = ("S(x)" if s != x else "x=S(x)", None)
        self.schedule_redraw()

    def aes_table(self):
        if not self.F.is_aes():
            self.load_aes()
        F = self.F
        top = tk.Toplevel(self.root)
        top.title("AES S-box")
        t = tk.Text(top, font="TkFixedFont", width=58, height=22)
        t.pack(fill="both", expand=True)
        rows = ["     " + " ".join(f"{c:2x}" for c in range(16)), "    " + "─" * 48]
        for r in range(16):
            rows.append(f" {r:x}0│" + " ".join(f"{aes_sbox(F, 16 * r + c):02x}" for c in range(16)))
        S = [aes_sbox(F, v) for v in range(256)]
        rows += ["", f"bijective: {len(set(S)) == 256},  fixed points: {sum(S[v] == v for v in range(256))},"
                     f"  S(x) = x⊕0xff: {sum(S[v] == v ^ 0xFF for v in range(256))}",
                 "row = high nibble, column = low nibble (e.g. S(0x53) = 0xed)"]
        t.insert("1.0", "\n".join(rows))
        t.configure(state="disabled")

    # ── operation tables ─────────────────────────────────────────────────
    def open_table(self, kind):
        F = self.F
        q = F.q
        if q > TABLE_MAX_Q:
            messagebox.showinfo("Too big", f"Tables are drawn for q ≤ {TABLE_MAX_Q}.")
            return
        top = tk.Toplevel(self.root)
        sym = "+" if kind == "add" else "·"
        top.title(f"GF({q}) {'addition' if kind == 'add' else 'multiplication'} table")
        order_var = tk.StringVar(value="power" if kind == "mul" else "integer")
        bar = ttk.Frame(top, padding=4)
        bar.pack(fill="x")
        ttk.Label(bar, text="order rows/columns by:").pack(side="left")
        for val in ("integer", "power"):
            ttk.Radiobutton(bar, text=val, value=val, variable=order_var, command=lambda: draw()).pack(side="left")
        info = ttk.Label(top, padding=4, text="hover a cell")
        info.pack(fill="x", side="bottom")
        cell = max(4, min(30, 660 // (q + 1)))
        size = cell * (q + 1)
        cv = tk.Canvas(top, width=size, height=size, bg="white", highlightthickness=0)
        cv.pack(padx=6, pady=6)
        op = F.add if kind == "add" else F.mul
        state = {}

        def colour(v):
            if kind == "mul":
                return "#333333" if v == 0 else hsv_hex(F.log[v] / (q - 1), 0.55, 0.95)
            return hsv_hex(v / q, 0.55, 0.95)

        def draw():
            cv.delete("all")
            order = list(range(q)) if order_var.get() == "integer" else [0] + F.exp
            state["order"] = order
            fmt = "power" if order_var.get() == "power" else self._lab_fmt()
            fs = max(6, min(11, int(cell * 0.38)))
            for i, a in enumerate(order):
                for j, b in enumerate(order):
                    v = op(a, b)
                    x, y = (j + 1) * cell, (i + 1) * cell
                    cv.create_rectangle(x, y, x + cell, y + cell, fill=colour(v), outline="white" if cell > 6 else "")
                    if cell >= 22 and q <= 32:
                        cv.create_text(x + cell / 2, y + cell / 2, text=F.fmt(v, fmt), font=("Helvetica", fs),
                                       fill="white" if (kind == "mul" and v == 0) else "black")
                if cell >= 14:
                    cv.create_text(cell / 2, (i + 1.5) * cell, text=F.fmt(a, fmt), font=("Helvetica", fs, "bold"))
                    cv.create_text((i + 1.5) * cell, cell / 2, text=F.fmt(a, fmt), font=("Helvetica", fs, "bold"))
            cv.create_text(cell / 2, cell / 2, text=sym, font=("Helvetica", fs + 2, "bold"))

        def hover(ev):
            i, j = ev.y // cell - 1, ev.x // cell - 1
            if 0 <= i < q and 0 <= j < q:
                a, b = state["order"][i], state["order"][j]
                info.configure(text=f"{F.fmt(a, 'poly')}  {sym}  {F.fmt(b, 'poly')}  =  {F.describe(op(a, b))}"
                                    f"      [{a} {sym} {b}]")

        cv.bind("<Motion>", hover)
        draw()
        ttk.Label(top, padding=(6, 0), foreground="#666", wraplength=size,
                  text=("Power order makes the × table a cyclic shift in every row: GF(q)* ≅ ℤ/(q−1)."
                        if kind == "mul" else
                        f"Addition is coefficient-wise mod {F.p}: GF(q) ≅ (ℤ/{F.p})^{F.n} as a group.")).pack(side="bottom")

    # ── export ───────────────────────────────────────────────────────────
    def save_image(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg",
                                            filetypes=[("SVG", "*.svg"), ("Encapsulated PostScript", "*.eps")],
                                            initialfile=f"GF{self.F.q}_{self.v_op.get()}.svg")
        if not path:
            return
        if path.lower().endswith(".eps"):
            self.canvas.postscript(file=path, colormode="color")
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.to_svg())
        self.status.configure(text=f"saved {path}")

    def to_svg(self):
        c = self.canvas
        W, H = c.winfo_width(), c.winfo_height()
        bg = THEMES[self.v_theme.get()]["bg"]
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
               f'<rect width="100%" height="100%" fill="{bg}"/>']
        for it in c.find_all():
            t, co = c.type(it), c.coords(it)
            g = lambda opt: c.itemcget(it, opt) or "none"
            if t == "line":
                pts = " ".join(f"{co[i]:.1f},{co[i + 1]:.1f}" for i in range(0, len(co), 2))
                out.append(f'<polyline points="{pts}" fill="none" stroke="{g("fill")}" '
                           f'stroke-width="{g("width")}" stroke-linecap="round"/>')
            elif t == "oval":
                x0, y0, x1, y1 = co
                out.append(f'<ellipse cx="{(x0 + x1) / 2:.1f}" cy="{(y0 + y1) / 2:.1f}" rx="{(x1 - x0) / 2:.1f}" '
                           f'ry="{(y1 - y0) / 2:.1f}" fill="{g("fill")}" stroke="{g("outline")}" stroke-width="{g("width")}"/>')
            elif t == "polygon":
                pts = " ".join(f"{co[i]:.1f},{co[i + 1]:.1f}" for i in range(0, len(co), 2))
                out.append(f'<polygon points="{pts}" fill="{g("fill")}"/>')
            elif t == "rectangle":
                x0, y0, x1, y1 = co
                out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{g("fill")}"/>')
            elif t == "text":
                anc = c.itemcget(it, "anchor")
                ta = "middle" if anc == "center" else "start" if "w" in anc else "end" if "e" in anc else "middle"
                db = "central" if anc == "center" else "hanging" if "n" in anc else "auto" if "s" in anc else "central"
                font = c.itemcget(it, "font")
                size = next((tok for tok in font.split() if tok.isdigit()), "10")
                weight = "bold" if "bold" in font else "normal"
                out.append(f'<text x="{co[0]:.1f}" y="{co[1]:.1f}" fill="{g("fill")}" font-family="Helvetica, Arial, sans-serif" '
                           f'font-size="{size}" font-weight="{weight}" text-anchor="{ta}" dominant-baseline="{db}">'
                           f'{esc(c.itemcget(it, "text"))}</text>')
        out.append("</svg>")
        return "\n".join(out)

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=f"GF{self.F.q}_{self.v_op.get()}.csv")
        if not path:
            return
        F = self.F
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x,x_poly,x_power,f(x),f(x)_poly,f(x)_power\n")
            for v in range(F.q):
                w = self.mapping[v]
                fh.write(f'{v},"{F.fmt(v, "poly", False)}",{F.power_str(v)},{w},"{F.fmt(w, "poly", False)}",{F.power_str(w)}\n')
        self.status.configure(text=f"saved {path}")


# ═════════════════════════════════════════════════════════════════════════════
#  Text mode and self-test
# ═════════════════════════════════════════════════════════════════════════════
def print_report(F, op, a, b, k, P, iters):
    print(f"GF({F.q}) = GF({F.p})[x]/({F.modulus_str()})   primitive modulus: {F.modulus_is_primitive}")
    print(f"generator {F.gname} = {F.describe(F.g)}")
    print()
    print(f"{'x':>5}  {'polynomial':<24} {'power':>6}  ->  f(x)")
    m = iterate_map(build_map(F, op, a, b, k, P), iters)
    for v in range(F.q):
        print(f"{v:>5}  {F.fmt(v, 'poly', False):<24} {F.power_str(v):>6}  ->  {m[v]:>4}  {F.fmt(m[v], 'poly', False)}")
    A = analyze_map(m)
    print()
    print(f"bijective: {A['bijective']},  fixed points: {len(A['fixed'])},  cycles: "
          + " + ".join(f"{c}×[{ln}]" for ln, c in A["cycle_type"].items()))
    print(op_note(F, op, a, b, k))


def selftest() -> bool:
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print("FAIL:", msg)

    try:
        import galois  # optional cross-check
    except ImportError:
        galois = None
        print("(galois not installed — skipping the library cross-check)")

    cases = [(2, 1), (3, 1), (7, 1), (13, 1), (2, 2), (2, 3), (2, 4), (3, 2), (5, 2), (3, 3), (2, 5), (7, 2), (2, 8), (11, 2)]
    for p, n in cases:
        q = p ** n
        polys = irreducible_polys(p, n)
        check(len(polys) == (count_irreducible(p, n) if n > 1 else p), f"irreducible count GF({q})")
        check(sum(pr for _, pr in polys) == (euler_phi(q - 1) // n if n > 1 else euler_phi(p - 1)),
              f"primitive count GF({q})")
        moduli = [list(c) for c, _ in polys] if q <= 32 else [None, list(polys[-1][0])]
        for mod in moduli:
            F = FiniteField(p, n, mod)
            pairs = [(x, y) for x in range(q) for y in range(q)] if q <= 64 else \
                [(random.randrange(q), random.randrange(q)) for _ in range(3000)]
            if galois is not None:
                G = galois.GF(q) if n == 1 else galois.GF(q, irreducible_poly=coeffs_to_int(F.modulus, p))
                for x, y in pairs:
                    if F.mul(x, y) != int(G(x) * G(y)) or F.add(x, y) != int(G(x) + G(y)):
                        check(False, f"GF({q}) mod {F.modulus_str()}: {x},{y} disagrees with galois")
                        break
            for x, y in pairs[:400]:
                z = (x * 7 + y) % q
                check(F.mul(x, F.add(y, z)) == F.add(F.mul(x, y), F.mul(x, z)), "distributivity")
                if F._raw_mul(x, y) != F.mul(x, y):
                    check(False, "log tables vs polynomial multiplication")
            for x in range(1, q):
                check(F.mul(x, F.inv(x)) == 1, "inverse")
                if n > 1 and x < 60:
                    last = F.inverse_steps(x)[-1]
                    check(last.startswith(f"a⁻¹ = {F.inv(x)}"), f"extended Euclid GF({q}) x={x}")
            for x in range(min(q, 60)):
                check(F.frobenius(x, n) == x, "Frobenius^n = id")
                check(F.trace(x) < p and F.norm(x) < p, "trace/norm in prime field")
                mp = F.minimal_poly(x)
                check(F.eval_field_poly({e: c for e, c in enumerate(mp)}, x) == 0, "minimal polynomial has x as root")
            check(F.minimal_poly(F.alpha) == F.modulus or n == 1, "minimal poly of α is f")
            for v in range(q):
                for st in ("int", "poly", "vec") + (("power",) if v else ()):
                    s = F.fmt(v, st, compact=False)
                    if F.parse(s) != v:
                        check(False, f"parse(fmt({v}, {st}) = '{s}') round trip")

    A = FiniteField(2, 8, list(AES_MODULUS))
    check(A.parse("x^8") == 0x1B, "x^8 = 0x1b in the AES field")
    check(A.mul(0x57, 0x83) == 0xC1, "FIPS-197 {57}·{83} = {c1}")
    check(A.mul(0x57, 0x13) == 0xFE, "FIPS-197 {57}·{13} = {fe}")
    check(A.inv(0x53) == 0xCA, "AES inverse of 0x53 is 0xca")
    for x, s in ((0x00, 0x63), (0x01, 0x7C), (0x53, 0xED), (0xFF, 0x16), (0x10, 0xCA), (0xC9, 0xDD)):
        check(aes_sbox(A, x) == s, f"S-box({x:#04x})")
    S = [aes_sbox(A, x) for x in range(256)]
    check(len(set(S)) == 256 and not any(S[x] == x for x in range(256)), "S-box permutation without fixed points")
    check(not A.modulus_is_primitive and A.g == 3, "AES modulus not primitive; generator 0x03")
    G7 = FiniteField(7, 1)
    check(G7.parse("-1") == 6 and G7.parse("g^3") == G7.pow(G7.g, 3), "prime field parsing")
    check(eval_int_expr("q-2", {"q": 16, "p": 2, "n": 4}) == 14, "exponent expression")
    try:
        FiniteField(2, 4, [1, 0, 0, 0, 1])     # x^4 + 1 = (x+1)^4
        check(False, "reducible modulus accepted")
    except ValueError:
        pass
    print("self-test:", "all checks passed" if ok else "FAILURES above")
    return ok


# ═════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Interactive explorer for Galois fields GF(p^n).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("Usage")[1])
    ap.add_argument("--p", type=int, help="characteristic (prime)")
    ap.add_argument("--n", type=int, help="extension degree")
    ap.add_argument("--q", type=int, help="field size p^n (alternative to --p/--n)")
    ap.add_argument("--modulus", help="irreducible polynomial, e.g. 'x^4+x+1' or 0x13")
    ap.add_argument("--aes", action="store_true", help="AES field GF(2^8) mod x^8+x^4+x^3+x+1")
    ap.add_argument("--random", action="store_true", help="random field and multiplier (like the original script)")
    ap.add_argument("--op", default="mul", choices=[o[0] for o in OPS])
    ap.add_argument("--a", default="g")
    ap.add_argument("--b", default="1")
    ap.add_argument("--k", default="2")
    ap.add_argument("--P", default="x^3", help="polynomial for --op poly")
    ap.add_argument("--iter", type=int, default=1)
    ap.add_argument("--layout", default="power", choices=list(LAYOUTS))
    ap.add_argument("--theme", default="light", choices=list(THEMES))
    ap.add_argument("--print", action="store_true", help="print the field and the map instead of opening the GUI")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)

    p, n, mod = 2, 4, None
    if args.aes:
        p, n, mod = 2, 8, list(AES_MODULUS)
        if args.op == "mul" and args.a == "g":
            args.a = "0x03"
    elif args.random:
        while True:
            p, n = random.choice([2, 3, 5, 7, 11]), random.randint(1, 3)
            if p ** n > 2:
                break
        mod = list(random.choice(irreducible_polys(p, n))[0])
    elif args.q:
        pn = prime_power(args.q)
        if not pn:
            ap.error(f"{args.q} is not a prime power — no field of that size exists")
        p, n = pn
    if args.p:
        p = args.p
    if args.n:
        n = args.n
    try:
        if args.modulus:
            mod = parse_integer_poly(args.modulus, p, n)
        F = FiniteField(p, n, mod)
        if args.random:
            args.a = str(random.randint(1, F.q - 1))
        if args.print:
            op = args.op
            a = F.parse(args.a) if "a" in OP_PARAMS[op] else None
            b = F.parse(args.b) if "b" in OP_PARAMS[op] else None
            k = eval_int_expr(args.k, {"q": F.q, "p": F.p, "n": F.n}) if "k" in OP_PARAMS[op] else None
            P = F.parse_field_poly(args.P) if op == "poly" else None
            print_report(F, op, a, b, k, P, args.iter)
            return
    except ValueError as exc:
        ap.error(str(exc))

    if tk is None:
        sys.exit("tkinter is not available in this Python. Install it (e.g. `sudo apt install python3-tk`) "
                 "or use --print / --selftest.")
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    Explorer(root, F, args)
    root.mainloop()


if __name__ == "__main__":
    main()
