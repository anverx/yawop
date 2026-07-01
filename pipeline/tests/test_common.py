"""Unit tests for scripts/common.py helpers (no network)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import common  # noqa: E402


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Records calls; returns queued responses. Raises if called when not expected."""
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        return self.responses.pop(0)


class TestListHelpers(unittest.TestCase):
    def test_five_letter_only(self):
        self.assertEqual(common.five_letter_only(["abcde", "four", "sixsix", "WHICH", "12345"]),
                         ["abcde", "WHICH"])

    def test_dedupe_ci_keeps_first_lowercased(self):
        self.assertEqual(common.dedupe_ci(["Which", "which", "THEIR", "abide"]),
                         ["which", "their", "abide"])

    def test_lines_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.txt"
            common.write_lines(p, ["alpha", "bravo"])
            self.assertEqual(common.read_lines(p), ["alpha", "bravo"])
            self.assertTrue(p.read_text().endswith("\n"))

    def test_jsonl_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            recs = [{"word": "a", "rank": 1, "senses": []}, {"word": "b", "rank": 2, "senses": [{"x": 1}]}]
            common.write_jsonl(p, recs)
            self.assertEqual(common.read_jsonl(p), recs)


class TestApiSenses(unittest.TestCase):
    def test_cache_hit_makes_no_network_call(self):
        cache = {"quoth": [{"pos": "v", "definition": "to say"}]}
        session = FakeSession()  # would IndexError if .get called
        out = common.api_senses("quoth", session, cache)
        self.assertEqual(out, cache["quoth"])
        self.assertEqual(session.calls, 0)

    def test_404_is_cached_as_empty(self):
        cache = {}
        session = FakeSession([FakeResp(status=404)])
        self.assertEqual(common.api_senses("zzzzz", session, cache), [])
        self.assertEqual(cache["zzzzz"], [])

    def test_200_parses_and_tags_source(self):
        payload = [{"meanings": [
            {"partOfSpeech": "verb", "definitions": [{"definition": "to say"}, {"definition": "to say"}]},
            {"partOfSpeech": "noun", "definitions": [{"definition": "a saying"}]},
        ]}]
        cache = {}
        out = common.api_senses("quoth", FakeSession([FakeResp(payload=payload)]), cache)
        self.assertEqual(len(out), 2)  # duplicate definition collapsed
        self.assertEqual({s["source"] for s in out}, {"dictionaryapi.dev"})
        self.assertEqual(out[0]["pos"], "v")
        self.assertEqual(out[0]["pos_label"], "verb")


if __name__ == "__main__":
    unittest.main()
