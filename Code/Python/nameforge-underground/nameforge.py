#!/usr/bin/env python3
"""
NameForge - Underground Handle Workbench
----------------------------------------
Offline CLI for designing fictional Internet aliases inspired by:
BBS, IRC, warez, phreak, cypherpunk, hacker and underground forum cultures.

This is a creative-writing tool. It generates fictional handles and evaluates
their stylistic properties; it is not an identity-generation or impersonation tool.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from itertools import product

APP = "NameForge"
VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------

class T:
    RESET="\033[0m"; DIM="\033[2m"; BOLD="\033[1m"
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
    CYAN="\033[36m"; MAGENTA="\033[35m"; WHITE="\033[37m"

def paint(s, color, enabled=True):
    return f"{color}{s}{T.RESET}" if enabled else s

def banner(color=True):
    print(paint(r"""
 _   _                    _____
| \ | | __ _ _ __ ___   |  ___|__  _ __ __ _  ___
|  \| |/ _` | '_ ` _ \  | |_ / _ \| '__/ _` |/ _ \
| |\  | (_| | | | | | | |  _| (_) | | | (_| |  __/
|_| \_|\__,_|_| |_| |_| |_|  \___/|_|  \__, |\___|
                                        |___/
       UNDERGROUND HANDLE WORKBENCH
