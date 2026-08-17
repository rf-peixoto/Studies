#!/usr/bin/env python3
"""
NameForge - Underground Handle Workbench
----------------------------------------
Offline CLI for designing fictional Internet aliases inspired by
BBS, IRC, warez, phreak, cypherpunk and underground computing cultures.

This is a creative-writing tool. It generates fictional handles and evaluates
their stylistic properties; it is not an identity-generation or impersonation tool.

Version 2.1 — see CHANGELOG.md for the list of bug fixes over 2.0.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP = "NameForge"
VERSION = "2.1.0"
SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------


class T:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    WHITE = "\033[37m"


# Global colour switch. Set once in main(); every paint() call honours it.
# (2.0 bug: --no-color computed a flag that paint() never consulted.)
_COLOR_ENABLED = False


def set_color(enabled: bool) -> None:
    global _COLOR_ENABLED
    _COLOR_ENABLED = bool(enabled)


def paint(s, color, enabled=None):
    use = _COLOR_ENABLED if enabled is None else enabled
    return f"{color}{s}{T.RESET}" if use else str(s)


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def visible_len(s: str) -> int:
    return len(ANSI_RE.sub("", s))


def pad(s: str, width: int) -> str:
    """Left-align to a visible width, ignoring ANSI escapes.

    (2.0 bug: f"{paint(x):22}" padded the string *including* the 9 invisible
    escape characters, so every coloured column was misaligned.)
    """
    return s + " " * max(0, width - visible_len(s))


def banner():
    print(
        paint(
            r"""
 _   _                    _____
| \ | | __ _ _ __ ___   |  ___|__  _ __ __ _  ___
|  \| |/ _` | '_ ` _ \  | |_ / _ \| '__/ _` |/ _ \
| |\  | (_| | | | | | | |  _| (_) | | | (_| |  __/
|_| \_|\__,_|_| |_| |_| |_|  \___/|_|  \__, |\___|
                                        |___/
       UNDERGROUND HANDLE WORKBENCH
