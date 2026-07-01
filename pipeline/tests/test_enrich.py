"""Tests for enrich_examples: dictionary/reference filter, dedupe, 3-cap, cleaning."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import enrich_examples as ee  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    """Answers Wikisource search queries with canned hits; author lookups with a fixed author."""
    def __init__(self, hits):
        self._hits = hits

    def get(self, url, params=None, **kw):
        params = params or {}
        if params.get("list") == "search":
            return FakeResp({"query": {"search": self._hits}})
        # revisions (author lookup)
        content = "{{header | title=X | author=[[Author:Homer|Homer]] }}"
        return FakeResp({"query": {"pages": {"1": {"revisions": [{"slots": {"main": {"*": content}}}]}}}})


class TestReferenceFilter(unittest.TestCase):
    def test_reference_regex_matches_reference_works(self):
        for t in ["A Dictionary of Slang", "English Glossary", "Latin Lexicon",
                  "Roget's Thesaurus", "Encyclopaedia Britannica", "A Concordance",
                  "The American Cyclopædia (1879)", "Cyclopedia of Painting",
                  "Catalog of Copyright Entries", "A Gazetteer of the World"]:
            self.assertTrue(ee.REFERENCE_RE.search(t), t)

    def test_reference_regex_allows_prose(self):
        for t in ["Beowulf", "Hamlet", "The Odyssey", "More English Fairy Tales"]:
            self.assertIsNone(ee.REFERENCE_RE.search(t), t)

    def test_clean_strips_tags_and_entities(self):
        self.assertEqual(ee.clean('a <span class="x">vaunt</span> &amp; more'), "a vaunt & more")


class TestExampleSelection(unittest.TestCase):
    def _run(self, hits):
        return ee.example_for("vaunt", FakeSession(hits), cache={})

    def test_filters_dictionaries_dedupes_works_and_caps_at_three(self):
        hits = [
            {"title": "A Dictionary of Archaic Words", "snippet": "vaunt (v.)"},   # filtered
            {"title": "Beowulf/Chapter 1", "snippet": "did vaunt his deeds"},
            {"title": "Beowulf/Chapter 2", "snippet": "vaunt once more"},          # same work -> skip
            {"title": "Hamlet/Act 1", "snippet": "no vaunt here"},
            {"title": "The Odyssey/Book 1", "snippet": "vaunt of kings"},
            {"title": "Paradise Lost/Book 2", "snippet": "proud vaunt"},           # beyond cap of 3
        ]
        out = self._run(hits)
        self.assertEqual([e["work"] for e in out], ["Beowulf", "Hamlet", "The Odyssey"])
        self.assertTrue(all(e["author"] == "Homer" for e in out))
        self.assertTrue(all(e["source"] == "wikisource" for e in out))

    def test_skips_hits_not_containing_the_word(self):
        out = self._run([{"title": "Beowulf", "snippet": "unrelated text"},
                         {"title": "Hamlet/Act 1", "snippet": "a vaunt indeed"}])
        self.assertEqual([e["work"] for e in out], ["Hamlet"])


if __name__ == "__main__":
    unittest.main()
