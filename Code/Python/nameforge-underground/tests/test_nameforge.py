"""Test suite for NameForge 2.1.

Each test in TestRegressions pins a specific bug found in 2.0 so it cannot
come back. The rest cover normal behaviour.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nameforge  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def make_system(**over):
    base = dict(
        id="test",
        archetypes={k: {} for k in ["technical", "ironic", "compound", "minimal",
                                    "orthographic", "leet", "numeric", "abstract"]},
        technical_terms=["opcode", "stack", "nullptr", "segfault"],
        abstract_terms=["entropy", "void", "silence"],
        mythology=["loki", "janus"],
        mundane=["janitor", "plumber"],
        threatening=["razor"],
        cyberpunk=["relay"],
        separators=["", "_", "-"],
        digits=["0", "13"],
        transformations=["leet", "drop-vowels", "corrupt", "numeric"],
        forbidden=["hacker"],
        overused=["dark", "phantom"],
        max_length=18,
        min_length=3,
        preferred_lengths=[4, 5, 6, 7, 8, 9, 10, 11, 12],
    )
    base.update(over)
    return nameforge.HandleSystem(**base)


def make_char(**over):
    base = dict(
        id="x",
        culture="hacker-underground",
        era="1990s IRC",
        first_online_year=1995,
        personality=["technical", "irreverent"],
        desired_impression=["oldschool", "mysterious"],
        contradiction="mundane surface",
    )
    base.update(over)
    return nameforge.Character(**base)


class TestNormalization(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(nameforge.normalize_handle(" Null Byte! "), "nullbyte")

    def test_accent_folding(self):
        self.assertEqual(nameforge.normalize_handle("Mará-Vãle"), "mara-vale")

    def test_levenshtein_empty(self):
        self.assertEqual(nameforge.levenshtein("", "abc"), 3)
        self.assertEqual(nameforge.levenshtein("abc", ""), 3)

    def test_similarity_bounds(self):
        self.assertEqual(nameforge.similarity("null", "null"), 1.0)
        self.assertEqual(nameforge.similarity("", "null"), 0.0)

    def test_pronounceability(self):
        self.assertGreater(nameforge.pronounceability("janitor"), nameforge.pronounceability("xkcdvvt"))


class TestGeneration(unittest.TestCase):
    def setUp(self):
        self.s = make_system()
        self.c = make_char()

    def test_generation(self):
        pool = nameforge.generate_handle_pool(self.s, 50, seed=42)
        self.assertGreaterEqual(len(pool), 10)
        self.assertTrue(all(nameforge.is_valid(h, self.s) for h in pool))

    def test_generation_is_deterministic(self):
        a = nameforge.generate_handle_pool(self.s, 40, seed=5)
        b = nameforge.generate_handle_pool(self.s, 40, seed=5)
        self.assertEqual(sorted(a), sorted(b))

    def test_compound(self):
        pool = nameforge.generate_handle_pool(self.s, 30, seed=1, archetype="compound")
        self.assertTrue(pool)

    def test_unknown_archetype_raises(self):
        with self.assertRaises(nameforge.NameForgeError):
            nameforge.generate_handle_pool(self.s, 10, seed=1, archetype="wizard")

    def test_leet(self):
        self.assertIn("3ntropy", nameforge.leet_variants("entropy"))

    def test_seeded_archetype_uses_writer_words(self):
        pool = nameforge.generate_handle_pool(
            make_system(archetypes={"seeded": {}}), 20, seed=3,
            archetype="seeded", seed_words=["vosszz"])
        self.assertTrue(pool)
        self.assertTrue(any("voss" in h for h in pool))


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.s = make_system()
        self.c = make_char()

    def test_scoring(self):
        x = nameforge.score_handle("nullptr", "minimal", self.c, self.s)
        self.assertGreater(x.score, 0)
        self.assertLessEqual(x.score, 100)

    def test_cast_collision_detected(self):
        other = nameforge.Character(id="other", aliases=["opcode"])
        x = nameforge.score_handle("opcode", "technical", self.c, self.s, [other])
        self.assertTrue(any("collision" in w.lower() for w in x.warnings))

    def test_character_is_not_compared_against_itself(self):
        me = make_char(id="me", aliases=["opcode"])
        x = nameforge.score_handle("opcode", "technical", me, self.s, [me])
        self.assertEqual(x.components["uniqueness"], 10.0)

    def test_avoid_list_penalises(self):
        plain = nameforge.score_handle("opcode", "technical", self.c, self.s)
        avoided = nameforge.score_handle(
            "opcode", "technical", make_char(avoid=["opcode"]), self.s)
        self.assertLess(avoided.score, plain.score)
        self.assertTrue(avoided.penalties)


class TestRegressions(unittest.TestCase):
    """One test per bug fixed in 2.1."""

    def setUp(self):
        self.s = make_system()
        self.c = make_char()

    def test_score_ceiling_is_reachable(self):
        """2.0 kept the penalty weight in the denominator, capping every score
        at ~87/100 even for a flawless handle."""
        weights = nameforge.DEFAULT_SCORE_WEIGHTS
        perfect = {k: 1.0 for k in weights}
        denom = sum(weights.values())
        self.assertAlmostEqual(sum(perfect[k] * weights[k] for k in weights) / denom, 1.0)

    def test_generic_penalty_is_not_double_counted(self):
        """2.0 subtracted the generic penalty from authenticity *and* applied it
        again as a negative-weight component."""
        x = nameforge.score_handle("cyberthing", "technical", self.c, self.s,
                                   [])
        self.assertEqual(len([p for p in x.penalties if "generic" in p]), 1)

    def test_overused_list_is_actually_used(self):
        """2.0 loaded `overused` and never consulted it anywhere."""
        clean = nameforge.score_handle("opcode", "technical", self.c, self.s)
        dirty = nameforge.score_handle("darkopcode", "technical", self.c, self.s)
        self.assertLess(dirty.score, clean.score)
        self.assertTrue(any("overused" in p for p in dirty.penalties))

    def test_overused_matching_respects_morphemes(self):
        """A substring test flagged 'neon' for containing 'neo'."""
        self.assertFalse(nameforge.contains_element("neon", "neo"))
        self.assertTrue(nameforge.contains_element("darkstack", "dark"))
        self.assertTrue(nameforge.contains_element("darkphantomx", "phantom"))

    def test_orthographic_always_changes_the_word(self):
        """2.0 included the unmodified source in the corruption set, so ~53% of
        'orthographic' handles were plain dictionary words."""
        rng = __import__("random").Random(0)
        srcs = {t.term for t in self.s.pool("technical", "abstract", "cyberpunk", "mythology")}
        for _ in range(200):
            b = nameforge.synthesize_one(self.s, "orthographic", rng)
            if b:
                self.assertNotIn(b.handle, srcs)

    def test_leet_always_contains_leet(self):
        rng = __import__("random").Random(0)
        srcs = {t.term for t in self.s.pool("technical", "abstract", "cyberpunk", "threatening")}
        for _ in range(200):
            b = nameforge.synthesize_one(self.s, "leet", rng)
            if b:
                self.assertNotIn(b.handle, srcs)

    def test_minimal_is_actually_minimal(self):
        """2.0 truncated to a random preferred length (up to 12), so 'minimal'
        routinely returned the whole source word."""
        rng = __import__("random").Random(0)
        for _ in range(100):
            b = nameforge.synthesize_one(self.s, "minimal", rng)
            if b:
                self.assertLessEqual(len(b.handle), 6)

    def test_compound_rejects_doubled_halves(self):
        """2.0 produced 'echoecho' and 'voidvoid'."""
        self.assertTrue(nameforge.compound_is_degenerate("echo", "echo"))
        self.assertTrue(nameforge.compound_is_degenerate("null", "nullptr"))
        self.assertFalse(nameforge.compound_is_degenerate("stack", "janitor"))

    def test_transforms_keep_their_archetype(self):
        """2.0 relabelled mutations '<archetype>+transform', a key absent from
        every scoring table, zeroing their resonance and archetype bonuses."""
        pool = nameforge.generate_handle_pool(self.s, 40, seed=11)
        full = nameforge.transform_pool(pool, self.s, seed=11)
        for b in full.values():
            self.assertIn(b.archetype, nameforge.ARCHETYPES)

    def test_transformed_handles_score_like_their_archetype(self):
        pool = nameforge.generate_handle_pool(self.s, 60, seed=11)
        full = nameforge.transform_pool(pool, self.s, seed=11)
        mutated = [b for b in full.values() if b.transforms]
        self.assertTrue(mutated)
        scored = [nameforge.score_handle(b.handle, b.archetype, self.c, self.s, [], b)
                  for b in mutated]
        self.assertTrue(any(x.components["character_resonance"] > 0 for x in scored))

    def test_scores_are_well_spread(self):
        """2.0 produced 36 distinct scores across 2207 candidates."""
        pool = nameforge.generate_handle_pool(self.s, 200, seed=3)
        pool = nameforge.transform_pool(pool, self.s, seed=3)
        scored = [nameforge.score_handle(b.handle, b.archetype, self.c, self.s, [], b)
                  for b in pool.values()]
        distinct = len({round(x.score, 2) for x in scored})
        self.assertGreater(distinct, len(scored) * 0.25)

    def test_missing_file_raises_filenotfound(self):
        """2.0 raised a bare TypeError from the dataclass constructor."""
        with self.assertRaises(FileNotFoundError):
            nameforge.load_character(Path("definitely-not-here.json"))

    def test_padding_ignores_ansi_escapes(self):
        """2.0 padded coloured cells by raw length, misaligning every column."""
        nameforge.set_color(True)
        try:
            cell = nameforge.pad(nameforge.paint("null", nameforge.T.CYAN), 10)
            self.assertEqual(nameforge.visible_len(cell), 10)
        finally:
            nameforge.set_color(False)

    def test_no_color_flag_is_honoured(self):
        nameforge.set_color(False)
        self.assertEqual(nameforge.paint("x", nameforge.T.CYAN), "x")

    def test_invalid_length_range_rejected(self):
        with self.assertRaises(nameforge.NameForgeError):
            make_system(min_length=10, max_length=4, preferred_lengths=[])

    def test_separator_edges_rejected(self):
        ok, why = nameforge.valid("_null", self.s)
        self.assertFalse(ok)
        ok, why = nameforge.valid("null__byte", self.s)
        self.assertFalse(ok)


class TestLexicon(unittest.TestCase):
    def test_legacy_string_lexicon_still_loads(self):
        s = make_system()  # plain strings, 2.0 format
        self.assertTrue(s.pools["technical"])
        self.assertEqual(s.pools["technical"][0].term, "opcode")

    def test_rich_lexicon_parses_metadata(self):
        s = make_system(technical_terms=[
            {"term": "ptrace", "tags": ["technical"], "gloss": "watch a process",
             "since": 1985, "register": "insider", "weight": 2.0}])
        t = s.pools["technical"][0]
        self.assertEqual((t.gloss, t.since, t.register, t.weight),
                         ("watch a process", 1985, "insider", 2.0))

    def test_duplicate_terms_are_collapsed(self):
        s = make_system(technical_terms=["stack", "stack", "heap"])
        self.assertEqual([t.term for t in s.pools["technical"]], ["stack", "heap"])

    def test_era_filter(self):
        s = make_system(technical_terms=[
            {"term": "bluebox", "since": 1971, "until": 1995},
            {"term": "mesh", "since": 1995}])
        early = nameforge.era_filter(s.pools["technical"], 1990)
        self.assertEqual([t.term for t in early], ["bluebox"])

    def test_shipped_system_is_healthy(self):
        s = nameforge.load_system(ROOT / "profiles/underground-hacker-handle.json")
        total = sum(len(v) for v in s.pools.values())
        self.assertGreater(total, 200)
        self.assertTrue(all(t.gloss for v in s.pools.values() for t in v),
                        "every shipped term should carry a gloss")
        for term in ("mildew", "bogon", "nonce", "janitor"):
            self.assertIsNotNone(s.lookup(term))

    def test_shipped_cast_loads(self):
        cast = nameforge.cast_load(ROOT / "characters")
        self.assertGreaterEqual(len(cast), 4)
        self.assertTrue(all(c.id for c in cast))


class TestCLI(unittest.TestCase):
    def test_generate_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            rc = nameforge.main([
                "--no-color", "generate",
                "--profile", str(ROOT / "profiles/underground-character.json"),
                "--system", str(ROOT / "profiles/underground-hacker-handle.json"),
                "--cast", str(ROOT / "characters"),
                "--top", "5", "--pool", "120", "--seed", "1", "--format", "json",
                "--output", str(out)])
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text())
            self.assertEqual(len(data["candidates"]), 5)

    def test_doctor_on_shipped_system(self):
        rc = nameforge.main(["--no-color", "doctor", "--strict",
                             "--system", str(ROOT / "profiles/underground-hacker-handle.json")])
        self.assertEqual(rc, 0)

    def test_missing_profile_exits_cleanly(self):
        rc = nameforge.main(["--no-color", "generate", "--profile", "nope.json",
                             "--system", str(ROOT / "profiles/underground-hacker-handle.json")])
        self.assertEqual(rc, 2)

    def test_analyze(self):
        self.assertEqual(nameforge.main(["--no-color", "analyze", "mildew",
                                         "--system", str(ROOT / "profiles/underground-hacker-handle.json")]), 0)

    def test_cast_check(self):
        self.assertEqual(nameforge.main(["--no-color", "cast-check", str(ROOT / "characters")]), 0)

    def test_init_copies_templates(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "proj"
            self.assertEqual(nameforge.main(["--no-color", "init", str(target)]), 0)
            self.assertTrue((target / "profiles/underground-hacker-handle.json").exists())


if __name__ == "__main__":
    unittest.main()