""".rstrip(),
            T.CYAN,
        )
    )
    print()


def warn(msg: str) -> None:
    print(paint(f"warning: {msg}", T.YELLOW), file=sys.stderr)


class NameForgeError(Exception):
    """User-facing configuration or input error."""


# ---------------------------------------------------------------------------
# Lexicon
# ---------------------------------------------------------------------------

# Canonical pool names -> the JSON key they are read from.
# Legacy 2.0 keys are kept so old system files still load unchanged.
POOL_KEYS = {
    "technical": "technical_terms",
    "abstract": "abstract_terms",
    "mythology": "mythology",
    "scifi": "scifi",
    "mundane": "mundane",
    "threatening": "threatening",
    "cyberpunk": "cyberpunk",
    "crypto": "crypto_terms",
    "organic": "organic_terms",
    "bureaucratic": "bureaucratic_terms",
    "phreak": "phreak_terms",
}

# Tags every term in a pool inherits unless it declares its own.
POOL_DEFAULT_TAGS = {
    "technical": ("technical",),
    "abstract": ("abstract", "mysterious"),
    "mythology": ("literary", "mythological"),
    "scifi": ("literary", "cyberpunk"),
    "mundane": ("mundane", "irreverent"),
    "threatening": ("threatening",),
    "cyberpunk": ("cyberpunk",),
    "crypto": ("technical", "cryptographic"),
    "organic": ("organic", "mundane"),
    "bureaucratic": ("bureaucratic", "mundane"),
    "phreak": ("oldschool", "technical"),
}


@dataclass(frozen=True)
class Term:
    """One vocabulary item, with the metadata that makes scoring explainable."""

    term: str
    pool: str = ""
    tags: tuple[str, ...] = ()
    gloss: str = ""
    since: int = 1970  # first year the word is plausible in this scene
    until: int = 9999  # last year it still reads as current
    weight: float = 1.0  # relative pick probability inside its pool
    register: str = "common"  # insider | common | pop

    @staticmethod
    def parse(raw, pool: str) -> "Term":
        """Accept either a bare string (2.0 format) or an object (2.1 format)."""
        defaults = POOL_DEFAULT_TAGS.get(pool, ())
        if isinstance(raw, str):
            return Term(term=raw.strip().lower(), pool=pool, tags=defaults)
        if not isinstance(raw, dict):
            raise NameForgeError(f"lexicon entry in '{pool}' must be a string or object, got {type(raw).__name__}")
        word = str(raw.get("term", "")).strip().lower()
        if not word:
            raise NameForgeError(f"lexicon entry in '{pool}' is missing a 'term' field")
        tags = tuple(dict.fromkeys([t.strip().lower() for t in raw.get("tags", []) if t] or defaults))
        try:
            weight = float(raw.get("weight", 1.0))
        except (TypeError, ValueError):
            raise NameForgeError(f"term '{word}': weight must be a number")
        if weight < 0:
            raise NameForgeError(f"term '{word}': weight must not be negative")
        return Term(
            term=word,
            pool=pool,
            tags=tags,
            gloss=str(raw.get("gloss", "")),
            since=int(raw.get("since", 1970)),
            until=int(raw.get("until", 9999)),
            weight=weight,
            register=str(raw.get("register", "common")).lower(),
        )

    def to_json(self):
        out = {"term": self.term, "tags": list(self.tags)}
        if self.gloss:
            out["gloss"] = self.gloss
        if self.since != 1970:
            out["since"] = self.since
        if self.until != 9999:
            out["until"] = self.until
        if self.weight != 1.0:
            out["weight"] = self.weight
        if self.register != "common":
            out["register"] = self.register
        return out


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class Character:
    id: str
    given_name: str = ""
    middle_name: str = ""
    family_name: str = ""
    aliases: list[str] = field(default_factory=list)
    era: str = ""
    geography: str = ""
    culture: str = ""
    generation: str = ""
    social_class: str = ""
    family_structure: str = ""
    religion: str = ""
    profession: str = ""
    personality: list[str] = field(default_factory=list)
    public_identity: str = ""
    private_identity: str = ""
    contradiction: str = ""
    narrative_role: str = ""
    desired_impression: list[str] = field(default_factory=list)
    naming_system: str = ""
    notes: str = ""
    # --- new in 2.1 -------------------------------------------------------
    first_online_year: int = 0  # when they picked the handle; drives era fit
    languages: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)  # feeds semantic resonance
    handle_history: list[str] = field(default_factory=list)  # earlier aliases
    avoid: list[str] = field(default_factory=list)  # substrings to reject
    seed_words: list[str] = field(default_factory=list)  # writer's own vocabulary

    @property
    def full_name(self):
        return " ".join(x for x in [self.given_name, self.middle_name, self.family_name] if x).strip()

    @property
    def searchable_text(self):
        return " ".join(
            [
                self.era, self.geography, self.culture, self.generation,
                self.social_class, self.family_structure, self.religion,
                self.profession, " ".join(self.personality),
                self.public_identity, self.private_identity, self.contradiction,
                self.narrative_role, " ".join(self.desired_impression),
                " ".join(self.interests), self.notes,
            ]
        ).lower()

    @property
    def era_years(self) -> tuple[int, int]:
        """Best-effort (start, end) years parsed from `era` / first_online_year."""
        years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", self.era or "")]
        # "1990s" style decades.
        for dec in re.findall(r"\b(19\d0|20\d0)s\b", self.era or ""):
            years.extend([int(dec), int(dec) + 9])
        if self.first_online_year:
            years.append(self.first_online_year)
        if not years:
            return (0, 0)
        return (min(years), max(years))


@dataclass
class HandleSystem:
    id: str
    description: str = ""
    schema_version: int = 1
    archetypes: dict[str, dict] = field(default_factory=dict)
    # Legacy flat pools (still accepted verbatim); parsed into `pools`.
    technical_terms: list = field(default_factory=list)
    abstract_terms: list = field(default_factory=list)
    mythology: list = field(default_factory=list)
    scifi: list = field(default_factory=list)
    mundane: list = field(default_factory=list)
    threatening: list = field(default_factory=list)
    cyberpunk: list = field(default_factory=list)
    crypto_terms: list = field(default_factory=list)
    organic_terms: list = field(default_factory=list)
    bureaucratic_terms: list = field(default_factory=list)
    phreak_terms: list = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)
    separators: list[str] = field(default_factory=list)
    digits: list[str] = field(default_factory=list)
    allowed_chars: str = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    max_length: int = 18
    min_length: int = 3
    preferred_lengths: list[int] = field(default_factory=lambda: [4, 5, 6, 7, 8, 9, 10, 11, 12])
    transformations: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    overused: list[str] = field(default_factory=list)
    generic_branding: list[str] = field(default_factory=list)
    archetype_weights: dict[str, float] = field(default_factory=dict)
    score_weights: dict[str, float] = field(default_factory=dict)

    pools: dict[str, list[Term]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if not self.pools:
            self.pools = {}
            for pool, key in POOL_KEYS.items():
                raw = getattr(self, key, []) or []
                self.pools[pool] = dedupe_terms([Term.parse(x, pool) for x in raw])
        self.validate()
        self._index = {}
        for pool, terms in self.pools.items():
            for t in terms:
                self._index.setdefault(t.term, t)

    # -- validation --------------------------------------------------------
    def validate(self):
        if self.min_length < 1:
            raise NameForgeError("min_length must be >= 1")
        if self.max_length < self.min_length:
            raise NameForgeError(f"max_length ({self.max_length}) is below min_length ({self.min_length})")
        if not self.allowed_chars:
            raise NameForgeError("allowed_chars must not be empty")
        bad = [n for n in self.preferred_lengths if not (self.min_length <= n <= self.max_length)]
        if bad:
            raise NameForgeError(f"preferred_lengths outside the length range: {bad}")
        if not self.preferred_lengths:
            self.preferred_lengths = list(range(self.min_length, min(self.max_length, 12) + 1))
        unknown = [k for k in self.archetype_weights if k not in ARCHETYPES]
        if unknown:
            warn(f"archetype_weights refers to unknown archetypes: {', '.join(sorted(unknown))}")
        for k, v in self.archetype_weights.items():
            if not isinstance(v, (int, float)) or v < 0:
                raise NameForgeError(f"archetype_weights['{k}'] must be a non-negative number")

    # -- accessors ---------------------------------------------------------
    def pool(self, *names: str) -> list[Term]:
        out: list[Term] = []
        for n in names:
            out.extend(self.pools.get(n, []))
        return out

    def lookup(self, word: str) -> Term | None:
        return self._index.get(word)

    def enabled_archetypes(self) -> list[str]:
        """Archetypes the system actually declares, in canonical order."""
        declared = [a for a in ARCHETYPES if a in self.archetypes] or list(ARCHETYPES)
        return [a for a in declared if self.archetypes.get(a, {}).get("enabled", True)]

    def to_json(self):
        out = {
            "id": self.id,
            "schema_version": SCHEMA_VERSION,
            "description": self.description,
            "archetypes": self.archetypes,
        }
        for pool, key in POOL_KEYS.items():
            out[key] = [t.to_json() for t in self.pools.get(pool, [])]
        for k in (
            "prefixes", "suffixes", "separators", "digits", "allowed_chars",
            "max_length", "min_length", "preferred_lengths", "transformations",
            "forbidden", "overused", "generic_branding", "archetype_weights",
            "score_weights",
        ):
            out[k] = getattr(self, k)
        return out


@dataclass
class HandleCandidate:
    handle: str
    archetype: str
    score: float
    components: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    transforms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    gloss: str = ""
    penalties: list[str] = field(default_factory=list)

    @property
    def base_archetype(self) -> str:
        return self.archetype.split("+", 1)[0]


def dedupe_terms(terms: list[Term]) -> list[Term]:
    seen = {}
    for t in terms:
        if t.term and t.term not in seen:
            seen[t.term] = t
    return list(seen.values())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def load_json(path: Path, default=None):
    if not path.exists():
        if default is None:
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise NameForgeError(f"{path}: invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}") from None


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _filter_fields(cls, raw: dict, source: Path):
    if not isinstance(raw, dict):
        raise NameForgeError(f"{source}: expected a JSON object, got {type(raw).__name__}")
    known = cls.__dataclass_fields__
    unknown = [k for k in raw if k not in known]
    if unknown:
        warn(f"{source.name}: ignoring unknown field(s): {', '.join(sorted(unknown)[:8])}")
    return {k: v for k, v in raw.items() if k in known}


def load_character(path: Path) -> Character:
    raw = load_json(path)  # raises FileNotFoundError with a real filename
    data = _filter_fields(Character, raw, path)
    if not data.get("id"):
        # 2.0 bug: a missing/blank id produced a bare TypeError from the dataclass.
        data["id"] = path.stem
        warn(f"{path.name}: no 'id' field; using '{data['id']}'")
    return Character(**data)


def load_system(path: Path) -> HandleSystem:
    raw = load_json(path)
    data = _filter_fields(HandleSystem, raw, path)
    if not data.get("id"):
        data["id"] = path.stem
    # 2.0 shipped archetypes as {name: [name]}; 2.1 uses {name: {...}}.
    arche = data.get("archetypes")
    if isinstance(arche, dict):
        data["archetypes"] = {
            k: (v if isinstance(v, dict) else {"tags": list(v) if isinstance(v, list) else []})
            for k, v in arche.items()
        }
    elif isinstance(arche, list):
        data["archetypes"] = {k: {} for k in arche}
    return HandleSystem(**data)


def cast_load(path: Path) -> list[Character]:
    if not path.exists():
        raise FileNotFoundError(2, "No such file or directory", str(path))
    if path.is_file():
        raw = load_json(path, [])
        if isinstance(raw, dict):
            raw = raw.get("characters", [])
        return [Character(**_filter_fields(Character, x, path)) for x in raw]
    out = []
    for p in sorted(path.glob("*.json")):
        try:
            out.append(load_character(p))
        except (NameForgeError, FileNotFoundError, TypeError) as e:
            warn(f"skipping cast file {p.name}: {e}")
    return out


# ---------------------------------------------------------------------------
# Normalization / similarity
# ---------------------------------------------------------------------------


def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def normalize_handle(s: str) -> str:
    s = fold(s).strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^a-z0-9_-]", "", s)
    return s


def words(s: str) -> list[str]:
    return [x for x in re.split(r"[_\-\s]+", fold(s)) if x]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    a, b = normalize_handle(a), normalize_handle(b)
    if not a or not b:
        return 0.0
    return 1 - levenshtein(a, b) / max(len(a), len(b))


def char_ngram_similarity(a: str, b: str, n: int = 2) -> float:
    a, b = normalize_handle(a), normalize_handle(b)
    A = {a[i:i + n] for i in range(max(0, len(a) - n + 1))}
    B = {b[i:i + n] for i in range(max(0, len(b) - n + 1))}
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def combined_similarity(a: str, b: str) -> float:
    return max(similarity(a, b), char_ngram_similarity(a, b))


def entropy_score(s: str) -> float:
    """Shannon entropy of the character distribution, scaled to 0..1."""
    s = normalize_handle(s)
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    h = -sum((v / n) * math.log2(v / n) for v in counts.values())
    # A handle can only reach log2(len) bits, so normalise against that,
    # not against a fixed constant. (2.0 divided by a hardcoded 4.0, which
    # made every short handle look low-entropy regardless of its shape.)
    ceiling = math.log2(n) if n > 1 else 1.0
    return min(1.0, h / ceiling) if ceiling else 0.0


VOWELS = set("aeiouy")


def pronounceability(s: str) -> float:
    """0..1 estimate of how sayable a handle is out loud.

    Matters for fiction: a handle characters must *speak* to each other needs
    to survive being read aloud.
    """
    s = re.sub(r"[^a-z]", "", normalize_handle(s))
    if not s:
        return 0.25
    v = sum(1 for c in s if c in VOWELS)
    ratio = v / len(s)
    # Ideal vowel ratio is around 0.40.
    balance = 1 - min(1.0, abs(ratio - 0.40) / 0.40)
    longest_cluster = max((len(m) for m in re.findall(r"[^aeiouy]+", s)), default=0)
    cluster_penalty = min(1.0, max(0, longest_cluster - 2) * 0.25)
    return max(0.0, min(1.0, balance * 0.75 + 0.25 - cluster_penalty))


def digit_ratio(s: str) -> float:
    s = normalize_handle(s)
    if not s:
        return 0.0
    return sum(1 for c in s if c.isdigit()) / len(s)


def bell(x: float, center: float, width: float) -> float:
    """Smooth 0..1 falloff. Replaces 2.0's hard length cliffs."""
    if width <= 0:
        return 1.0 if x == center else 0.0
    return math.exp(-((x - center) ** 2) / (2 * width ** 2))


# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------

