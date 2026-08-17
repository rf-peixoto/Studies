import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nameforge

class TestUndergroundHandles(unittest.TestCase):
    def setUp(self):
        self.s = nameforge.HandleSystem(
            id="test",
            archetypes={"technical":["technical"],"ironic":["ironic"],"compound":["compound"]},
            technical_terms=["opcode","stack","null"],
            abstract_terms=["entropy","void"],
            mythology=["loki"],
            mundane=["janitor"],
            threatening=["razor"],
            cyberpunk=["wire"],
            separators=["","_","-"],
            digits=["0","13"],
            transformations=["leet","drop-vowels","corrupt","numeric"],
            forbidden=["hacker"],
            max_length=18,
            min_length=3,
            preferred_lengths=[4,5,6,7,8,9,10,11,12]
        )
        self.c = nameforge.Character(
            id="x",
            culture="hacker-underground",
            era="1990s IRC",
            personality=["technical","irreverent"],
            desired_impression=["oldschool","mysterious"],
            contradiction="mundane surface"
        )

    def test_normalization(self):
        self.assertEqual(nameforge.normalize_handle(" Null Byte! "), "nullbyte")

    def test_generation(self):
        pool = nameforge.generate_handle_pool(self.s, 50, seed=42)
        self.assertGreaterEqual(len(pool), 10)
        self.assertTrue(all(nameforge.valid(x,self.s) for x in pool))

    def test_leet(self):
        self.assertIn("3ntropy", nameforge.leet_variants("entropy"))

    def test_compound(self):
        pool = nameforge.generate_handle_pool(self.s, 100, seed=1, archetype="compound")
        self.assertTrue(pool)

    def test_scoring(self):
        x = nameforge.score_handle("null", "minimal", self.c, self.s)
        self.assertGreater(x.score, 0)

if __name__ == "__main__":
    unittest.main()