""".rstrip(), T.CYAN, color))
    print()

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

    @property
    def full_name(self):
        return " ".join(x for x in [self.given_name, self.middle_name, self.family_name] if x).strip()

    @property
    def searchable_text(self):
        return " ".join([
            self.era, self.geography, self.culture, self.generation,
            self.social_class, self.family_structure, self.religion,
            self.profession, " ".join(self.personality),
            self.public_identity, self.private_identity, self.contradiction,
            self.narrative_role, " ".join(self.desired_impression), self.notes
        ]).lower()

@dataclass
class HandleSystem:
    id: str
    description: str = ""
    archetypes: dict[str, list[str]] = field(default_factory=dict)
    technical_terms: list[str] = field(default_factory=list)
    abstract_terms: list[str] = field(default_factory=list)
    mythology: list[str] = field(default_factory=list)
    scifi: list[str] = field(default_factory=list)
    mundane: list[str] = field(default_factory=list)
    threatening: list[str] = field(default_factory=list)
    cyberpunk: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)
    separators: list[str] = field(default_factory=list)
    digits: list[str] = field(default_factory=list)
    allowed_chars: str = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    max_length: int = 18
    min_length: int = 3
    preferred_lengths: list[int] = field(default_factory=lambda: [4,5,6,7,8,9,10,11,12])
    transformations: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    overused: list[str] = field(default_factory=list)
    archetype_weights: dict[str, float] = field(default_factory=dict)

@dataclass
class HandleCandidate:
    handle: str
    archetype: str
    score: float
    components: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def load_character(path: Path) -> Character:
    raw = load_json(path, {})
    return Character(**{k:v for k,v in raw.items() if k in Character.__dataclass_fields__})

def load_system(path: Path) -> HandleSystem:
    raw = load_json(path, {})
    return HandleSystem(**{k:v for k,v in raw.items() if k in HandleSystem.__dataclass_fields__})

# ---------------------------------------------------------------------------
# Normalization / similarity
# ---------------------------------------------------------------------------

def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

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

def char_ngram_similarity(a: str, b: str, n=2) -> float:
    a, b = normalize_handle(a), normalize_handle(b)
    A = {a[i:i+n] for i in range(max(0, len(a)-n+1))}
    B = {b[i:i+n] for i in range(max(0, len(b)-n+1))}
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def entropy_score(s: str) -> float:
    s = normalize_handle(s)
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    h = -sum((v/n) * __import__("math").log2(v/n) for v in counts.values())
    # 0..1 relative to a useful handle range.
    return min(1.0, h / 4.0)

# ---------------------------------------------------------------------------
# Handle construction
# ---------------------------------------------------------------------------

LEET = {
    "a": "4",
    "e": "3",
    "i": "1",
    "l": "1",
    "o": "0",
    "s": "5",
    "t": "7",
    "g": "9",
    "b": "8"
}

def leet_variants(s: str) -> list[str]:
    s = normalize_handle(s)
    variants = {s}
    for i, ch in enumerate(s):
        if ch in LEET:
            variants.add(s[:i] + LEET[ch] + s[i+1:])
    # Conservative multi-substitution variants.
    for a,b in [("a","4"),("e","3"),("o","0"),("s","5")]:
        variants.add(s.replace(a,b))
    return sorted(variants)

def drop_vowels(s: str) -> str:
    s = normalize_handle(s)
    if len(s) <= 4:
        return s
    return s[0] + "".join(ch for ch in s[1:] if ch not in "aeiou")

def truncate(s: str, n: int) -> str:
    return normalize_handle(s)[:n]

def deliberate_corruption(s: str) -> list[str]:
    s = normalize_handle(s)
    out = {s}
    if "ph" in s:
        out.add(s.replace("ph", "f"))
    if "f" in s:
        out.add(s.replace("f", "ph"))
    if "c" in s:
        out.add(s.replace("c", "k"))
    if "k" in s:
        out.add(s.replace("k", "c"))
    if "s" in s:
        out.add(s.replace("s", "z"))
    if len(s) > 5:
        out.add(s[0] + s[2:])
    if len(s) > 6:
        out.add(s[:-1])
    return sorted(x for x in out if x)

def combine(a: str, b: str, separator: str = "") -> str:
    a, b = normalize_handle(a), normalize_handle(b)
    return normalize_handle(a + separator + b)

def valid(handle: str, system: HandleSystem) -> bool:
    h = normalize_handle(handle)
    if not (system.min_length <= len(h) <= system.max_length):
        return False
    if any(x in h for x in system.forbidden):
        return False
    if not all(ch in system.allowed_chars for ch in h):
        return False
    if re.search(r"(.)\1\1", h):
        return False
    return True

def weighted_choice(rng, values, weights=None):
    if not values:
        return ""
    if not weights:
        return rng.choice(values)
    return rng.choices(values, weights=weights, k=1)[0]

def generate_handle_pool(system: HandleSystem, count=500, seed=None, archetype=None):
    rng = random.Random(seed)
    pool: dict[str, str] = {}

    archetypes = [archetype] if archetype else list(system.archetypes)
    if not archetypes:
        archetypes = ["technical", "abstract", "compound"]

    for _ in range(count * 30):
        if len(pool) >= count:
            break
        kind = weighted_choice(
            rng,
            archetypes,
            [system.archetype_weights.get(x, 1.0) for x in archetypes]
        )
        h = synthesize_one(system, kind, rng)
        h = normalize_handle(h)
        if valid(h, system):
            pool.setdefault(h, kind)

    return pool

def synthesize_one(system: HandleSystem, kind: str, rng: random.Random) -> str:
    tech = system.technical_terms
    abstract = system.abstract_terms
    myth = system.mythology
    scifi = system.scifi
    mundane = system.mundane
    threat = system.threatening
    cyber = system.cyberpunk

    def pick(seq):
        return rng.choice(seq) if seq else ""

    if kind == "technical":
        return pick(tech or cyber or abstract)

    if kind == "abstract":
        return pick(abstract or cyber or tech)

    if kind == "mythological":
        return pick(myth or abstract or scifi)

    if kind == "scifi":
        return pick(scifi or myth or abstract)

    if kind == "mundane":
        return pick(mundane or abstract)

    if kind == "threatening":
        return pick(threat or abstract or cyber)

    if kind == "minimal":
        source = pick(tech + abstract + cyber + ["null", "void", "root", "zero"])
        return truncate(source, rng.choice(system.preferred_lengths))

    if kind == "compound":
        left_pool = tech + abstract + cyber
        right_pool = abstract + mundane + threat + myth
        a, b = pick(left_pool), pick(right_pool)
        sep = pick(system.separators) if rng.random() < .18 else ""
        return combine(a, b, sep)

    if kind == "technical_myth":
        return combine(pick(tech), pick(myth))

    if kind == "mundane_threat":
        return combine(pick(mundane), pick(threat))

    if kind == "ironic":
        return pick(mundane or ["accountant", "gardener", "plumber", "milkman"])

    if kind == "orthographic":
        source = pick(tech + abstract + cyber + myth)
        variants = deliberate_corruption(source)
        return pick(variants)

    if kind == "leet":
        source = pick(tech + abstract + cyber + threat)
        return pick(leet_variants(source))

    if kind == "numeric":
        source = pick(tech + abstract + cyber + threat)
        digit = pick(system.digits or ["0", "1", "7", "13", "42", "64", "69", "88", "404", "451", "0x0"])
        return source + digit

    if kind == "prefix":
        return pick(system.prefixes) + pick(tech + abstract + cyber)

    if kind == "suffix":
        return pick(tech + abstract + cyber) + pick(system.suffixes)

    return pick(tech + abstract + cyber + mundane)

def transform_pool(pool: dict[str, str], system: HandleSystem, seed=None):
    rng = random.Random(seed)
    result = dict(pool)

    for base, kind in list(pool.items()):
        operations = rng.sample(system.transformations, min(len(system.transformations), rng.randint(0, 2)))
        variants = {base}
        for op in operations:
            new = set()
            for x in variants:
                if op == "leet":
                    new.update(leet_variants(x))
                elif op == "drop-vowels":
                    new.add(drop_vowels(x))
                elif op == "truncate":
                    new.add(truncate(x, rng.choice(system.preferred_lengths)))
                elif op == "corrupt":
                    new.update(deliberate_corruption(x))
                elif op == "lower":
                    new.add(x.lower())
                elif op == "numeric":
                    new.add(x + rng.choice(system.digits or ["0","1","7","13","42"]))
                else:
                    new.add(x)
            variants = new
        for x in variants:
            x = normalize_handle(x)
            if valid(x, system):
                result.setdefault(x, f"{kind}+transform")
    return result

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

TAG_ALIASES = {
    "technical": {"technical","technicality","computer","computing","hacker","engineer","reverse","coding"},
    "mysterious": {"mysterious","secretive","enigmatic","anonymous","occult"},
    "irreverent": {"irreverent","humorous","absurd","playful","satirical"},
    "intelligent": {"intelligent","brilliant","academic","analytical","intellectual"},
    "threatening": {"threatening","dangerous","violent","ruthless","intimidating","dark"},
    "minimal": {"minimal","minimalist","spartan","simple"},
    "oldschool": {"oldschool","old-school","retro","bbs","irc","warez","phreak"},
    "gothic": {"gothic","melancholic","occult","macabre","romantic"},
    "cyberpunk": {"cyberpunk","punk","dystopian","corporate","underground"},
    "rebellious": {"rebellious","anarchic","anti-authoritarian","independent"},
    "literary": {"literary","mythological","philosophical","poetic","symbolic"},
}

def expand_tags(items):
    result=set()
    for item in items:
        result.update(re.split(r"[,;/ ]+", fold(item)))
    for key, aliases in TAG_ALIASES.items():
        if key in result:
            result.update(aliases)
    return {x for x in result if x}

def overlap(a,b):
    A, B = expand_tags(a), expand_tags(b)
    if not B:
        return 0.5
    return len(A & B) / len(B)

def score_handle(handle, archetype, char: Character, system: HandleSystem, cast=None):
    cast=cast or []
    h=normalize_handle(handle)
    low=h.lower()
    desired=expand_tags(char.desired_impression + char.personality)
    rationale=[]
    warnings=[]

    # 1. Cultural / scene fit.
    scene=0.55
    if "hacker-underground" in char.culture.lower():
        scene += 0.15
    if "oldschool" in desired and archetype in {"technical","minimal","orthographic","ironic","leet"}:
        scene += 0.12
    if char.era and any(x in char.era.lower() for x in ["1980","1990","bbs","irc"]):
        if archetype in {"technical","minimal","orthographic","ironic","leet"}:
            scene += 0.10
    scene=min(scene,1)

    # 2. Authenticity: understatement and specificity beat generic "hacker" branding.
    generic_penalty = 0
    generic_terms={"hacker","cyber","cyberwarrior","hackmaster","elitehacker","anonymous","darkweb"}
    if any(x in low for x in generic_terms):
        generic_penalty=.35
        warnings.append("Generic cyber/hacker branding; this reads more like a fictional stereotype than an organic handle.")
    authenticity=.78 - generic_penalty
    if archetype in {"technical","ironic","orthographic","minimal","compound"}:
        authenticity += .10
    if len(h) <= 12:
        authenticity += .05
    authenticity=max(0,min(1,authenticity))

    # 3. Memorability.
    memorability=.45
    if len(h) in system.preferred_lengths:
        memorability += .28
    if 1 <= len(words(h)) <= 2:
        memorability += .12
    if len(set(h)) / max(1,len(h)) >= .55:
        memorability += .08
    if h.startswith("_") or h.endswith("_"):
        memorability -= .05
    memorability=max(0,min(1,memorability))

    # 4. Character resonance.
    archetype_tags = {
        "technical":["technical","intelligent"],
        "abstract":["mysterious","literary"],
        "mythological":["literary","gothic"],
        "scifi":["cyberpunk","literary"],
        "mundane":["irreverent","minimal"],
        "threatening":["threatening"],
        "minimal":["minimal","mysterious"],
        "compound":["technical","mysterious"],
        "technical_myth":["technical","literary"],
        "mundane_threat":["irreverent","threatening"],
        "ironic":["irreverent"],
        "orthographic":["oldschool","technical","irreverent"],
        "leet":["oldschool","technical"],
        "numeric":["technical","oldschool"],
        "prefix":["technical"],
        "suffix":["technical"]
    }
    resonance=overlap(archetype_tags.get(archetype,[]), desired)
    if not desired:
        resonance=.65

    # 5. Aesthetic fit.
    aesthetic=.60
    if any(x in desired for x in TAG_ALIASES["gothic"]) and archetype in {"mythological","abstract","scifi"}:
        aesthetic += .18
    if "cyberpunk" in desired and archetype in {"technical","compound","orthographic","numeric"}:
        aesthetic += .15
    if "irreverent" in desired and archetype in {"ironic","mundane_threat","orthographic"}:
        aesthetic += .18
    aesthetic=min(1,aesthetic)

    # 6. Handle length / interface usability.
    usability=.95
    if len(h)>14: usability-=.12
    if len(h)>18: usability-=.25
    if h.count("_")+h.count("-")>1: usability-=.08
    usability=max(0,usability)

    # 7. Cast collision.
    maxsim=0
    collision=""
    for other in cast:
        for existing in [other.full_name] + other.aliases:
            if not existing: continue
            sim=max(similarity(h,existing),char_ngram_similarity(h,existing))
            if sim>maxsim:
                maxsim=sim; collision=existing
    uniqueness=max(0,1-maxsim)
    if maxsim>=.82:
        warnings.append(f"Strong cast collision with '{collision}' ({maxsim:.0%}).")
    elif maxsim>=.68:
        warnings.append(f"Moderate cast similarity with '{collision}' ({maxsim:.0%}).")

    # 8. Contradiction.
    contradiction=.55
    if char.contradiction:
        contradiction=.75
        if archetype=="ironic":
            contradiction=.95
            rationale.append("Ironic handle deliberately conflicts with the character's surface identity.")
        elif archetype=="mundane":
            contradiction=.90
            rationale.append("Mundane handle can conceal an otherwise dramatic character.")
        else:
            rationale.append("Contradiction field is active; the name is not required to describe the character literally.")

    # 9. Orthographic / old-school signal.
    oldschool=.55
    if archetype in {"orthographic","leet","numeric"}:
        oldschool=.90
    if "oldschool" in desired:
        oldschool=min(1,oldschool+.12)

    components={
        "scene_fit":scene,
        "authenticity":authenticity,
        "memorability":memorability,
        "character_resonance":resonance,
        "aesthetic_fit":aesthetic,
        "interface_usability":usability,
        "uniqueness":uniqueness,
        "contradiction_value":contradiction,
        "oldschool_signal":oldschool,
        "generic_penalty":generic_penalty
    }
    weights={
        "scene_fit":2.0,
        "authenticity":3.0,
        "memorability":3.0,
        "character_resonance":3.0,
        "aesthetic_fit":2.0,
        "interface_usability":2.0,
        "uniqueness":2.0,
        "contradiction_value":2.0,
        "oldschool_signal":1.0,
        "generic_penalty":-3.0
    }
    denom=sum(abs(x) for x in weights.values())
    total=100*sum(components[k]*weights[k] for k in weights)/denom
    total=max(0,min(100,total))

    if archetype=="technical":
        rationale.append("Technical terminology gives the handle a direct underground-computing signal.")
    elif archetype=="ironic":
        rationale.append("The deliberately mundane/absurd construction avoids obvious 'hacker name' aesthetics.")
    elif archetype=="orthographic":
        rationale.append("Orthographic distortion evokes the visual culture of older Internet aliases.")
    elif archetype=="minimal":
        rationale.append("Short handles can imply seniority, confidence, or scarcity within a fictional community.")
    elif archetype=="compound":
        rationale.append("Compound construction creates a semantic collision rather than a generic cyber label.")

    rationale.append(f"Archetype: {archetype}")
    rationale.append(f"Length: {len(h)} characters")
    rationale.append(f"Character entropy: {entropy_score(h):.0%}")

    return HandleCandidate(h,archetype,round(total,2),
                           {k:round(v*10,2) for k,v in components.items()},
                           warnings,rationale)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cast_load(path: Path):
    if path.is_file():
        raw=load_json(path,[])
        if isinstance(raw,dict): raw=raw.get("characters",[])
        return [Character(**{k:v for k,v in x.items() if k in Character.__dataclass_fields__}) for x in raw]
    out=[]
    for p in sorted(path.glob("*.json")):
        try: out.append(load_character(p))
        except Exception: pass
    return out

def cmd_init(args):
    root=Path(args.path).resolve()
    for d in ("data","profiles","projects","characters"):
        (root/d).mkdir(parents=True,exist_ok=True)

    profile=Character(
        id="forum-operator",
        era="1998-2012",
        geography="international IRC/BBS/underground forum culture",
        culture="hacker-underground",
        generation="early Internet",
        social_class="mixed",
        profession="reverse engineer",
        personality=["technical","irreverent","secretive","intelligent"],
        public_identity="ordinary Internet user",
        private_identity="experienced underground operator",
        contradiction="The person is more dangerous and knowledgeable than the handle initially suggests.",
        narrative_role="underground operator",
        desired_impression=["technical","oldschool","mysterious","intelligent","irreverent"],
        naming_system="underground-hacker-handle",
        notes="Prefer organic aliases: technical references, obscure jokes, mythology, literary references, mundane irony, compact handles, and deliberate spelling mutations."
    )
    save_json(root/"profiles/underground-handle.json",asdict(profile))

    system={
        "id":"underground-hacker-handle",
        "description":"Fictional Internet aliases inspired by BBS, IRC, warez, phreak, cypherpunk and underground computing cultures. The system deliberately favors specificity, wordplay and understatement over generic cyber-warrior branding.",
        "archetypes":{
            "technical":["technical"],
            "abstract":["abstract"],
            "mythological":["mythological"],
            "scifi":["scifi"],
            "mundane":["mundane"],
            "threatening":["threatening"],
            "minimal":["minimal"],
            "compound":["compound"],
            "technical_myth":["technical_myth"],
            "mundane_threat":["mundane_threat"],
            "ironic":["ironic"],
            "orthographic":["orthographic"],
            "leet":["leet"],
            "numeric":["numeric"],
            "prefix":["prefix"],
            "suffix":["suffix"]
        },
        "technical_terms":[
            "opcode","stack","heap","daemon","shell","kernel","root","packet","socket",
            "buffer","offset","pointer","segfault","overflow","underflow","syscall",
            "register","bit","byte","hex","xor","null","pipe","fork","signal","trace",
            "dump","core","inode","socket","cache","cipher","hash","nonce","entropy",
            "vector","process","thread","race","deadlock","wire","node","proxy","relay",
            "backdoor","payload","loader","stub","hook","patch","debug","strace","ptrace"
        ],
        "abstract_terms":[
            "void","absence","noise","static","entropy","chaos","paradox","silence",
            "echo","zero","shadow","ghost","signal","fracture","delta","nadir","axiom",
            "anomaly","cipher","riddle","oracle","oblivion","static","afterimage"
        ],
        "mythology":[
            "loki","hermes","anubis","janus","icarus","morpheus","orpheus","nyx",
            "eris","atlas","hecate","charon","echo","daemon","prometheus"
        ],
        "scifi":[
            "sprawl","neuromancer","wintermute","molly","case","akira","tyrell",
            "replicant","deckard","gibson","console","matrix","orbital","cyberspace"
        ],
        "mundane":[
            "accountant","gardener","plumber","milkman","janitor","librarian",
            "mechanic","teacher","postman","butcher","dentist","farmer","driver",
            "baker","clerk","janitor"
        ],
        "threatening":[
            "razor","venom","grave","black","dead","frost","fang","scar","wraith",
            "reaper","rot","ash","blade","thorn","viper","bruise"
        ],
        "cyberpunk":[
            "chrome","neon","wire","ghost","static","grid","mesh","relay","node",
            "proxy","zero","void","sprawl","deck","console","signal"
        ],
        "prefixes":["null","0x","neo","dead","ghost","x","cyber","hex","meta","anti"],
        "suffixes":["null","void","x","404","13","0x0","exe","bin","sys","net"],
        "separators":["","_","-"],
        "digits":["0","1","3","7","13","17","23","42","64","88","101","127","1337","404","451","0x0"],
        "allowed_chars":"abcdefghijklmnopqrstuvwxyz0123456789_-",
        "max_length":18,
        "min_length":3,
        "preferred_lengths":[4,5,6,7,8,9,10,11,12],
        "transformations":["leet","drop-vowels","truncate","corrupt","lower","numeric"],
        "forbidden":[
            "hacker","hackers","cyberwarrior","hackmaster","elitehacker",
            "anonymous","darkweb","darknet","ransomware","terrorist"
        ],
        "overused":[
            "shadow","dark","cyber","hack","killer","elite","warrior","ghost",
            "anonymous","1337","xX","Xx"
        ],
        "archetype_weights":{
            "technical":1.3,
            "abstract":1.2,
            "compound":1.5,
            "ironic":1.1,
            "orthographic":1.0,
            "minimal":1.0,
            "mythological":0.7,
            "scifi":0.7,
            "mundane":0.8,
            "threatening":0.6,
            "technical_myth":0.8,
            "mundane_threat":0.8,
            "leet":0.6,
            "numeric":0.7,
            "prefix":0.6,
            "suffix":0.6
        }
    }
    save_json(root/"profiles/underground-hacker-handle.json",system)

    # Profile and system use separate files: preserve the requested pair.
    save_json(root/"profiles/underground-character.json",asdict(profile))

    # Example cast.
    examples=[
        Character(id="zero",aliases=["null"],given_name="Elias",family_name="Voss"),
        Character(id="mildew",aliases=["mildew"],given_name="Mara",family_name="Vale"),
        Character(id="oracle",aliases=["oracle"],given_name="Adrian",family_name="Vey")
    ]
    for x in examples:
        save_json(root/"characters"/f"{x.id}.json",asdict(x))

    print(paint(f"Initialized underground NameForge project: {root}",T.GREEN))
    print("Profile :",root/"profiles/underground-character.json")
    print("System  :",root/"profiles/underground-hacker-handle.json")

def cmd_generate(args):
    char=load_character(Path(args.profile))
    system=load_system(Path(args.system))
    cast=cast_load(Path(args.cast)) if args.cast else []
    pool=generate_handle_pool(system,args.pool,args.seed,args.archetype)
    pool=transform_pool(pool,system,args.seed)
    ranked=[score_handle(h,k,char,system,cast) for h,k in pool.items()]
    ranked.sort(key=lambda x:x.score,reverse=True)

    print(paint(f"UNDERGROUND HANDLE CANDIDATES — {char.id}",T.BOLD))
    print("─"*88)
    for i,x in enumerate(ranked[:args.top],1):
        print(f"{i:>2}. {paint(x.handle,T.CYAN):22} {x.score:5.1f}/100  [{x.archetype}]")
        if args.verbose:
            print("    "+" | ".join(f"{k}={v/10:.1f}" for k,v in x.components.items()))
            for r in x.rationale:
                print("    + "+r)
            for w in x.warnings:
                print("    "+paint("⚠ "+w,T.YELLOW))
    if args.output:
        save_json(Path(args.output),[asdict(x) for x in ranked[:args.top]])
        print(paint(f"\nSaved: {args.output}",T.GREEN))

def cmd_score(args):
    char=load_character(Path(args.profile))
    system=load_system(Path(args.system))
    cast=cast_load(Path(args.cast)) if args.cast else []
    rows=[]
    for line in Path(args.names).read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            handle, archetype=line.split("\t",1)
            archetype=archetype.strip() or "unknown"
        else:
            handle, archetype=line, "unknown"
        rows.append(score_handle(handle,archetype,char,system,cast))
    rows.sort(key=lambda x:x.score,reverse=True)
    for x in rows:
        print(f"{x.handle:22} {x.score:5.1f}/100 [{x.archetype}]")
        if args.verbose:
            for k,v in x.components.items():
                print(f"  {k:24} {v/10:.1f}/10")
            for r in x.rationale: print("  +",r)
            for w in x.warnings: print("  !",w)

def cmd_analyze(args):
    h=normalize_handle(args.handle)
    print(f"Handle:          {args.handle}")
    print(f"Normalized:      {h}")
    print(f"Length:          {len(h)}")
    print(f"Words:           {words(h)}")
    print(f"Unique chars:    {len(set(h))}/{len(h)}")
    print(f"Entropy score:   {entropy_score(h):.0%}")
    print(f"Has digits:      {'yes' if any(x.isdigit() for x in h) else 'no'}")
    print(f"Has separator:   {'yes' if any(x in h for x in '_-') else 'no'}")
    print(f"Leet variants:   {', '.join(leet_variants(h)[:8])}")
    print(f"Corruptions:     {', '.join(deliberate_corruption(h)[:8])}")

def cmd_cast(args):
    cast=cast_load(Path(args.cast))
    pairs=[]
    aliases=[]
    for x in cast:
        aliases.extend([(a,x.id) for a in x.aliases])
    for i,(a,aid) in enumerate(aliases):
        for b,bid in aliases[i+1:]:
            if aid==bid: continue
            sim=max(similarity(a,b),char_ngram_similarity(a,b))
            if sim>=args.threshold:
                pairs.append((sim,aid,a,bid,b))
    pairs.sort(reverse=True)
    print(paint("UNDERGROUND HANDLE COLLISION REPORT",T.BOLD))
    print("─"*88)
    if not pairs:
        print(paint("No significant alias collisions detected.",T.GREEN))
        return
    for sim,aid,a,bid,b in pairs:
        level="HIGH" if sim>=.82 else "MEDIUM"
        print(f"{level:6} {sim:.0%}  {aid}:{a}  <->  {bid}:{b}")

def cmd_system(args):
    s=load_system(Path(args.system))
    print(paint(f"NAMING SYSTEM: {s.id}",T.BOLD))
    print(s.description)
    print("\nArchetypes:")
    for k,v in s.archetypes.items():
        print(f"  {k:18} {', '.join(v)}")
    print("\nPools:")
    for field in ("technical_terms","abstract_terms","mythology","scifi","mundane","threatening","cyberpunk"):
        print(f"  {field:18} {len(getattr(s,field))}")
    print(f"\nLength range: {s.min_length}-{s.max_length}")
    print("Preferred:     "+", ".join(map(str,s.preferred_lengths)))
    print("Transformations:",", ".join(s.transformations))

def cmd_export(args):
    char=load_character(Path(args.profile))
    system=load_system(Path(args.system))
    obj={"nameforge_version":VERSION,"character":asdict(char),"handle_system":asdict(system)}
    save_json(Path(args.output),obj)
    print(paint(f"Exported: {args.output}",T.GREEN))

def build_parser():
    p=argparse.ArgumentParser(prog="nameforge",description="Offline underground Internet-handle workbench.")
    p.add_argument("--version",action="version",version=f"%(prog)s {VERSION}")
    p.add_argument("--no-color",action="store_true")
    sp=p.add_subparsers(dest="command",required=True)

    x=sp.add_parser("init",help="Create an underground-handle project.")
    x.add_argument("path",nargs="?",default="nameforge-underground")
    x.set_defaults(func=cmd_init)

    x=sp.add_parser("generate",help="Generate, transform and rank underground handles.")
    x.add_argument("--profile",required=True)
    x.add_argument("--system",required=True)
    x.add_argument("--cast")
    x.add_argument("--pool",type=int,default=1000)
    x.add_argument("--top",type=int,default=30)
    x.add_argument("--seed",type=int)
    x.add_argument("--archetype",choices=[
        "technical","abstract","mythological","scifi","mundane","threatening",
        "minimal","compound","technical_myth","mundane_threat","ironic",
        "orthographic","leet","numeric","prefix","suffix"
    ])
    x.add_argument("--verbose","-v",action="store_true")
    x.add_argument("--output")
    x.set_defaults(func=cmd_generate)

    x=sp.add_parser("score",help="Score a newline-separated handle list. Optional TAB + archetype.")
    x.add_argument("--profile",required=True)
    x.add_argument("--system",required=True)
    x.add_argument("--names",required=True)
    x.add_argument("--cast")
    x.add_argument("--verbose","-v",action="store_true")
    x.set_defaults(func=cmd_score)

    x=sp.add_parser("analyze",help="Analyze one handle.")
    x.add_argument("handle")
    x.set_defaults(func=cmd_analyze)

    x=sp.add_parser("cast-check",help="Find collisions among aliases in a cast.")
    x.add_argument("cast")
    x.add_argument("--threshold",type=float,default=.68)
    x.set_defaults(func=cmd_cast)

    x=sp.add_parser("system",help="Inspect a handle system.")
    x.add_argument("--system",required=True)
    x.set_defaults(func=cmd_system)

    x=sp.add_parser("export",help="Export a character + handle system snapshot.")
    x.add_argument("--profile",required=True)
    x.add_argument("--system",required=True)
    x.add_argument("--output",required=True)
    x.set_defaults(func=cmd_export)

    return p

def main(argv=None):
    parser=build_parser()
    args=parser.parse_args(argv)
    if args.command=="init":
        args.func(args)
        return 0
    color=not args.no_color and sys.stdout.isatty()
    if color: banner(True)
    try:
        args.func(args)
        return 0
    except FileNotFoundError as e:
        print(paint(f"ERROR: file not found: {e.filename}",T.RED),file=sys.stderr)
        return 2
    except (ValueError,json.JSONDecodeError) as e:
        print(paint(f"ERROR: {e}",T.RED),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
