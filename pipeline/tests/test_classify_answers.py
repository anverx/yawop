"""Tests for the rule-based answer-eligibility classifier (scripts/classify_answers.py).

Needs nltk + WordNet (the rule reads WordNet metadata); skipped gracefully where
those aren't installed (e.g. a bare CI). The obscene/reference regexes and the
dictionary augmentation are the novel logic and are covered here.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    import classify_answers as CA
    from nltk.corpus import wordnet as wn
    wn.synsets("test")  # force corpus load; raises if absent
    HAVE_WN = True
except Exception:
    HAVE_WN = False


@unittest.skipUnless(HAVE_WN, "nltk/WordNet not installed")
class TestObsceneRegex(unittest.TestCase):
    """Matches definitions that mark the WORD as a slur, not ones that merely mention offensiveness."""

    def test_marks_obscene_terms(self):
        for d in ["obscene terms for penis", "offensive term for a lesbian",
                  "an offensive or indecent word or phrase", "a racial slur", "a term of contempt"]:
            self.assertTrue(CA.OBSCENE.search(d), d)

    def test_ignores_mere_mentions(self):
        for d in ["(American football) break through the offensive line", "highly offensive; arousing disgust",
                  "a rude or vulgar fool", "offensive or even malicious"]:
            self.assertFalse(CA.OBSCENE.search(d), d)


@unittest.skipUnless(HAVE_WN, "nltk/WordNet not installed")
class TestReferenceRegex(unittest.TestCase):
    def test_degenerate_references(self):
        for d in ["Alternative letter-case form of Allah", "plural of yeman",
                  "Misspelling of googol", "Obsolete spelling of hook", "Clipping of sousaphone"]:
            self.assertTrue(CA.REFERENCE.search(d), d)

    def test_real_meanings_are_not_references(self):
        for d in ["A spicy fritter, originally from Ghana", "A short match, made of wood or wax",
                  "A gold coin issued by the French kings"]:
            self.assertFalse(CA.REFERENCE.search(d), d)


@unittest.skipUnless(HAVE_WN, "nltk/WordNet not installed")
class TestClassify(unittest.TestCase):
    def test_curated_obscene_wins(self):
        self.assertEqual(CA.classify("penis", {}, {"penis"})[0], "obscene")

    def test_clean_dominant_stays_eligible(self):
        self.assertEqual(CA.classify("cock", {}, set())[0], "eligible")   # rooster >> slang

    def test_obscene_dominant_is_gated(self):
        self.assertEqual(CA.classify("pussy", {}, set())[0], "obscene")   # slang >> cat

    def test_proper_only_is_a_name(self):
        cache = {"allah": {"en": [{"partOfSpeech": "Proper noun",
                                   "definitions": [{"definition": "The God of Islam."}]}]}}
        self.assertEqual(CA.classify("allah", cache, set())[0], "name")

    def test_side_meaning_rescues_a_name(self):
        cache = {"ghana": {"en": [{"partOfSpeech": "noun",
                                   "definitions": [{"definition": "A style of Maltese folk singing"}]}]}}
        verdict, side = CA.classify("ghana", cache, set())
        self.assertEqual(verdict, "eligible")
        self.assertTrue(side and "Maltese" in side[0]["definition"])

    def test_no_evidence_keeps_eligible(self):
        # a WordNet-less, uncached word (defined elsewhere) is never stripped on a guess
        self.assertEqual(CA.classify("aboon", {}, set())[0], "eligible")


@unittest.skipUnless(HAVE_WN, "nltk/WordNet not installed")
class TestAugment(unittest.TestCase):
    def test_grafts_side_sense_with_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            assets = Path(d)
            pack = assets / "p"
            pack.mkdir()
            (pack / "dictionary.jsonl").write_text(
                json.dumps({"word": "ghana", "senses": [{"pos_label": "noun", "definition": "a country"}]}) + "\n")
            side = [{"pos_label": "noun", "definition": "Maltese folk singing", "source": "wiktionary"}]
            added = CA.augment_dictionaries(assets, {"ghana": side})
            self.assertEqual(added, 1)
            rec = json.loads((pack / "dictionary.jsonl").read_text().strip())
            self.assertEqual(len(rec["senses"]), 2)
            # idempotent: re-running grafts nothing
            self.assertEqual(CA.augment_dictionaries(assets, {"ghana": side}), 0)


if __name__ == "__main__":
    unittest.main()