# Single source of truth for archetype metadata. 2.0 duplicated this list in
# four places (argparse choices, README, the scoring table, the init template)
# and they had already drifted apart.
ARCHETYPES: dict[str, dict] = {
    "technical": {
        "tags": ["technical", "intelligent"],
        "note": "Technical terminology gives a direct underground-computing signal.",
        "era": (1975, 9999),
    },
    "abstract": {
        "tags": ["mysterious", "literary", "abstract"],
        "note": "An abstract noun says little and therefore ages well.",
        "era": (1975, 9999),
    },
    "mythological": {
        "tags": ["literary", "gothic", "mythological"],
        "note": "Mythological reference implies education and self-mythologising.",
        "era": (1975, 9999),
    },
    "scifi": {
        "tags": ["cyberpunk", "literary"],
        "note": "Genre vocabulary marks the character as a reader, not just an operator.",
        "era": (1982, 9999),
    },
    "mundane": {
        "tags": ["mundane", "irreverent", "minimal"],
        "note": "A mundane handle can conceal an otherwise dramatic character.",
        "era": (1980, 9999),
    },
    "threatening": {
        "tags": ["threatening"],
        "note": "Overt menace reads as young or performative; use deliberately.",
        "era": (1980, 9999),
    },
    "minimal": {
        "tags": ["minimal", "mysterious"],
        "note": "Short handles imply seniority, confidence or scarcity.",
        "era": (1975, 9999),
    },
    "compound": {
        "tags": ["technical", "mysterious"],
        "note": "Compound construction creates a semantic collision rather than a label.",
        "era": (1980, 9999),
    },
    "technical_myth": {
        "tags": ["technical", "literary"],
        "note": "Technical/mythic fusion is the classic cypherpunk register.",
        "era": (1985, 9999),
    },
    "mundane_threat": {
        "tags": ["irreverent", "threatening", "mundane"],
        "note": "Domestic word plus menace: understated and quotable.",
        "era": (1985, 9999),
    },
    "ironic": {
        "tags": ["irreverent", "mundane"],
        "note": "Deliberately banal construction avoids obvious 'hacker name' aesthetics.",
        "era": (1985, 9999),
    },
    "orthographic": {
        "tags": ["oldschool", "technical", "irreverent"],
        "note": "Orthographic distortion evokes the visual culture of older aliases.",
        "era": (1984, 2012),
    },
    "leet": {
        "tags": ["oldschool", "technical"],
        "note": "Leet substitution is strongly period-marked; after ~2005 it reads as parody.",
        "era": (1985, 2008),
    },
    "numeric": {
        "tags": ["technical", "oldschool"],
        "note": "A trailing number implies a taken name, a birth year, or an in-joke.",
        "era": (1980, 9999),
    },
    "prefix": {
        "tags": ["technical"],
        "note": "Prefixed handle; keep the prefix specific or it reads as filler.",
        "era": (1985, 9999),
    },
    "suffix": {
        "tags": ["technical"],
        "note": "Suffixed handle; file-extension suffixes date to the DOS/BBS era.",
        "era": (1985, 9999),
    },
    "acronym": {
        "tags": ["technical", "minimal", "oldschool"],
        "note": "Initialism reads as institutional, military or self-consciously opaque.",
        "era": (1980, 9999),
    },
    "phonetic": {
        "tags": ["irreverent", "oldschool"],
        "note": "Phonetic respelling is the oldest handle joke there is.",
        "era": (1984, 9999),
    },
    "seeded": {
        "tags": ["personal"],
        "note": "Built from the writer's own seed words for this character.",
        "era": (1975, 9999),
    },
}

ARCHETYPE_NAMES = list(ARCHETYPES)


@dataclass
class Build:
    """A generated handle plus the provenance needed to explain its score."""

    handle: str
    archetype: str
    sources: list[Term] = field(default_factory=list)
    transforms: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Handle construction
# ---------------------------------------------------------------------------

LEET = {"a": "4", "e": "3", "i": "1", "l": "1", "o": "0", "s": "5", "t": "7", "g": "9", "b": "8"}

PHONETIC_SWAPS = [
    ("ph", "f"), ("f", "ph"), ("ck", "k"), ("c", "k"), ("k", "c"),
    ("s", "z"), ("qu", "kw"), ("x", "ks"), ("er", "a"), ("ou", "u"),
]


def leet_variants(s: str, strict: bool = False) -> list[str]:
    """Leet respellings of `s`.

    strict=True drops the identity variant, so the `leet` archetype can no
    longer emit an unmodified word. (2.0 returned the original inside the
    variant set, so ~26% of "leet" handles contained no leet at all.)
    """
    s = normalize_handle(s)
    variants = {s}
    for i, ch in enumerate(s):
        if ch in LEET:
            variants.add(s[:i] + LEET[ch] + s[i + 1:])
    for a, b in [("a", "4"), ("e", "3"), ("o", "0"), ("s", "5")]:
        if a in s:
            variants.add(s.replace(a, b))
    out = sorted(variants)
    if strict:
        out = [x for x in out if x != s]
    return out


def drop_vowels(s: str) -> str:
    s = normalize_handle(s)
    if len(s) <= 4:
        return s
    return s[0] + "".join(ch for ch in s[1:] if ch not in "aeiou")


def truncate(s: str, n: int) -> str:
    return normalize_handle(s)[:max(0, n)]


def deliberate_corruption(s: str, strict: bool = False) -> list[str]:
    """Period-plausible misspellings. strict=True excludes the input itself."""
    s = normalize_handle(s)
    out = {s}
    for a, b in PHONETIC_SWAPS:
        if a in s:
            out.add(s.replace(a, b))
    if s.endswith("s"):
        out.add(s[:-1] + "z")
    if len(s) > 6:
        out.add(s[:-1])  # clipped ending, the way handles get shortened in use
    result = sorted(x for x in out if x)
    if strict:
        result = [x for x in result if x != s]
    return result


def acronymize(terms: list[str]) -> str:
    letters = "".join(t[0] for t in terms if t)
    return normalize_handle(letters)


def combine(a: str, b: str, separator: str = "") -> str:
    a, b = normalize_handle(a), normalize_handle(b)
    return normalize_handle(a + separator + b)


def compound_is_degenerate(a: str, b: str) -> bool:
    """Reject 'echoecho', 'voidvoid', 'nodenode' and containment pairs.

    (2.0 had no such check and happily produced doubled halves.)
    """
    a, b = normalize_handle(a), normalize_handle(b)
    if not a or not b:
        return True
    if a == b:
        return True
    if a in b or b in a:
        return True
    # 'staticstatus' — heavy shared prefix reads as a typo, not a compound.
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= 3


def valid(handle: str, system: HandleSystem) -> tuple[bool, str]:
    """Return (ok, reason). 2.0 returned a bare bool, so nothing could report
    *why* a candidate was dropped and the rejection rate was invisible."""
    h = normalize_handle(handle)
    if not h:
        return False, "empty"
    if len(h) < system.min_length:
        return False, "too short"
    if len(h) > system.max_length:
        return False, "too long"
    for bad in system.forbidden:
        b = normalize_handle(bad)
        if b and b in h:
            return False, f"forbidden term '{bad}'"
    if not all(ch in system.allowed_chars for ch in h):
        return False, "disallowed character"
    if re.search(r"(.)\1\1", h):
        return False, "triple repeated character"
    if h[0] in "-_" or h[-1] in "-_":
        return False, "leading/trailing separator"
    if re.search(r"[-_]{2}", h):
        return False, "doubled separator"
    return True, ""


def is_valid(handle: str, system: HandleSystem) -> bool:
    return valid(handle, system)[0]


def weighted_choice(rng: random.Random, values, weights=None):
    if not values:
        return None
    if not weights:
        return rng.choice(values)
    if sum(weights) <= 0:
        return rng.choice(values)
    return rng.choices(values, weights=weights, k=1)[0]


def pick_term(rng: random.Random, terms: list[Term]) -> Term | None:
    if not terms:
        return None
    return weighted_choice(rng, terms, [max(0.0, t.weight) for t in terms])


def era_filter(terms: list[Term], year: int | None) -> list[Term]:
    if not year:
        return terms
    keep = [t for t in terms if t.since <= year <= t.until]
    return keep or terms


