"""Tests for worddata.pick: determinism, difficulty, untiered fallback, errors."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> import worddata
from worddata import pick  # noqa: E402
from worddata import store  # noqa: E402


def make_assets(root: Path):
    """A tiered pack + an untiered pack, laid out like assets/dictionaries/."""
    tiered = root / "tpack"
    tiered.mkdir()
    tiers = {"tiers": {"easy": ["alpha", "bravo"], "medium": ["charl", "delta"], "hard": ["echoo", "foxtr"]}}
    (tiered / "tiers.json").write_text(json.dumps(tiers))
    (tiered / "puzzle_words.txt").write_text("alpha\nbravo\ncharl\ndelta\nechoo\nfoxtr\n")
    (tiered / "dictionary.jsonl").write_text("")

    flat = root / "flat"
    flat.mkdir()
    (flat / "words.txt").write_text("apple\nmango\nlemon\n")
    (flat / "dictionary.jsonl").write_text("")


class TestPick(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_assets(self.root)
        store.ASSETS = self.root  # redirect the package to our fixture

    def tearDown(self):
        self._tmp.cleanup()

    def test_seed_is_repeatable(self):
        self.assertEqual(pick.pick_word("tpack", seed="2026-07-01"),
                         pick.pick_word("tpack", seed="2026-07-01"))

    def test_different_seeds_explore_pool(self):
        self.assertGreater(len({pick.pick_word("tpack", seed=f"s{i}") for i in range(20)}), 1)

    def test_difficulty_draws_from_that_tier(self):
        for i in range(30):
            self.assertIn(pick.pick_word("tpack", difficulty="easy", seed=str(i)), {"alpha", "bravo"})

    def test_all_tiers_joined_when_no_difficulty(self):
        self.assertEqual(set(pick.load_pool("tpack", None)),
                         {"alpha", "bravo", "charl", "delta", "echoo", "foxtr"})

    def test_untiered_pack_uses_word_list(self):
        self.assertEqual(set(pick.load_pool("flat", None)), {"apple", "mango", "lemon"})

    def test_difficulty_on_untiered_pack_errors(self):
        with self.assertRaises(SystemExit):
            pick.pick_word("flat", difficulty="easy")

    def test_unknown_pack_errors(self):
        with self.assertRaises(SystemExit):
            pick.pick_word("nope")

    def test_tier_of(self):
        self.assertEqual(store.tier_of("tpack", "charl"), "medium")
        self.assertIsNone(store.tier_of("flat", "apple"))

    def test_mature_words_excluded_from_solutions_by_default(self):
        (self.root / "blocklist_solutions.txt").write_text("bravo\ndelta\n")
        # default: blocklisted words never appear in the pool ...
        self.assertEqual(set(pick.load_pool("tpack", None)),
                         {"alpha", "charl", "echoo", "foxtr"})
        # ... and pick_word can never return one
        self.assertNotIn("bravo", {pick.pick_word("tpack", seed=str(i)) for i in range(40)})
        # opt-in restores them as eligible solutions
        self.assertEqual(set(pick.load_pool("tpack", None, allow_mature=True)),
                         {"alpha", "bravo", "charl", "delta", "echoo", "foxtr"})

    def test_mature_filter_applies_to_difficulty_and_untiered_packs(self):
        (self.root / "blocklist_solutions.txt").write_text("bravo\nmango\n")
        self.assertEqual(set(pick.load_pool("tpack", "easy")), {"alpha"})        # tiered: bravo gone
        self.assertEqual(set(pick.load_pool("flat", None)), {"apple", "lemon"})  # untiered: mango gone


if __name__ == "__main__":
    unittest.main()
