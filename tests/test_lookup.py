"""Tests for worddata.lookup: cross-pack merge of an entry."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worddata import lookup  # noqa: E402
from worddata import store  # noqa: E402


def write_jsonl(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))


class TestLookup(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        us = self.root / "subtlex-us"; us.mkdir()
        arc = self.root / "arcane"; arc.mkdir()
        write_jsonl(us / "dictionary.jsonl", [
            {"word": "quoth", "senses": [{"pos_label": "v", "definition": "to say", "source": "wordnet"}]}])
        (us / "tiers.json").write_text(json.dumps({"tiers": {"easy": [], "medium": ["quoth"], "hard": []}}))
        write_jsonl(arc / "dictionary.jsonl", [
            {"word": "quoth",
             "senses": [{"pos_label": "v", "definition": "to say", "source": "wordnet"},
                        {"pos_label": "v", "definition": "declare", "source": "dictionaryapi.dev"}],
             "examples": [{"work": "Beowulf", "author": "Anon", "text": "quoth he", "source": "wikisource"}],
             "gutenberg_search_url": "http://example/quoth"}])
        (arc / "tiers.json").write_text(json.dumps({"tiers": {"easy": ["quoth"], "medium": [], "hard": []}}))
        store.ASSETS = self.root

    def tearDown(self):
        self._tmp.cleanup()

    def test_merges_senses_examples_and_packs(self):
        e = lookup.lookup_entry("QUOTH")  # case-insensitive
        self.assertEqual(len(e["senses"]), 2)                     # deduped union across packs
        self.assertEqual(len(e["examples"]), 1)
        self.assertEqual(e["gutenberg_search_url"], "http://example/quoth")
        self.assertEqual({p["pack"] for p in e["packs"]}, {"subtlex-us", "arcane"})
        tiers = {p["pack"]: p["tier"] for p in e["packs"]}
        self.assertEqual(tiers, {"subtlex-us": "medium", "arcane": "easy"})

    def test_missing_word_returns_none(self):
        self.assertIsNone(lookup.lookup_entry("zzzzz"))

    def test_pack_filter(self):
        e = lookup.lookup_entry("quoth", pack="subtlex-us")
        self.assertEqual([p["pack"] for p in e["packs"]], ["subtlex-us"])
        self.assertEqual(len(e["senses"]), 1)


if __name__ == "__main__":
    unittest.main()