def synthesize_one(system: HandleSystem, kind: str, rng: random.Random,
                   year: int | None = None, seed_words: list[str] | None = None) -> Build | None:
    """Build a single candidate of the requested archetype.

    Returns None when the archetype cannot be built from this system's
    vocabulary, instead of silently degrading into a different archetype.
    """
    def P(*names) -> list[Term]:
        return era_filter(system.pool(*names), year)

    tech, abstract = P("technical", "crypto"), P("abstract")
    myth, scifi = P("mythology"), P("scifi")
    mundane = P("mundane", "bureaucratic", "organic")
    threat, cyber = P("threatening"), P("cyberpunk")
    phreak = P("phreak")

    def one(pool: list[Term], archetype: str) -> Build | None:
        t = pick_term(rng, pool)
        return Build(t.term, archetype, [t]) if t else None

    if kind == "technical":
        return one(tech + phreak, kind)
    if kind == "abstract":
        return one(abstract, kind)
    if kind == "mythological":
        return one(myth, kind)
    if kind == "scifi":
        return one(scifi, kind)
    if kind == "mundane":
        return one(mundane, kind)
    if kind == "threatening":
        return one(threat, kind)
    if kind == "ironic":
        return one([t for t in mundane if "irreverent" in t.tags or "mundane" in t.tags] or mundane, kind)

    if kind == "minimal":
        # 2.0 truncated to a random *preferred* length (up to 12), so "minimal"
        # routinely returned the whole word. Minimal now means minimal.
        source = pick_term(rng, tech + abstract + cyber)
        if not source:
            return None
        n = rng.randint(max(system.min_length, 3), max(system.min_length, 6))
        h = truncate(source.term, n)
        return Build(h, kind, [source], ["truncate"] if h != source.term else [])

    if kind == "compound":
        left_pool = tech + cyber + abstract
        right_pool = abstract + mundane + threat + myth
        for _ in range(12):
            a, b = pick_term(rng, left_pool), pick_term(rng, right_pool)
            if not a or not b or compound_is_degenerate(a.term, b.term):
                continue
            sep = rng.choice(system.separators) if (system.separators and rng.random() < 0.18) else ""
            return Build(combine(a.term, b.term, sep), kind, [a, b])
        return None

    if kind == "technical_myth":
        for _ in range(12):
            a, b = pick_term(rng, tech), pick_term(rng, myth)
            if a and b and not compound_is_degenerate(a.term, b.term):
                return Build(combine(a.term, b.term), kind, [a, b])
        return None

    if kind == "mundane_threat":
        for _ in range(12):
            a, b = pick_term(rng, mundane), pick_term(rng, threat)
            if a and b and not compound_is_degenerate(a.term, b.term):
                return Build(combine(a.term, b.term), kind, [a, b])
        return None

    if kind == "orthographic":
        source = pick_term(rng, tech + abstract + cyber + myth + phreak)
        if not source:
            return None
        variants = deliberate_corruption(source.term, strict=True)
        if not variants:
            return None  # nothing to corrupt; don't emit the clean word as "orthographic"
        return Build(rng.choice(variants), kind, [source], ["corrupt"])

    if kind == "leet":
        source = pick_term(rng, tech + abstract + cyber + threat)
        if not source:
            return None
        variants = leet_variants(source.term, strict=True)
        if not variants:
            return None
        return Build(rng.choice(variants), kind, [source], ["leet"])

    if kind == "phonetic":
        source = pick_term(rng, tech + abstract + myth + mundane)
        if not source:
            return None
        variants = [v for v in deliberate_corruption(source.term, strict=True) if len(v) >= len(source.term) - 1]
        if not variants:
            return None
        return Build(rng.choice(variants), kind, [source], ["phonetic"])

    if kind == "numeric":
        source = pick_term(rng, tech + abstract + cyber + threat)
        if not source:
            return None
        digits = system.digits or ["0", "1", "7", "13", "42", "64", "404", "451"]
        return Build(source.term + rng.choice(digits), kind, [source], ["numeric"])

    if kind == "prefix":
        source = pick_term(rng, tech + abstract + cyber)
        if not source or not system.prefixes:
            return None
        return Build(normalize_handle(rng.choice(system.prefixes) + source.term), kind, [source])

    if kind == "suffix":
        source = pick_term(rng, tech + abstract + cyber)
        if not source or not system.suffixes:
            return None
        return Build(normalize_handle(source.term + rng.choice(system.suffixes)), kind, [source])

    if kind == "acronym":
        pool = tech + abstract + cyber + myth
        n = rng.randint(3, 4)
        chosen = [pick_term(rng, pool) for _ in range(n)]
        chosen = [c for c in chosen if c]
        if len(chosen) < 3:
            return None
        h = acronymize([c.term for c in chosen])
        return Build(h, kind, chosen, ["acronym"])

    if kind == "seeded":
        seeds = [normalize_handle(w) for w in (seed_words or []) if normalize_handle(w)]
        if not seeds:
            return None
        base = rng.choice(seeds)
        partner = pick_term(rng, tech + abstract + cyber)
        mode = rng.random()
        if mode < 0.35 or not partner:
            return Build(base, kind, [Term(base, "seed", ("personal",), "writer-supplied seed word")], [])
        if compound_is_degenerate(base, partner.term):
            return Build(base, kind, [Term(base, "seed", ("personal",), "writer-supplied seed word")], [])
        order = rng.random() < 0.5
        h = combine(base, partner.term) if order else combine(partner.term, base)
        return Build(h, kind, [Term(base, "seed", ("personal",), "writer-supplied seed word"), partner], [])

    return one(tech + abstract + cyber + mundane, kind or "technical")


def generate_handle_pool(system: HandleSystem, count: int = 500, seed=None,
                         archetype: str | None = None, year: int | None = None,
                         seed_words: list[str] | None = None,
                         stats: dict | None = None) -> dict[str, Build]:
    rng = random.Random(seed)
    pool: dict[str, Build] = {}

    if archetype:
        if archetype not in ARCHETYPES:
            raise NameForgeError(f"unknown archetype '{archetype}'. Known: {', '.join(ARCHETYPE_NAMES)}")
        archetypes = [archetype]
    else:
        archetypes = system.enabled_archetypes()
    if not archetypes:
        archetypes = ["technical", "abstract", "compound"]

    weights = [system.archetype_weights.get(x, 1.0) for x in archetypes]
    rejected = Counter()
    attempts = 0
    budget = max(count * 40, 2000)

    while len(pool) < count and attempts < budget:
        attempts += 1
        kind = weighted_choice(rng, archetypes, weights)
        build = synthesize_one(system, kind, rng, year, seed_words)
        if build is None:
            rejected["unbuildable:" + kind] += 1
            continue
        h = normalize_handle(build.handle)
        ok, why = valid(h, system)
        if not ok:
            rejected[why] += 1
            continue
        build.handle = h
        pool.setdefault(h, build)

    if stats is not None:
        stats["attempts"] = attempts
        stats["rejected"] = dict(rejected.most_common(8))
        stats["requested"] = count
        stats["produced"] = len(pool)
    if len(pool) < count:
        warn(
            f"only {len(pool)} of {count} requested handles could be generated "
            f"({attempts} attempts). Widen the vocabulary, relax length limits, or lower --pool."
        )
    return pool


TRANSFORM_OPS = ("leet", "drop-vowels", "truncate", "corrupt", "numeric", "phonetic", "separator")


def transform_pool(pool: dict[str, Build], system: HandleSystem, seed=None,
                   max_variants: int = 3) -> dict[str, Build]:
    """Expand the pool with mutations, preserving each variant's provenance.

    2.0 tagged every mutation as "<archetype>+transform" and then looked that
    string up in the scoring tables, where it always missed — so two thirds of
    the pool scored with zero character resonance and no archetype bonuses.
    Provenance is now kept in Build.transforms and the archetype stays intact.
    """
    rng = random.Random(seed)
    result = dict(pool)
    ops = [op for op in system.transformations if op in TRANSFORM_OPS]
    unknown = [op for op in system.transformations if op not in TRANSFORM_OPS]
    if unknown:
        warn(f"ignoring unknown transformation(s): {', '.join(sorted(set(unknown)))}")
    if not ops:
        return result

    for base, build in list(pool.items()):
        chosen = rng.sample(ops, min(len(ops), rng.randint(0, 2)))
        # Corrupt+phonetic+leet in combination destroys the source word; keep
        # spelling mutations to one per handle.
        spelling = [o for o in chosen if o in ("corrupt", "phonetic", "leet")]
        if len(spelling) > 1:
            chosen = [o for o in chosen if o not in spelling[1:]]
        variants: set[str] = {base}
        for op in chosen:
            new: set[str] = set()
            for x in variants:
                if op == "leet":
                    new.update(leet_variants(x, strict=True)[:6] or [x])
                elif op == "drop-vowels":
                    new.add(drop_vowels(x))
                elif op == "truncate":
                    n = rng.choice([n for n in system.preferred_lengths if n < len(x)] or [len(x)])
                    new.add(truncate(x, n))
                elif op == "corrupt":
                    new.update(deliberate_corruption(x, strict=True)[:6] or [x])
                elif op == "phonetic":
                    new.update(deliberate_corruption(x, strict=True)[:4] or [x])
                elif op == "numeric":
                    new.add(x + rng.choice(system.digits or ["0", "1", "7", "13", "42"]))
                elif op == "separator":
                    # Only ever split between two source terms. Cutting a single
                    # word at a random index produced things like "uma-sc64".
                    seps = [c for c in system.separators if c] or ["_"]
                    cut = None
                    if len(build.sources) >= 2 and len(words(x)) == 1:
                        head = normalize_handle(build.sources[0].term)
                        if head and x.startswith(head) and len(x) > len(head) + 1:
                            cut = len(head)
                    new.add(x[:cut] + rng.choice(seps) + x[cut:] if cut else x)
                else:
                    new.add(x)
            variants = new or variants
        kept = 0
        for x in sorted(variants):
            if kept >= max_variants:
                break
            x = normalize_handle(x)
            if x in result:
                continue
            if not is_valid(x, system):
                continue
            result[x] = Build(x, build.archetype, list(build.sources), build.transforms + chosen)
            kept += 1
    return result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

TAG_ALIASES = {
    "technical": {"technical", "technicality", "computer", "computing", "engineer", "reverse", "coding", "lowlevel"},
    "mysterious": {"mysterious", "secretive", "enigmatic", "opaque", "occult", "elusive"},
    "irreverent": {"irreverent", "humorous", "absurd", "playful", "satirical", "funny", "deadpan"},
    "intelligent": {"intelligent", "brilliant", "academic", "analytical", "intellectual", "erudite", "curious"},
    "threatening": {"threatening", "dangerous", "violent", "ruthless", "intimidating", "menacing"},
    "minimal": {"minimal", "minimalist", "spartan", "simple", "terse", "compact"},
    "oldschool": {"oldschool", "old-school", "retro", "bbs", "irc", "warez", "phreak", "demoscene", "usenet"},
    "gothic": {"gothic", "melancholic", "macabre", "romantic", "morbid", "funereal"},
    "cyberpunk": {"cyberpunk", "punk", "dystopian", "corporate", "underground", "noir"},
    "rebellious": {"rebellious", "anarchic", "anti-authoritarian", "independent", "contrarian"},
    "literary": {"literary", "mythological", "philosophical", "poetic", "symbolic", "allusive"},
    "mundane": {"mundane", "banal", "ordinary", "domestic", "unremarkable", "bureaucratic"},
    "organic": {"organic", "biological", "decay", "fungal", "botanical"},
    "cryptographic": {"cryptographic", "crypto", "cypherpunk", "privacy", "paranoid"},
    "abstract": {"abstract", "conceptual"},
}

