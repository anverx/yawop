"""Integration tests: run the pure-logic pipeline CLIs on synthetic fixtures.

These invoke the scripts exactly as the Makefile/CI does (subprocess + files),
so they cover the argument contracts too. No network or WordNet needed.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(script, *args):
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"{script} failed ({proc.returncode}):\n{proc.stderr}")
    return proc


def write_jsonl(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def lines(path):
    return path.read_text().split()


class TestPrune(unittest.TestCase):
    def test_drops_undefined_keeps_order_and_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "in.jsonl"
            write_jsonl(src, [
                {"word": "which", "rank": 1, "senses": [{"pos_label": "det", "definition": "x"}]},
                {"word": "zzzzz", "rank": 2, "senses": []},       # undefined -> dropped
                {"word": "abide", "rank": 3, "senses": [{"pos_label": "verb", "definition": "dwell"}]},
            ])
            run("prune_undefined.py", "--in", src,
                "--out-dict", d / "dict.jsonl", "--out-words", d / "words.txt",
                "--out-undefined", d / "undef.txt")
            # puzzle words keep frequency order, undefined dropped
            self.assertEqual(lines(d / "words.txt"), ["which", "abide"])
            # dictionary is alphabetical
            self.assertEqual([r["word"] for r in read_jsonl(d / "dict.jsonl")], ["abide", "which"])
            self.assertEqual(lines(d / "undef.txt"), ["zzzzz"])


class TestAssignTiers(unittest.TestCase):
    def _words(self, d, n):
        p = d / "w.txt"
        p.write_text("\n".join(f"w{i:03d}" for i in range(n)) + "\n")
        return p

    def test_percentile_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            run("assign_tiers.py", "--words", self._words(d, 100), "--out", d / "t.json",
                "--easy", "0.15", "--medium", "0.40")
            t = json.loads((d / "t.json").read_text())["counts"]
            self.assertEqual((t["easy"], t["medium"], t["hard"]), (15, 25, 60))

    def test_rank_by_reorders_unknowns_last(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "w.txt").write_text("rare\ncommon\nmid\n")        # arbitrary input order
            (d / "ref.txt").write_text("common\nmid\n")            # frequency reference
            run("assign_tiers.py", "--words", d / "w.txt", "--out", d / "t.json",
                "--rank-by", d / "ref.txt", "--easy", "0.34", "--medium", "0.67")
            tiers = json.loads((d / "t.json").read_text())["tiers"]
            # 'common' most frequent -> easy; 'rare' (unknown to ref) -> hard
            self.assertEqual(tiers["easy"], ["common"])
            self.assertEqual(tiers["hard"], ["rare"])


class TestSubtract(unittest.TestCase):
    def _minuend(self, d):
        p = d / "guten.jsonl"
        write_jsonl(p, [
            {"word": "which", "rank": 1, "senses": [{"definition": "x"}]},  # common, in modern -> removed
            {"word": "quoth", "rank": 2, "senses": [{"definition": "say"}]},  # archaic, defined
            {"word": "aboon", "rank": 3, "senses": []},                       # archaic, undefined but real
            {"word": "afaik", "rank": 4, "senses": []},                       # junk, undefined, not real
        ])
        return p

    def test_subtraction_with_junk_filter(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "modern.txt").write_text("which\nother\n")
            (d / "whitelist.txt").write_text("quoth\naboon\n")  # real words (Wordle-like)
            run("subtract.py", "--minuend", self._minuend(d),
                "--subtract", d / "modern.txt",
                "--keep-in", d / "whitelist.txt", "--keep-defined",
                "--out-dict", d / "arc.jsonl", "--out-words", d / "arc.txt")
            words = set(lines(d / "arc.txt"))
            self.assertIn("quoth", words)     # defined + whitelisted
            self.assertIn("aboon", words)     # whitelisted though undefined
            self.assertNotIn("which", words)  # subtracted (modern)
            self.assertNotIn("afaik", words)  # junk: neither defined nor whitelisted

    def test_subtract_top_limits_modern_set(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "modern.txt").write_text("which\nquoth\n")  # 'quoth' only removed if top>=2
            run("subtract.py", "--minuend", self._minuend(d),
                "--subtract", d / "modern.txt", "--subtract-top", "1",
                "--out-dict", d / "arc.jsonl", "--out-words", d / "arc.txt")
            words = set(lines(d / "arc.txt"))
            self.assertNotIn("which", words)  # within top-1
            self.assertIn("quoth", words)     # beyond top-1, so not subtracted


class TestCombineSurprise(unittest.TestCase):
    def test_union_merges_senses_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a = d / "a"; a.mkdir(); b = d / "b"; b.mkdir()
            write_jsonl(a / "dictionary.jsonl", [
                {"word": "quoth", "senses": [{"source": "wordnet", "pos_label": "v", "definition": "say"}]}])
            write_jsonl(b / "dictionary.jsonl", [
                {"word": "quoth", "senses": [{"source": "wordnet", "pos_label": "v", "definition": "say"},
                                             {"source": "dictionaryapi.dev", "pos_label": "v", "definition": "declare"}]},
                {"word": "mulct", "senses": [{"source": "wordnet", "pos_label": "n", "definition": "fine"}]}])
            run("combine_surprise.py", "--dicts", a / "dictionary.jsonl", b / "dictionary.jsonl",
                "--out-dict", d / "s.jsonl", "--out-words", d / "s.txt")
            recs = {r["word"]: r for r in read_jsonl(d / "s.jsonl")}
            self.assertEqual(set(recs), {"quoth", "mulct"})
            self.assertEqual(len(recs["quoth"]["senses"]), 2)          # deduped union
            self.assertEqual(set(recs["quoth"]["sources"]), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