# Reverse index so "old-school" in a profile also activates the "oldschool"
# family. 2.0 only expanded when the canonical key itself appeared.
_ALIAS_TO_CANON = {}
for _canon, _members in TAG_ALIASES.items():
    for _m in _members:
        _ALIAS_TO_CANON.setdefault(_m, set()).add(_canon)


def expand_tags(items) -> set[str]:
    result: set[str] = set()
    for item in items or []:
        result.update(x for x in re.split(r"[,;/ ]+", fold(item)) if x)
    expanded = set(result)
    for token in result:
        for canon in _ALIAS_TO_CANON.get(token, ()):
            expanded.add(canon)
            expanded.update(TAG_ALIASES[canon])
    return {x for x in expanded if x}


def canonical_tags(items) -> set[str]:
    """Normalise tags to their canonical family names without expanding them
    into the full family (which would make nearly every handle match)."""
    out: set[str] = set()
    for item in items or []:
        tok = fold(item).strip()
        if not tok:
            continue
        out.add(tok)
        out.update(_ALIAS_TO_CANON.get(tok, ()))
    return out


def tag_hits(handle_tags: set[str], desired: set[str]) -> set[str]:
    return handle_tags & desired


def contains_element(handle: str, element: str, min_affix: int = 4, min_infix: int = 5) -> bool:
    """Does `handle` use `element` as a recognisable building block?

    A plain substring test is too crude — it flags "neon" for containing "neo".
    An element counts when it is a whole separator-delimited word, a prefix or
    suffix of at least `min_affix` characters, or a long enough substring that
    it cannot be coincidental ("darkphantomx" really does contain "phantom").
    """
    h, e = normalize_handle(handle), normalize_handle(element)
    if not h or not e:
        return False
    if e in words(h):
        return True
    if len(e) >= min_affix and (h.startswith(e) or h.endswith(e)):
        return True
    if len(e) >= min_infix and e in h:
        return True
    return False


def infer_sources(handle: str, system: HandleSystem) -> list[Term]:
    """Recover which lexicon terms a hand-written handle appears to contain."""
    h = normalize_handle(handle)
    found: list[Term] = []
    consumed = [False] * len(h)
    for term in sorted(system._index.values(), key=lambda t: -len(t.term)):
        if len(term.term) < 3:
            continue
        start = h.find(term.term)
        if start == -1:
            continue
        if any(consumed[start:start + len(term.term)]):
            continue
        for i in range(start, start + len(term.term)):
            consumed[i] = True
        found.append(term)
    return found


def score_handle(handle, archetype, char: Character, system: HandleSystem,
                 cast=None, build: Build | None = None) -> HandleCandidate:
    cast = cast or []
    h = normalize_handle(handle)
    base_archetype = (archetype or "unknown").split("+", 1)[0]
    meta = ARCHETYPES.get(base_archetype, {})
    desired = expand_tags(list(char.desired_impression) + list(char.personality) + list(char.interests))
    rationale: list[str] = []
    warnings: list[str] = []
    penalties: list[tuple[str, float]] = []

    sources = build.sources if build else infer_sources(h, system)
    transforms = list(build.transforms) if build else []
    handle_tags = set(meta.get("tags", []))
    for t in sources:
        handle_tags.update(t.tags)
    handle_tags = canonical_tags(handle_tags)

    year = char.first_online_year or (char.era_years[1] or None)

    # 1. Scene fit -----------------------------------------------------------
    scene = 0.50
    culture = (char.culture or "").lower()
    if any(k in culture for k in ("hacker", "underground", "cypherpunk", "phreak", "warez", "demoscene")):
        scene += 0.15
    if sources:
        scene += 0.10  # built from scene vocabulary rather than arbitrary letters
    if "oldschool" in desired and base_archetype in {"technical", "minimal", "orthographic", "ironic", "leet", "phonetic"}:
        scene += 0.12
    if char.profession and any(w in char.profession.lower() for w in ("engineer", "programmer", "reverse", "analyst", "sysadmin", "operator")):
        if "technical" in handle_tags:
            scene += 0.08
    scene = min(scene, 1.0)

    # 2. Era fit -------------------------------------------------------------
    lo, hi = meta.get("era", (0, 9999))
    era_fit = 0.7
    if year:
        if lo <= year <= hi:
            era_fit = 0.95
        elif year > hi:
            era_fit = 0.45
            warnings.append(
                f"The {base_archetype} archetype reads as dated after ~{hi}; this character is placed around {year}."
            )
        else:
            era_fit = 0.40
            warnings.append(f"The {base_archetype} archetype is anachronistic before ~{lo} (character year ~{year}).")
        off = [t for t in sources if t.since > year or t.until < year]
        if off:
            era_fit = max(0.0, era_fit - 0.25)
            warnings.append("Vocabulary outside the character's period: " + ", ".join(t.term for t in off[:3]) + ".")
    elif sources:
        era_fit = 0.75

    # 3. Authenticity --------------------------------------------------------
    generic_terms = {normalize_handle(x) for x in (system.generic_branding or [])} or {
        "hacker", "cyber", "cyberwarrior", "hackmaster", "elitehacker", "anonymous", "darkweb"
    }
    hit_generic = sorted(x for x in generic_terms if x and contains_element(h, x))
    authenticity = 0.72
    if hit_generic:
        penalties.append((f"generic branding: {', '.join(hit_generic)}", 0.30))
        warnings.append("Generic cyber/hacker branding; this reads as a fictional stereotype rather than an organic handle.")
    # `overused` was loaded by 2.0 and then never consulted anywhere.
    hit_overused = sorted({normalize_handle(x) for x in system.overused if contains_element(h, x)})
    if hit_overused:
        penalties.append((f"overused element(s): {', '.join(hit_overused)}", min(0.24, 0.09 * len(hit_overused))))
    if base_archetype in {"technical", "ironic", "orthographic", "minimal", "compound", "mundane", "phonetic", "seeded"}:
        authenticity += 0.12
    if any(t.register == "insider" for t in sources):
        authenticity += 0.10
        rationale.append("Uses insider vocabulary a casual observer would not recognise.")
    if any(t.register == "pop" for t in sources):
        authenticity -= 0.08
    if len(h) <= 12:
        authenticity += 0.05
    authenticity = max(0.0, min(1.0, authenticity))

    # 4. Memorability --------------------------------------------------------
    center = sum(system.preferred_lengths) / len(system.preferred_lengths) if system.preferred_lengths else 7
    memorability = 0.35 + 0.40 * bell(len(h), center, 3.2)  # smooth, not a cliff
    if 1 <= len(words(h)) <= 2:
        memorability += 0.10
    uniq_ratio = len(set(h)) / max(1, len(h))
    memorability += 0.15 * min(1.0, max(0.0, (uniq_ratio - 0.45) / 0.45))
    if digit_ratio(h) > 0.35:
        memorability -= 0.10
    memorability = max(0.0, min(1.0, memorability))

    # 5. Legibility: is the underlying word still readable through the mutation?
    if sources:
        legibility = max(combined_similarity(h, t.term) for t in sources)
        # A handle built by joining several terms is legible by construction.
        if len(sources) > 1:
            legibility = max(legibility, 0.72)
        if legibility < 0.55 and transforms:
            warnings.append("Mutation has buried the source word; the joke no longer survives being read.")
    else:
        legibility = 0.70  # invented rather than assembled; neither a plus nor a minus
    if sources and re.search(r"(.)\1", h) and not any(re.search(r"(.)\1", t.term) for t in sources):
        legibility -= 0.20  # a doubled letter the source never had reads as a typo
    legibility = max(0.0, min(1.0, legibility))

    # 6. Speakability --------------------------------------------------------
    speakability = pronounceability(h)
    if speakability < 0.35:
        warnings.append("Hard to say out loud; awkward if characters must speak this alias in dialogue.")

    # 7. Character resonance -------------------------------------------------
    hits = tag_hits(handle_tags, desired)
    if not desired:
        resonance = 0.60
    else:
        # Coverage of what the writer asked for, saturating at three matches.
        resonance = min(1.0, len(hits) / 3.0)
        if hits:
            rationale.append("Resonates with: " + ", ".join(sorted(hits)[:4]) + ".")
    if char.contradiction and not hits:
        resonance = max(resonance, 0.35)

    # 8. Aesthetic fit -------------------------------------------------------
    aesthetic = 0.55
    if desired & TAG_ALIASES["gothic"] and base_archetype in {"mythological", "abstract", "scifi"}:
        aesthetic += 0.18
    if "cyberpunk" in desired and base_archetype in {"technical", "compound", "orthographic", "numeric", "scifi"}:
        aesthetic += 0.15
    if "irreverent" in desired and base_archetype in {"ironic", "mundane_threat", "orthographic", "mundane", "phonetic"}:
        aesthetic += 0.18
    if "minimal" in desired and len(h) <= 6:
        aesthetic += 0.12
    if "cryptographic" in handle_tags and "cryptographic" in desired:
        aesthetic += 0.10
    aesthetic = min(1.0, aesthetic)

    # 9. Interface usability -------------------------------------------------
    usability = 1.0
    usability -= 0.10 * max(0, len(h) - 12) / 3.0
    seps = h.count("_") + h.count("-")
    if seps > 1:
        usability -= 0.10 * (seps - 1)
    ambiguous = sum(1 for c in h if c in "l1i0o")
    if ambiguous >= 3:
        usability -= 0.08
        warnings.append("Contains several visually ambiguous characters (l/1/i/0/o); easy to mistype or misread on the page.")
    if digit_ratio(h) > 0.4:
        usability -= 0.12
    usability = max(0.0, min(1.0, usability))

    # 10. Cast collision ------------------------------------------------------
    maxsim, collision = 0.0, ""
    for other in cast:
        if other.id == char.id:
            continue
        for existing in [other.full_name] + list(other.aliases) + list(other.handle_history):
            if not existing:
                continue
            sim = combined_similarity(h, existing)
            if sim > maxsim:
                maxsim, collision = sim, existing
    uniqueness = max(0.0, 1 - maxsim)
    if maxsim >= 0.82:
        warnings.append(f"Strong cast collision with '{collision}' ({maxsim:.0%}); readers will confuse them.")
    elif maxsim >= 0.68:
        warnings.append(f"Moderate cast similarity with '{collision}' ({maxsim:.0%}).")
    # Also check the character's own earlier handles: echoing them is a feature.
    for old in char.handle_history:
        if old and combined_similarity(h, old) >= 0.55:
            rationale.append(f"Echoes this character's earlier handle '{old}', suggesting continuity.")
            break

    # 11. Contradiction ------------------------------------------------------
    contradiction = 0.50
    if char.contradiction:
        contradiction = 0.72
        if base_archetype == "ironic":
            contradiction = 0.95
            rationale.append("Ironic handle deliberately conflicts with the character's surface identity.")
        elif base_archetype in {"mundane", "minimal"}:
            contradiction = 0.88
            rationale.append("An unremarkable handle can conceal an otherwise dramatic character.")
        elif base_archetype == "threatening":
            contradiction = 0.35
            rationale.append("Overt menace states the character's threat instead of concealing it.")
        else:
            rationale.append("Contradiction field is active; the handle need not describe the character literally.")

    # 12. Old-school signal --------------------------------------------------
    oldschool = 0.50
    if base_archetype in {"orthographic", "leet", "numeric", "phonetic", "acronym"}:
        oldschool = 0.88
    if any("oldschool" in t.tags for t in sources):
        oldschool = max(oldschool, 0.80)
    if "oldschool" in desired:
        oldschool = min(1.0, oldschool + 0.12)
    elif oldschool > 0.8 and desired:
        oldschool -= 0.15  # period styling nobody asked for

    # -- writer's explicit avoid list ---------------------------------------
    for bad in char.avoid:
        b = normalize_handle(bad)
        if b and (b in h):
            penalties.append((f"on this character's avoid list: '{bad}'", 0.45))
            warnings.append(f"Contains '{bad}', which this character profile lists under 'avoid'.")

    components = {
        "scene_fit": scene,
        "legibility": legibility,
        "era_fit": era_fit,
        "authenticity": authenticity,
        "memorability": memorability,
        "speakability": speakability,
        "character_resonance": resonance,
        "aesthetic_fit": aesthetic,
        "interface_usability": usability,
        "uniqueness": uniqueness,
        "contradiction_value": contradiction,
        "oldschool_signal": oldschool,
    }
    weights = dict(DEFAULT_SCORE_WEIGHTS)
    for k, v in (system.score_weights or {}).items():
        if k not in weights:
            warn(f"score_weights: ignoring unknown component '{k}'")
            continue
        weights[k] = float(v)

    denom = sum(weights[k] for k in components) or 1.0
    base_total = sum(components[k] * weights[k] for k in components) / denom

    # Penalties are multiplicative and reported separately. In 2.0 the generic
    # penalty was subtracted from authenticity *and* added as a negative-weight
    # component whose |weight| stayed in the denominator, so a flawless handle
    # could never exceed ~87/100 and the penalty was counted twice.
    penalty_total = min(0.7, sum(p for _, p in penalties))
    total = 100 * base_total * (1 - penalty_total)
    total = max(0.0, min(100.0, total))

    if meta.get("note"):
        rationale.append(meta["note"])
    glosses = [f"{t.term}: {t.gloss}" for t in sources if t.gloss]
    if transforms:
        rationale.append("Transforms applied: " + ", ".join(dict.fromkeys(transforms)) + ".")
    rationale.append(f"Archetype: {archetype} | length {len(h)} | entropy {entropy_score(h):.0%}")

    return HandleCandidate(
        handle=h,
        archetype=archetype,
        score=round(total, 2),
        components={k: round(v * 10, 2) for k, v in components.items()},
        warnings=warnings,
        rationale=rationale,
        sources=[t.term for t in sources],
        transforms=list(dict.fromkeys(transforms)),
        tags=sorted(handle_tags & (desired | set(meta.get("tags", [])))) or sorted(handle_tags)[:6],
        gloss="; ".join(glosses),
        penalties=[f"{label} (-{amount:.0%})" for label, amount in penalties],
    )


DEFAULT_SCORE_WEIGHTS = {
    "scene_fit": 2.0,
    "legibility": 2.0,
    "era_fit": 1.5,
    "authenticity": 3.0,
    "memorability": 3.0,
    "speakability": 1.5,
    "character_resonance": 3.0,
    "aesthetic_fit": 2.0,
    "interface_usability": 2.0,
    "uniqueness": 2.0,
    "contradiction_value": 2.0,
    "oldschool_signal": 1.0,
}


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def diversify(ranked: list[HandleCandidate], per_archetype: int | None) -> list[HandleCandidate]:
    """Cap how many results a single archetype may occupy.

    Without this, one high-weight archetype swamps the whole shortlist and the
    writer never sees the alternatives.
    """
    if not per_archetype or per_archetype < 1:
        return ranked
    seen = Counter()
    out = []
    for c in ranked:
        k = c.base_archetype
        if seen[k] >= per_archetype:
            continue
        seen[k] += 1
        out.append(c)
    return out


def render_table(rows: list[HandleCandidate], verbose: bool) -> str:
    buf = io.StringIO()
    for i, x in enumerate(rows, 1):
        line = f"{i:>3}. {pad(paint(x.handle, T.CYAN), 22)} {x.score:5.1f}/100  [{x.archetype}]"
        print(line, file=buf)
        if x.gloss:
            print("     " + paint(x.gloss, T.DIM), file=buf)
        if verbose:
            print("     " + " | ".join(f"{k}={v / 10:.2f}" for k, v in x.components.items()), file=buf)
            if x.sources:
                print(f"     source: {', '.join(x.sources)}", file=buf)
            for r in x.rationale:
                print("     + " + r, file=buf)
            for p in x.penalties:
                print("     " + paint("- " + p, T.MAGENTA), file=buf)
            for w in x.warnings:
                print("     " + paint("! " + w, T.YELLOW), file=buf)
    return buf.getvalue()


def render_markdown(rows: list[HandleCandidate], char: Character) -> str:
    buf = io.StringIO()
    print(f"# Handle shortlist — {char.id}\n", file=buf)
    by_arch: dict[str, list[HandleCandidate]] = defaultdict(list)
    for x in rows:
        by_arch[x.base_archetype].append(x)
    for arch in sorted(by_arch, key=lambda a: -max(c.score for c in by_arch[a])):
        note = ARCHETYPES.get(arch, {}).get("note", "")
        print(f"## {arch}\n", file=buf)
        if note:
            print(f"*{note}*\n", file=buf)
        for x in by_arch[arch]:
            bits = [f"**{x.handle}** — {x.score:.0f}/100"]
            if x.gloss:
                bits.append(f"({x.gloss})")
            print("- " + " ".join(bits), file=buf)
            for w in x.warnings:
                print(f"  - ⚠ {w}", file=buf)
        print("", file=buf)
    return buf.getvalue()


def render_csv(rows: list[HandleCandidate]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    keys = list(rows[0].components) if rows else []
    w.writerow(["handle", "archetype", "score", "sources", "transforms", "tags", "warnings"] + keys)
    for x in rows:
        w.writerow([
            x.handle, x.archetype, x.score, "|".join(x.sources), "|".join(x.transforms),
            "|".join(x.tags), " ".join(x.warnings),
        ] + [x.components[k] for k in keys])
    return buf.getvalue()


def emit(rows: list[HandleCandidate], args, char: Character) -> None:
    fmt = getattr(args, "format", "table")
    if fmt == "table":
        print(paint(f"UNDERGROUND HANDLE CANDIDATES — {char.id}", T.BOLD))
        print("─" * 88)
        print(render_table(rows, getattr(args, "verbose", False)), end="")
    elif fmt == "md":
        print(render_markdown(rows, char), end="")
    elif fmt == "csv":
        print(render_csv(rows), end="")
    elif fmt == "json":
        print(json.dumps([asdict(x) for x in rows], ensure_ascii=False, indent=2))

    out = getattr(args, "output", None)
    if out:
        path = Path(out)
        if path.suffix.lower() == ".csv":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_csv(rows), encoding="utf-8")
        elif path.suffix.lower() == ".md":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_markdown(rows, char), encoding="utf-8")
        else:
            save_json(path, {
                "nameforge_version": VERSION,
                "character": char.id,
                "seed": getattr(args, "seed", None),
                "candidates": [asdict(x) for x in rows],
            })
        print(paint(f"\nSaved: {path}", T.GREEN), file=sys.stderr)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).resolve().parent


def cmd_init(args):
    root = Path(args.path).resolve()
    for d in ("profiles", "characters", "projects"):
        (root / d).mkdir(parents=True, exist_ok=True)

    copied = 0
    for sub in ("profiles", "characters"):
        src = TEMPLATE_DIR / sub
        if not src.is_dir():
            continue
        for p in sorted(src.glob("*.json")):
            dest = root / sub / p.name
            if dest.exists() and not args.force:
                continue
            dest.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1

    if not copied and not any((root / "profiles").glob("*.json")):
        # Fallback when nameforge.py was copied out of its project directory.
        save_json(root / "profiles/underground-character.json", asdict(Character(
            id="forum-operator",
            era="1998-2012",
            first_online_year=2001,
            culture="hacker-underground",
            personality=["technical", "irreverent", "secretive", "intelligent"],
            desired_impression=["technical", "oldschool", "mysterious", "irreverent"],
            contradiction="More dangerous and knowledgeable than the handle suggests.",
            naming_system="underground-hacker-handle",
        )))
        warn("template lexicon not found next to nameforge.py; wrote a minimal profile only.")

    print(paint(f"Initialized underground NameForge project: {root}", T.GREEN))
    print(f"  profiles/   {len(list((root / 'profiles').glob('*.json')))} file(s)")
    print(f"  characters/ {len(list((root / 'characters').glob('*.json')))} file(s)")
    print("\nNext:")
    print(f"  cd {root}")
    print("  nameforge generate --profile profiles/underground-character.json \\")
    print("      --system profiles/underground-hacker-handle.json --top 25 --seed 1337 -v")


def _load_pair(args):
    char = load_character(Path(args.profile))
    system = load_system(Path(args.system))
    cast = cast_load(Path(args.cast)) if getattr(args, "cast", None) else []
    if char.naming_system and system.id and char.naming_system != system.id:
        warn(f"profile expects naming system '{char.naming_system}' but '{system.id}' was supplied.")
    return char, system, cast


def cmd_generate(args):
    char, system, cast = _load_pair(args)
    if args.avoid:
        char.avoid = list(char.avoid) + list(args.avoid)
    year = args.year or char.first_online_year or (char.era_years[1] or None)
    seed_words = list(char.seed_words) + list(args.seed_word or [])

    stats: dict = {}
    pool = generate_handle_pool(system, args.pool, args.seed, args.archetype, year, seed_words, stats)
    if not args.no_transform:
        pool = transform_pool(pool, system, args.seed)

    ranked = [score_handle(b.handle, b.archetype, char, system, cast, b) for b in pool.values()]
    if args.min_score:
        ranked = [x for x in ranked if x.score >= args.min_score]
    # Deterministic ordering: score, then handle, so equal scores never shuffle
    # between runs with the same seed.
    ranked.sort(key=lambda x: (-x.score, x.handle))
    ranked = diversify(ranked, args.per_archetype)
    rows = ranked[: args.top]

    if args.stats:
        print(paint("POOL STATISTICS", T.BOLD), file=sys.stderr)
        print(f"  generated {stats.get('produced', 0)} base handles in {stats.get('attempts', 0)} attempts", file=sys.stderr)
        print(f"  after transforms: {len(pool)}   scored: {len(ranked)}", file=sys.stderr)
        if stats.get("rejected"):
            print("  top rejection reasons: " + ", ".join(f"{k} x{v}" for k, v in stats["rejected"].items()), file=sys.stderr)
        spread = len({round(x.score, 2) for x in ranked})
        print(f"  distinct scores: {spread} across {len(ranked)} candidates", file=sys.stderr)

    if not rows:
        print(paint("No candidates survived filtering. Try lowering --min-score or widening the vocabulary.", T.YELLOW))
        return
    emit(rows, args, char)

    if not args.per_archetype and len(rows) >= 8:
        top_arch, n = Counter(x.base_archetype for x in rows).most_common(1)[0]
        if n > len(rows) * 0.5:
            print(paint(
                f"\n{n}/{len(rows)} results are '{top_arch}' — this profile's desired_impression favours it. "
                f"Add --per-archetype 3 to see the alternatives.", T.DIM), file=sys.stderr)


def cmd_score(args):
    char, system, cast = _load_pair(args)
    path = Path(args.names)
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            handle, archetype = line.split("\t", 1)
            archetype = archetype.strip() or "unknown"
        else:
            handle, archetype = line, "unknown"
        handle = handle.strip()
        if archetype != "unknown" and archetype not in ARCHETYPES:
            warn(f"{path.name}:{lineno}: unknown archetype '{archetype}'; scoring as 'unknown'.")
            archetype = "unknown"
        norm = normalize_handle(handle)
        if not norm:
            warn(f"{path.name}:{lineno}: '{handle}' normalises to nothing; skipped.")
            continue
        ok, why = valid(norm, system)
        cand = score_handle(norm, archetype, char, system, cast)
        if not ok:
            cand.warnings.insert(0, f"Violates the handle system: {why}.")
            cand.score = round(cand.score * 0.6, 2)
        rows.append(cand)
    rows.sort(key=lambda x: (-x.score, x.handle))
    if not rows:
        print(paint("No scorable handles found in the input file.", T.YELLOW))
        return
    emit(rows, args, char)


def cmd_analyze(args):
    h = normalize_handle(args.handle)
    if not h:
        raise NameForgeError(f"'{args.handle}' contains no usable characters")
    print(f"Handle:          {args.handle}")
    print(f"Normalized:      {h}")
    print(f"Length:          {len(h)}")
    print(f"Words:           {words(h)}")
    print(f"Unique chars:    {len(set(h))}/{len(h)}")
    print(f"Entropy score:   {entropy_score(h):.0%}")
    print(f"Speakability:    {pronounceability(h):.0%}")
    print(f"Digit ratio:     {digit_ratio(h):.0%}")
    print(f"Has separator:   {'yes' if any(x in h for x in '_-') else 'no'}")
    print(f"Leet variants:   {', '.join(leet_variants(h, strict=True)[:8]) or '—'}")
    print(f"Corruptions:     {', '.join(deliberate_corruption(h, strict=True)[:8]) or '—'}")
    print(f"Vowel-dropped:   {drop_vowels(h)}")
    if args.system:
        system = load_system(Path(args.system))
        ok, why = valid(h, system)
        print(f"System '{system.id}': {'valid' if ok else 'INVALID — ' + why}")
        found = infer_sources(h, system)
        if found:
            print("Recognised vocabulary:")
            for t in found:
                print(f"  {t.term:14} [{t.pool}] {t.gloss}")
        else:
            print("Recognised vocabulary: none — reads as invented rather than assembled.")


def cmd_cast(args):
    cast = cast_load(Path(args.cast))
    if not cast:
        print(paint("No character files found.", T.YELLOW))
        return
    entries = []
    for x in cast:
        for a in list(x.aliases) + list(x.handle_history):
            if a:
                entries.append((a, x.id))
    pairs = []
    for i, (a, aid) in enumerate(entries):
        for b, bid in entries[i + 1:]:
            if aid == bid:
                continue
            sim = combined_similarity(a, b)
            if sim >= args.threshold:
                pairs.append((sim, aid, a, bid, b))
    pairs.sort(key=lambda t: (-t[0], t[1], t[3]))
    print(paint("UNDERGROUND HANDLE COLLISION REPORT", T.BOLD))
    print("─" * 88)
    print(f"{len(cast)} characters, {len(entries)} aliases, threshold {args.threshold:.0%}")
    # First-letter crowding is the collision readers actually notice.
    initials = Counter(a[0] for a, _ in entries if a)
    crowded = [f"{c}×{n}" for c, n in initials.most_common(3) if n >= 3]
    if crowded:
        print(paint(f"Initial-letter crowding: {', '.join(crowded)}", T.YELLOW))
    if not pairs:
        print(paint("No significant alias collisions detected.", T.GREEN))
        return
    for sim, aid, a, bid, b in pairs:
        level = "HIGH" if sim >= 0.82 else "MEDIUM"
        color = T.RED if sim >= 0.82 else T.YELLOW
        print(f"{paint(pad(level, 6), color)} {sim:.0%}  {aid}:{a}  <->  {bid}:{b}")


def cmd_system(args):
    s = load_system(Path(args.system))
    print(paint(f"NAMING SYSTEM: {s.id}", T.BOLD))
    print(s.description)
    print("\nArchetypes (weight):")
    for name in s.enabled_archetypes():
        w = s.archetype_weights.get(name, 1.0)
        meta = ARCHETYPES.get(name, {})
        print(f"  {pad(name, 16)} {w:>4.1f}  {meta.get('note', '')}")
    print("\nVocabulary pools:")
    total = 0
    for pool_name in POOL_KEYS:
        terms = s.pools.get(pool_name, [])
        total += len(terms)
        if not terms:
            continue
        glossed = sum(1 for t in terms if t.gloss)
        print(f"  {pad(pool_name, 16)} {len(terms):>4} terms  ({glossed} glossed)")
    print(f"  {pad('TOTAL', 16)} {total:>4} terms")
    print(f"\nLength range:    {s.min_length}-{s.max_length}")
    print("Preferred:       " + ", ".join(map(str, s.preferred_lengths)))
    print("Transformations: " + (", ".join(s.transformations) or "—"))
    print(f"Forbidden:       {len(s.forbidden)} | Overused: {len(s.overused)}")


def cmd_doctor(args):
    """Validate a system file and report data-quality problems."""
    s = load_system(Path(args.system))
    problems, notes = [], []

    for pool_name, terms in s.pools.items():
        raw = getattr(s, POOL_KEYS[pool_name], []) or []
        raw_words = [(x if isinstance(x, str) else x.get("term", "")).strip().lower() for x in raw]
        dupes = [w for w, n in Counter(raw_words).items() if w and n > 1]
        if dupes:
            problems.append(f"{pool_name}: duplicate entries {sorted(dupes)} (they bias random selection)")
        for t in terms:
            bad = [c for c in normalize_handle(t.term) if c not in s.allowed_chars]
            if bad:
                problems.append(f"{pool_name}: '{t.term}' contains characters outside allowed_chars")
            if len(t.term) > s.max_length:
                problems.append(f"{pool_name}: '{t.term}' is longer than max_length and can never be used alone")

    seen: dict[str, list[str]] = defaultdict(list)
    for pool_name, terms in s.pools.items():
        for t in terms:
            seen[t.term].append(pool_name)
    cross = {w: p for w, p in seen.items() if len(p) > 1}
    if cross:
        notes.append(f"{len(cross)} term(s) appear in more than one pool: " +
                     ", ".join(f"{w} ({'/'.join(p)})" for w, p in list(cross.items())[:6]))

    forb = {normalize_handle(x) for x in s.forbidden}
    for w, pools in seen.items():
        if any(f and f in w for f in forb):
            problems.append(f"'{w}' in {'/'.join(pools)} contains a forbidden substring and can never pass validation")
    over = {normalize_handle(x) for x in s.overused}
    hits = [w for w in seen if any(o and contains_element(w, o) for o in over)]
    if hits:
        notes.append(f"{len(hits)} vocabulary term(s) overlap the 'overused' list and will be penalised: " +
                     ", ".join(sorted(hits)[:8]))
    for p in s.prefixes + s.suffixes:
        if any(o and contains_element(p, o) for o in over):
            notes.append(f"affix '{p}' is on the overused list; every handle built from it loses points")

    glossed = sum(1 for terms in s.pools.values() for t in terms if t.gloss)
    total = sum(len(v) for v in s.pools.values())
    tagged = sum(1 for terms in s.pools.values() for t in terms if t.tags)
    dated = sum(1 for terms in s.pools.values() for t in terms if t.since != 1970 or t.until != 9999)

    for name in ARCHETYPES:
        if name == "seeded":
            continue  # depends on the character's seed_words, not on the system
        if name in s.enabled_archetypes():
            rng = random.Random(0)
            ok = any(synthesize_one(s, name, rng) for _ in range(40))
            if not ok:
                problems.append(f"archetype '{name}' is enabled but cannot be built from this vocabulary")

    print(paint(f"SYSTEM CHECK: {s.id}", T.BOLD))
    print("─" * 88)
    print(f"terms: {total}   glossed: {glossed} ({glossed / max(1, total):.0%})   "
          f"tagged: {tagged} ({tagged / max(1, total):.0%})   period-dated: {dated} ({dated / max(1, total):.0%})")
    for p in problems:
        print(paint("  ERROR  ", T.RED) + p)
    for n in notes:
        print(paint("  NOTE   ", T.YELLOW) + n)
    if not problems:
        print(paint("  No blocking problems found.", T.GREEN))
    return 1 if problems and args.strict else 0


def cmd_export(args):
    char = load_character(Path(args.profile))
    system = load_system(Path(args.system))
    obj = {"nameforge_version": VERSION, "character": asdict(char), "handle_system": system.to_json()}
    save_json(Path(args.output), obj)
    print(paint(f"Exported: {args.output}", T.GREEN))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(prog="nameforge", description="Offline underground Internet-handle workbench.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colour even on a terminal.")
    p.add_argument("--color", action="store_true", help="Force ANSI colour even when piping.")
    sp = p.add_subparsers(dest="command", required=True)

    x = sp.add_parser("init", help="Create an underground-handle project.")
    x.add_argument("path", nargs="?", default="nameforge-underground")
    x.add_argument("--force", action="store_true", help="Overwrite existing template files.")
    x.set_defaults(func=cmd_init)

    def add_output_flags(sub):
        sub.add_argument("--format", choices=["table", "json", "csv", "md"], default="table")
        sub.add_argument("--verbose", "-v", action="store_true")
        sub.add_argument("--output", help="Write results to a file (.json, .csv or .md).")

    x = sp.add_parser("generate", help="Generate, transform and rank underground handles.")
    x.add_argument("--profile", required=True)
    x.add_argument("--system", required=True)
    x.add_argument("--cast", help="Character file or directory to check collisions against.")
    x.add_argument("--pool", type=int, default=1000, help="Base handles to synthesize before transforms.")
    x.add_argument("--top", type=int, default=30)
    x.add_argument("--seed", type=int, help="Reproducible output for the same inputs.")
    x.add_argument("--archetype", choices=ARCHETYPE_NAMES)
    x.add_argument("--per-archetype", type=int, help="Cap results per archetype so one style cannot swamp the list.")
    x.add_argument("--min-score", type=float, default=0.0)
    x.add_argument("--year", type=int, help="Override the year used for period plausibility.")
    x.add_argument("--seed-word", action="append", help="Extra personal vocabulary (repeatable).")
    x.add_argument("--avoid", action="append", help="Reject handles containing this substring (repeatable).")
    x.add_argument("--no-transform", action="store_true", help="Skip the mutation pass.")
    x.add_argument("--stats", action="store_true", help="Print pool diagnostics to stderr.")
    add_output_flags(x)
    x.set_defaults(func=cmd_generate)

    x = sp.add_parser("score", help="Score a newline-separated handle list. Optional TAB + archetype.")
    x.add_argument("--profile", required=True)
    x.add_argument("--system", required=True)
    x.add_argument("--names", required=True)
    x.add_argument("--cast")
    add_output_flags(x)
    x.set_defaults(func=cmd_score)

    x = sp.add_parser("analyze", help="Analyze one handle.")
    x.add_argument("handle")
    x.add_argument("--system", help="Also validate against a handle system and identify vocabulary.")
    x.set_defaults(func=cmd_analyze)

    x = sp.add_parser("cast-check", help="Find collisions among aliases in a cast.")
    x.add_argument("cast")
    x.add_argument("--threshold", type=float, default=0.68)
    x.set_defaults(func=cmd_cast)

    x = sp.add_parser("system", help="Inspect a handle system.")
    x.add_argument("--system", required=True)
    x.set_defaults(func=cmd_system)

    x = sp.add_parser("doctor", help="Validate a handle system and report data-quality problems.")
    x.add_argument("--system", required=True)
    x.add_argument("--strict", action="store_true", help="Exit non-zero when problems are found.")
    x.set_defaults(func=cmd_doctor)

    x = sp.add_parser("export", help="Export a character + handle system snapshot.")
    x.add_argument("--profile", required=True)
    x.add_argument("--system", required=True)
    x.add_argument("--output", required=True)
    x.set_defaults(func=cmd_export)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.no_color and args.color:
        parser.error("--color and --no-color are mutually exclusive")
    set_color(args.color or (not args.no_color and sys.stdout.isatty()))

    if args.command != "init" and getattr(args, "format", "table") == "table" and sys.stdout.isatty():
        banner()

    try:
        rc = args.func(args)
        return rc or 0
    except FileNotFoundError as e:
        print(paint(f"ERROR: file not found: {e.filename}", T.RED), file=sys.stderr)
        return 2
    except NameForgeError as e:
        print(paint(f"ERROR: {e}", T.RED), file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError) as e:
        print(paint(f"ERROR: {type(e).__name__}: {e}", T.RED), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
